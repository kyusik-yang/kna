"""
kna - Law bills on the agendas of kr-hearings-data v10
======================================================
Finds the meetings whose agenda (안건) in kr-hearings-data v10 lists a law
bill. collect_likms_billinfo.py build calls match_bill_meetings() for the
bill_meetings rows without conf_num, and the build step here writes
bill_agenda_17.parquet.

An agenda item lists a bill in one of three ways. Titles are compared
without spaces or punctuation and with Hanja read as Hangul (hanja package).

  number  the item prints the bill's number, as "(의안번호 N)" in its text or
          in the bill_no of agenda.parquet. The minutes of the 17th to 21st
          Assembly print it without the assembly prefix and leading zeros
          (1718 for 171718), so both forms count. An item that prints another
          number lists no other bill.
  title   the item prints no number and holds the bill's title and
          "(<대표발의자> 의원 대표발의)" or "(정부 제출)". A bare "<대표발의자>
          의원" would also hit the last name of a cosponsor list. A bill whose
          title and 대표발의자 another bill of the same assembly shares is
          "shared", and a shared match alone is no evidence.
  id      the item prints no number, its bill_id in agenda.parquet is the
          bill's, and it holds the bill's title, for a bill without a
          대표발의자 (위원장 and other proposers). The bill_id of agenda.parquet
          alone is not used. In v10.2 it often names a bill of the same title
          by another 대표발의자 (in 37% of the 17th-Assembly items that carry a
          bill_id and no number, 11% of the 19th and about 1% of the 20th and
          21st).

bill_meetings: conf_num_matched and conf_match
----------------------------------------------
For a row without conf_num, the candidates are the v10 meetings held on the
row's date (from date to date_end) of the row's kind:

  plenary            국회본회의
  judiciary          법제사법위원회, full committee
  committee          a committee of the bill (the master's committee_nm or a
                     소관위 of its LIKMS page), not 국회본회의. A subcommittee
                     meeting when the row's name holds 소위 (not
                     안건조정위원회), a full committee meeting otherwise, and
                     either for a 공청회 or 청문회
  related_committee  none, as the related committee is not known here

The meeting is the one candidate whose agenda lists the bill, or else the
only candidate. The row's name agrees with it when 제N회 and 제M차 of the name
are the meeting's session_no and sitting, either way round, because the
17th-Assembly 법사위 rows print them swapped.

  conf_match  agenda_and_name  the agenda lists the bill (number, title or id)
                               and the name agrees
              agenda           the agenda lists the bill and the name does not
                               agree
              name             the name agrees, and the meeting is the only
                               candidate or its agenda lists a shared title
              null             otherwise

conf_num_matched is that meeting's conf_num where conf_match is set.

bill_agenda_17.parquet
----------------------
One row per 17th-Assembly law bill and full committee or subcommittee
meeting of its own committee (not 국회본회의 or 국정감사) whose agenda lists
it by number, title or id.

  bill_no, bill_id   as in the master
  conf_num           the meeting, as in hearing_meetings_summary
  meeting_date       date of the meeting
  committee          committee_raw of the meeting (the parent committee of a
                     subcommittee)
  is_subcommittee
  match              number, title or id, the first that applies
  in_bill_meetings   bill_meetings has a committee-stage row of the bill with
                     this conf_num, conf_num_matched or date
  title_in_minutes   the bill's title, Hanja read as Hangul, appears in the
                     speeches of the meeting. A bill of the same title counts
                     as well. Null for a meeting without turns.

Usage:
    python3 hearings_agenda.py build --out data/_build --master-dir data/_build
    python3 hearings_agenda.py build --out data/_build --v10-dir ~/.cache/kr-hearings-data/v10.2

--v10-dir (or KNA_HEARINGS_V10_DIR, by default ../kr-hearings-data/v10/build/release)
is a v10 build directory or a directory of release assets, as for
build_hearings_summary.py. The build step reads bill_meetings.parquet from
--out, so collect_likms_billinfo.py build runs first. Needs the hanja package
(pip install "kna[hearings]").
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import build_hearings_summary as bhs
from kna_api import write_parquet_atomic

REPO = Path(__file__).resolve().parent
RAW_DIR = REPO / "data" / "raw"
PROCESSED_DIR = REPO / "data" / "processed"
AGES = list(range(17, 23))
AGENDA_AGE = 17
OUT_NAME = f"bill_agenda_{AGENDA_AGE}.parquet"
MATCH_COLS = ["conf_num_matched", "conf_match"]
MEETING_COLUMNS = ["conf_num", "term", "class_name", "committee_raw", "committee_key",
                   "is_subcommittee", "session_no", "sitting", "date", "date_end"]
AGENDA_COLUMNS = ["conf_num", "text", "bill_id", "bill_no"]
BILL_COLUMNS = ["bill_no", "bill_id", "bill_nm", "bill_kind", "committee_nm", "ppsr_kind", "rst_proposer"]
OUT_COLS = ["bill_no", "bill_id", "conf_num", "meeting_date", "committee", "is_subcommittee",
            "match", "in_bill_meetings", "title_in_minutes"]
HANJA = re.compile(r"[㐀-鿿豈-﫿]")


def norm(s) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣一-龥]", "", s or "")


def cnorm(s) -> str:
    """Committee name without parenthesized text, spaces and ·ㆍ/."""
    return re.sub(r"\(.*?\)|[\s·ㆍ/.]", "", s or "")


def hangul(s) -> str:
    if not s or not HANJA.search(s):
        return s or ""
    try:
        import hanja
    except ImportError as e:
        raise SystemExit("hearings_agenda needs the `hanja` package to read Hanja agenda "
                         "titles (pip install hanja)") from e
    return hanja.translate(s, "substitution")


def same_number(printed, bill_no: str) -> bool:
    """A printed bill number is the bill's, in full or without the assembly prefix."""
    return printed == bill_no or printed.lstrip("0") == bill_no[2:].lstrip("0")


# ── inputs ──────────────────────────────────────────────────────────

def load_v10(v10_dir: Path, version: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, str, str | None]:
    """(meetings, agenda, layout, version) of a v10 build or release-asset directory."""
    layout, version = bhs.v10_layout(v10_dir, version)
    if layout is None:
        raise SystemExit(f"ERROR: no meetings.parquet or meetings_v*.parquet in {v10_dir}. "
                         "Set KNA_HEARINGS_V10_DIR or --v10-dir")
    sfx = "" if layout == "build" else f"_{version}"
    meetings = bhs._read_columns(v10_dir / f"meetings{sfx}.parquet", MEETING_COLUMNS)
    agenda = bhs._read_columns(v10_dir / f"agenda{sfx}.parquet", AGENDA_COLUMNS)
    return meetings, agenda, layout, version


def load_bills(master_dir: Path, ages=AGES) -> pd.DataFrame:
    """Every bill of the master (all kinds, for the shared titles), with tn, pn and shared."""
    b = pd.concat([pd.read_parquet(master_dir / f"master_bills_{a}.parquet", columns=BILL_COLUMNS).assign(age=a)
                   for a in ages], ignore_index=True).astype({"bill_no": str, "bill_id": str})
    b["tn"] = b["bill_nm"].map(norm)
    b["pn"] = [norm(p) + "의원대표발의" if k == "의원" and isinstance(p, str) and p
               else ("정부제출" if k == "정부" else "")
               for k, p in zip(b["ppsr_kind"], b["rst_proposer"])]
    b["shared"] = (b["pn"] != "") & b.duplicated(["age", "tn", "pn"], keep=False)
    return b


def committee_keys(meetings: pd.DataFrame) -> dict:
    """Normalized committee name -> the committee_key v10 gives it most often."""
    n = meetings["committee_raw"].map(cnorm)
    return meetings.assign(n=n).groupby("n")["committee_key"].agg(lambda s: s.mode().iloc[0]).to_dict()


def bill_committees(raw: pd.DataFrame, bills: pd.DataFrame, key: dict) -> dict:
    """bill_no -> committee keys of the bill: the 소관위 of its page and the master's committee_nm."""
    com = raw[raw["section"] == "소관위 심사정보"]
    out = {}
    for b, c in zip(com["bill_no"], com["committee"]):
        out.setdefault(b, set()).add(key.get(cnorm(c), cnorm(c)))
    for b, c in zip(bills["bill_no"], bills["committee_nm"]):
        out.setdefault(b, set()).add(key.get(cnorm(c), cnorm(c)))
    return out


def prepare_agenda(agenda: pd.DataFrame) -> pd.DataFrame:
    """agenda with t (normalized text, Hanja read as Hangul) and nums (the bill numbers it prints)."""
    a = agenda.copy()
    a["t"] = a["text"].map(lambda x: norm(hangul(x)))
    printed = a["text"].fillna("").str.replace(r"\s", "", regex=True).str.findall(r"의안번호(\d+)")
    a["nums"] = [tuple(sorted(set(p) | ({str(n)} if pd.notna(n) else set())))
                 for p, n in zip(printed, a["bill_no"])]
    a["bill_id"] = a["bill_id"].astype(object).where(a["bill_id"].notna(), None)
    return a


def lists_bill(item, b) -> str:
    """How one agenda item lists bill b: number, unique, id, shared or ''."""
    if item.nums:
        return "number" if any(same_number(n, b.bill_no) for n in item.nums) else ""
    if b.pn:
        if b.tn in item.t and b.pn in item.t:
            return "shared" if b.shared else "unique"
        return ""
    return "id" if item.bill_id is not None and item.bill_id == b.bill_id and b.tn in item.t else ""


# ── bill_meetings rows without conf_num ─────────────────────────────

ORDER = {"number": 0, "unique": 1, "id": 2, "shared": 3, "": 4}
EVIDENCE = {"number", "unique", "id"}


def match_rows(rows: pd.DataFrame, bills: pd.DataFrame, raw: pd.DataFrame,
               meetings: pd.DataFrame, agenda: pd.DataFrame) -> pd.DataFrame:
    """conf_num_matched and conf_match for bill_meetings rows, on the index of rows."""
    key = committee_keys(meetings)
    vm = meetings.assign(key=meetings["committee_raw"].map(cnorm).map(key),
                         cn=meetings["committee_raw"].map(cnorm),
                         end=meetings["date_end"].fillna(meetings["date"]),
                         sit=meetings["sitting"].astype(str).str.extract(r"(\d+)")[0].astype(float))
    bkeys = bill_committees(raw, bills, key)
    bill = bills.set_index("bill_no")
    items = {c: list(g.itertuples()) for c, g in agenda.groupby("conf_num")}

    out = pd.DataFrame({"conf_num_matched": pd.array([None] * len(rows), dtype="Int64"),
                        "conf_match": pd.Series([None] * len(rows), dtype="object")}, index=rows.index)
    for r in rows.itertuples():
        if r.bill_no not in bill.index:
            continue
        b = bill.loc[r.bill_no].copy()
        b["bill_no"] = r.bill_no
        name = r.meeting_name if isinstance(r.meeting_name, str) else ""
        g = vm[(vm["date"] <= r.meeting_date) & (vm["end"] >= r.meeting_date)]
        if r.stage == "plenary":
            g = g[g["class_name"] == "국회본회의"]
        elif r.stage == "judiciary":
            g = g[(g["cn"] == "법제사법위원회") & ~g["is_subcommittee"]]
        elif r.stage == "committee":
            g = g[g["key"].isin(bkeys.get(r.bill_no, set())) & (g["class_name"] != "국회본회의")]
            if "공청회" not in name and "청문회" not in name:
                named_sub = "소위" in name and "안건조정" not in name
                g = g[g["is_subcommittee"] == named_sub]
        else:
            continue
        if g.empty:
            continue
        how = {}
        for c in g["conf_num"]:
            found = [lists_bill(i, b) for i in items.get(c, [])]
            how[c] = min(found, key=ORDER.get, default="")
        hit = [c for c in g["conf_num"] if how[c]]
        if len(hit) == 1:
            conf, listed = hit[0], how[hit[0]]
        elif len(g) == 1 and not hit:
            conf, listed = g["conf_num"].iloc[0], ""
        else:
            continue
        m = g[g["conf_num"] == conf].iloc[0]
        sess = re.search(r"제(\d+)회", name)
        sit = re.search(r"제(\d+)차", name)
        name_agrees = bool(sess and sit) and (
            (float(sess.group(1)), float(sit.group(1))) in {(m["session_no"], m["sit"]), (m["sit"], m["session_no"])})
        on_agenda = listed in EVIDENCE
        if on_agenda:
            basis = "agenda_and_name" if name_agrees else "agenda"
        elif name_agrees and (listed == "shared" or len(g) == 1):
            basis = "name"
        else:
            continue
        out.at[r.Index, "conf_num_matched"] = int(conf)
        out.at[r.Index, "conf_match"] = basis
    return out


def match_bill_meetings(m: pd.DataFrame, raw: pd.DataFrame, master_dir: Path,
                        v10_dir: Path, version: str | None = None) -> pd.DataFrame:
    """conf_num_matched and conf_match for every bill_meetings row (null where conf_num is set)."""
    meetings, agenda, layout, version = load_v10(v10_dir, version)
    print(f"  agenda match: v10 {layout} {version or ''} at {v10_dir}, "
          f"{len(meetings):,} meetings, {len(agenda):,} agenda items")
    rows = m[m["conf_num"].isna()]
    got = match_rows(rows, load_bills(master_dir), raw, meetings, prepare_agenda(agenda))
    return got.reindex(m.index).astype({"conf_num_matched": "Int64", "conf_match": "object"})


# ── bill_agenda_17 ──────────────────────────────────────────────────

def agenda_pairs(age: int, bills: pd.DataFrame, raw: pd.DataFrame,
                 meetings: pd.DataFrame, agenda: pd.DataFrame) -> pd.DataFrame:
    """(bill, meeting) pairs of one assembly: a law bill and a meeting of its own committee
    whose agenda lists it by link or by a title and 대표발의자 no other bill shares."""
    key = committee_keys(meetings)
    vA = meetings[(meetings["term"] == age) & ~meetings["class_name"].isin(["국회본회의", "국정감사"])]
    vA = vA.assign(key=vA["committee_raw"].map(cnorm).map(key))
    law = bills[(bills["age"] == age) & (bills["bill_kind"] == "법률안")]
    bkeys = bill_committees(raw[raw["age"] == age], law, key)
    a = agenda.merge(vA[["conf_num", "key", "date", "committee_raw", "is_subcommittee"]], on="conf_num")

    by_no = {**{n[2:].lstrip("0"): n for n in law["bill_no"]}, **{n: n for n in law["bill_no"]}}
    no_pn = law[law["pn"] == ""].set_index("bill_id")
    rows = []
    for i in a.itertuples():
        if i.nums:
            for n in i.nums:
                b = by_no.get(n) or by_no.get(n.lstrip("0"))
                if b is not None:
                    rows.append((b, i.conf_num, "number"))
        elif i.bill_id is not None and i.bill_id in no_pn.index:
            b = no_pn.loc[i.bill_id]
            if isinstance(b, pd.Series) and b["tn"] in i.t:
                rows.append((b["bill_no"], i.conf_num, "id"))
    by_key = {k: [i for i in g.itertuples() if not i.nums] for k, g in a.groupby("key")}
    for b in law[(law["pn"] != "") & ~law["shared"]].itertuples():
        for k in bkeys.get(b.bill_no, ()):
            for i in by_key.get(k, ()):
                if b.tn in i.t and b.pn in i.t:
                    rows.append((b.bill_no, i.conf_num, "title"))
    order = {"number": 0, "title": 1, "id": 2}
    p = (pd.DataFrame(rows, columns=["bill_no", "conf_num", "match"])
         .sort_values("match", key=lambda s: s.map(order), kind="stable")
         .drop_duplicates(["bill_no", "conf_num"]))
    p = p.merge(vA[["conf_num", "key", "date", "committee_raw", "is_subcommittee"]], on="conf_num")
    p = p[[k in bkeys.get(b, set()) for b, k in zip(p["bill_no"], p["key"])]]
    p["bill_id"] = p["bill_no"].map(law.set_index("bill_no")["bill_id"])
    return p.rename(columns={"date": "meeting_date", "committee_raw": "committee"})


def meeting_texts(files: list[Path], confs: set) -> dict:
    """conf_num -> the normalized text of its turns, for the meetings in confs."""
    parts: dict = {}
    for f in files:
        for batch in pq.ParquetFile(f).iter_batches(columns=["conf_num", "text"], batch_size=200_000):
            d = batch.to_pandas()
            d = d[d["conf_num"].isin(confs)]
            for c, g in d.groupby("conf_num", sort=False):
                parts.setdefault(c, []).append(" ".join(g["text"].fillna("")))
    return {c: norm(hangul(" ".join(v))) for c, v in parts.items()}


def build(args) -> None:
    out, master_dir = Path(args.out), Path(args.master_dir)
    v10_dir = Path(args.v10_dir) if args.v10_dir else bhs.V10_DIR
    bm_path = out / "bill_meetings.parquet"
    if not bm_path.exists():
        raise SystemExit(f"ERROR: no {bm_path}. Run collect_likms_billinfo.py build first")
    meetings, agenda, layout, version = load_v10(v10_dir, args.v10_version)
    raw = pd.read_parquet(RAW_DIR / f"likms_billinfo_{AGENDA_AGE}.parquet")
    bills = load_bills(master_dir)
    p = agenda_pairs(AGENDA_AGE, bills, raw, meetings, prepare_agenda(agenda[agenda["conf_num"].isin(
        meetings.loc[meetings["term"] == AGENDA_AGE, "conf_num"])]))

    bm = pd.read_parquet(bm_path, columns=["age", "bill_no", "stage", "conf_num", "conf_num_matched", "meeting_date"])
    bm = bm[(bm["age"] == AGENDA_AGE) & (bm["stage"] == "committee")]
    known = (set(zip(bm["bill_no"], bm["conf_num"].dropna().astype(int)))
             | set(zip(bm["bill_no"], bm["conf_num_matched"].dropna().astype(int)))
             | set(zip(bm["bill_no"], bm["meeting_date"])))
    p["in_bill_meetings"] = [(b, c) in known or (b, d) in known
                             for b, c, d in zip(p["bill_no"], p["conf_num"], p["meeting_date"])]

    if layout == "build":
        files = sorted((v10_dir / "turns" / f"t{AGENDA_AGE}").glob("part-*.parquet"))
    else:
        files = [v10_dir / f"turns_t{AGENDA_AGE}_{version}.parquet"]
    if not files or not all(f.exists() for f in files):
        raise SystemExit(f"ERROR: no {AGENDA_AGE}th-Assembly turn files under {v10_dir}")
    texts = meeting_texts(files, set(p["conf_num"]))
    tn = p["bill_no"].map(bills.set_index("bill_no")["tn"])
    p["title_in_minutes"] = pd.array([t in texts[c] if c in texts else None
                                      for t, c in zip(tn, p["conf_num"])], dtype="boolean")

    p = (p.astype({"conf_num": "int64", "is_subcommittee": bool, "in_bill_meetings": bool})
         .sort_values(["bill_no", "meeting_date", "conf_num"])[OUT_COLS].reset_index(drop=True))
    out.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(p, out / OUT_NAME)
    law = bills[(bills["age"] == AGENDA_AGE) & (bills["bill_kind"] == "법률안")]
    new = p[~p["in_bill_meetings"]]
    have = set(bm["bill_no"])
    print(f"build: {OUT_NAME} {len(p):,} pairs, {p['bill_no'].nunique():,} bills, "
          f"{p['is_subcommittee'].sum():,} subcommittee; match " +
          ", ".join(f"{k} {v:,}" for k, v in p["match"].value_counts().items()))
    print(f"  in bill_meetings {p['in_bill_meetings'].sum():,}, new {len(new):,} "
          f"({new['is_subcommittee'].sum():,} subcommittee); law bills with a committee-stage row "
          f"{len(have):,} of {len(law):,}, with the new pairs {len(have | set(new['bill_no'])):,}")
    print("  title in the minutes: " + ", ".join(
        f"{'sub' if s else 'full'} {'new' if not k else 'known'} {g.mean():.3f} of {g.notna().sum():,}"
        for (s, k), g in p.groupby(["is_subcommittee", "in_bill_meetings"])["title_in_minutes"]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Law bills on the agendas of kr-hearings-data v10")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help=f"write {OUT_NAME}")
    b.add_argument("--out", default=str(PROCESSED_DIR))
    b.add_argument("--master-dir", default=str(PROCESSED_DIR))
    b.add_argument("--v10-dir", default=None, help="v10 build or release-asset directory")
    b.add_argument("--v10-version", default=None, help="release version when --v10-dir holds several")
    args = ap.parse_args()
    {"build": build}[args.command](args)


if __name__ == "__main__":
    main()
