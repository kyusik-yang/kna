"""
kna - Structural tables (subcommittee stages, alternatives, cosponsorship)
=========================================================================
Builds analysis tables from the official sources that collect_structure.py
and collect.py store in data/raw.

Usage:
    python3 build_structure.py all --out data/_build --members-dir data/_build
    python3 build_structure.py subcommittee --out data/_build
    python3 build_structure.py alternatives --out data/_build
    python3 build_structure.py edges --out data/_build --members-dir data/_build

subcommittee  data/raw/TVBPMCONFINFO_{age}  -> subcommittee_reviews.parquet
              One row per bill x subcommittee stage (소위 심사정보).
alternatives  data/raw/alt_absorption_{age} -> alternative_absorption.parquet
              One row per committee alternative (대안) x absorbed bill.
edges         data/raw/nzmimeepazxkubdpn_{age} + BILLINFOPPSR_{age}
              -> cosponsorship_edges.parquet (17th-22nd).
              Per member bill, the first available source wins:
                1. BILLINFOPPSR_{age} (official list, party at proposal)
                2. the legacy edge file (korean-assembly-bills copy) when the
                   bill has fewer than 100 rows there, i.e. not truncated
                3. the master code lists RST_MONA_CD / PUBL_MONA_CD with
                   names and party at election from members_{age}

A missing raw input stops the build unless --allow-missing is passed, so a
partial table is never written by accident. Validation reports go to
--report-dir.
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

REPO = Path(__file__).parent
RAW_DIR = REPO / "data" / "raw"
PROCESSED_DIR = REPO / "data" / "processed"
FETCHLOG_DIR = RAW_DIR / "fetchlog"
ALL_AGES = [17, 18, 19, 20, 21, 22]

MONA_RE = re.compile(r"^[0-9A-Z]{8}$")
ROLE_RANK = {"대표발의": 0, "공동발의": 1, "찬성": 2}
# The upstream proposer collection stopped at 100 names per bill.
LEGACY_CAP = 100
EDGE_COLS = ["bill_id", "member_name", "member_id", "party", "role", "age",
             "bill_no", "party_source", "source"]


def parse_ages(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def safe_date(series: pd.Series) -> pd.Series:
    """Convert to datetime, coercing errors to NaT. Handles '0' and empty strings."""
    s = series.replace({"0": pd.NaT, "": pd.NaT, " ": pd.NaT})
    return pd.to_datetime(s, errors="coerce")


def split_codes(s) -> list[str]:
    """'A1234567,B1234567' -> ['A1234567', 'B1234567'] (joint leads are comma-joined)."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    return [c.strip() for c in str(s).split(",") if c.strip()]


def proposer_count(text) -> int:
    """Number of proposers stated in the PROPOSER text.

    '홍길동의원 등 11인' -> 11 (named leads are inside the 11)
    '홍길동의원 외 10인' -> 11 (named leads + 10)
    'AㆍBㆍC의원 외 185인' -> 188
    '이두아의원 등 1인 외 165인' -> 166
    등 N인 counts the proposers (leads + co-proposers), 외 M인 the supporters.
    Official lists (BILLINFOPPSR) confirm that '외' names are 찬성자.
    """
    text = text if isinstance(text, str) else ""
    head = re.split(r"등\s*\d+\s*인|외\s*\d+\s*인", text)[0]
    n_named = len(re.findall(r"의원", head))
    m_deung = re.search(r"등\s*(\d+)\s*인", text)
    m_oe = re.search(r"외\s*(\d+)\s*인", text)
    base = int(m_deung.group(1)) if m_deung else n_named
    return base + (int(m_oe.group(1)) if m_oe else 0)


def supporter_count(text) -> int:
    """Supporters (찬성의원): the M of '외 M인' ('등 N인 외 M인' or 'X의원 외 M인')."""
    text = text if isinstance(text, str) else ""
    m = re.search(r"외\s*(\d+)\s*인", text)
    return int(m.group(1)) if m else 0


def fetch_status(log_path: Path) -> "dict[str, str] | None":
    """Per-key status of a collector fetch log: 'rows', 'empty' or 'error'.

    Reads only the status, and skips a half-written last line, because the
    collector may be appending to the log while this runs. Returns None when
    the log is absent (fetch logs are git-ignored, so a fresh clone has none).
    """
    status: dict[str, str] = {}
    if not log_path.exists():
        return None
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") != "ok":
                status[rec["key"]] = "error"
            else:
                status[rec["key"]] = "rows" if rec.get("rows") else "empty"
    return status


def check_inputs(paths: list[Path], allow_missing: bool, what: str) -> list[Path]:
    """Return the missing paths; stop unless allow_missing."""
    missing = [p for p in paths if not p.exists()]
    if missing:
        names = ", ".join(p.name for p in missing)
        if not allow_missing:
            raise SystemExit(f"{what}: missing raw input(s): {names}. "
                             f"Collect them first or pass --allow-missing.")
        print(f"  WARNING {what}: missing, built without them: {names}")
    return missing


def load_master(master_dir: Path, age: int) -> pd.DataFrame:
    p = master_dir / f"master_bills_{age}.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["bill_id", "bill_kind", "committee_dt"])
    cols = pq.read_schema(p).names
    use = [c for c in ["bill_id", "bill_kind", "committee_dt"] if c in cols]
    return pd.read_parquet(p, columns=use)


def bill_no_lookup(age: int) -> dict[str, str]:
    """BILL_ID -> BILL_NO over every raw bill list of one assembly."""
    out: dict[str, str] = {}
    for name in ["nzmimeepazxkubdpn", "nzpltgfqabtcpsmai", "BILLRCP"]:
        p = RAW_DIR / f"{name}_{age}.parquet"
        if p.exists():
            d = pd.read_parquet(p, columns=["BILL_ID", "BILL_NO"]).dropna()
            out.update(dict(zip(d["BILL_ID"], d["BILL_NO"])))
    # A vetoed bill awaiting its re-vote is listed only under its GOV_ record,
    # which carries the same BILL_NO as the original PRC_ record.
    for bid, no in list(out.items()):
        if bid.startswith("GOV_"):
            out.setdefault("PRC_" + bid[4:], no)
    return out


# ── 1. Subcommittee stages ────────────────────────────────────────────────

def build_subcommittee(ages, out: Path, master_dir: Path, allow_missing: bool):
    print("=" * 60)
    print("1. Subcommittee review stages (TVBPMCONFINFO)")
    print("=" * 60)
    paths = {age: RAW_DIR / f"TVBPMCONFINFO_{age}.parquet" for age in ages}
    missing = check_inputs(list(paths.values()), allow_missing, "subcommittee")

    frames = []
    for age, p in paths.items():
        if p in missing:
            continue
        d = pd.read_parquet(p)
        d.columns = [c.lower() for c in d.columns]
        d["age"] = pd.to_numeric(d["age"], errors="coerce").fillna(age).astype(int)
        for c in ["submit_dt", "present_dt", "proc_dt"]:
            d[c] = safe_date(d[c])
        for c in ["present_session", "present_cha", "proc_session", "proc_cha"]:
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("Int64")
        d["is_direct_referral"] = (d["enroll_type"] == "Y").astype(int)
        frames.append(d)
    if not frames:
        print("  No subcommittee data; nothing written.")
        return
    sub = pd.concat(frames, ignore_index=True)
    sub = sub.sort_values(["age", "bill_no", "present_dt", "submit_dt", "sub_committee_name"],
                          na_position="last", kind="mergesort").reset_index(drop=True)

    print(f"  {'age':>4} {'rows':>8} {'no_sub':>7} {'bills':>7} {'direct':>7} {'조정위':>6} {'dup':>4}"
          f" {'master':>7} {'cov_all':>8} {'cov_sub':>8} {'cov_law':>8} {'cov_ref':>8}")
    for age, g in sub.groupby("age"):
        bills = set(g["bill_id"])
        # Rows without a subcommittee name carry no subcommittee stage (almost
        # all are bills never sent to one), so named stages are counted apart
        bills_sub = set(g.loc[g["sub_committee_name"].notna(), "bill_id"])
        m = load_master(master_dir, age)
        n_m = len(m)
        cov_all = len(bills & set(m["bill_id"])) / n_m if n_m else float("nan")
        cov_sub = len(bills_sub & set(m["bill_id"])) / n_m if n_m else float("nan")
        law = m[m["bill_kind"] == "법률안"] if "bill_kind" in m else m.iloc[0:0]
        cov_law = len(bills & set(law["bill_id"])) / len(law) if len(law) else float("nan")
        ref = m[m["committee_dt"].notna()] if "committee_dt" in m else m.iloc[0:0]
        cov_ref = len(bills & set(ref["bill_id"])) / len(ref) if len(ref) else float("nan")
        n_adj = g["sub_committee_name"].fillna("").str.contains("안건조정").sum()
        n_dup = g.duplicated().sum()
        print(f"  {age:>4} {len(g):>8,} {g['sub_committee_name'].isna().sum():>7,} {len(bills):>7,}"
              f" {g['is_direct_referral'].sum():>7,} {n_adj:>6,} {n_dup:>4} {n_m:>7,}"
              f" {cov_all:>8.1%} {cov_sub:>8.1%} {cov_law:>8.1%} {cov_ref:>8.1%}")
    print("  cov_all = share of master bills with >= 1 row; cov_sub = share with >= 1 named"
          " subcommittee stage; no_sub = rows without a subcommittee name (almost all bills"
          " never sent to a subcommittee); cov_law = share of 법률안 with >= 1 row;"
          " cov_ref = share of bills referred to committee (committee_dt set) with >= 1 row;"
          " direct = 소위 직접회부 (ENROLL_TYPE Y); 조정위 = 안건조정위원회 rows;"
          " dup = exact duplicate rows (kept as the API returns them)")

    outpath = out / "subcommittee_reviews.parquet"
    sub.to_parquet(outpath, index=False)
    print(f"  Saved: {outpath} ({len(sub):,} rows, {sub['bill_id'].nunique():,} bills)")


# ── 2. Alternative absorption links ───────────────────────────────────────

def alternative_ids(age: int) -> list[str]:
    """Committee alternatives of one assembly, as queried by
    collect_structure.alternative_ids (bill name ends with '(대안)')."""
    ids: set[str] = set()
    for name, col in [("BILLRCP", "BILL_NM"), ("nzpltgfqabtcpsmai", "BILL_NAME")]:
        p = RAW_DIR / f"{name}_{age}.parquet"
        if p.exists():
            d = pd.read_parquet(p, columns=["BILL_ID", col])
            is_alt = d[col].fillna("").str.strip().str.endswith("(대안)")
            ids |= set(d.loc[is_alt, "BILL_ID"].dropna())
    ids |= {"PRC_" + i[4:] for i in ids if i.startswith("GOV_")}
    return sorted(i for i in ids if not i.startswith("GOV_"))


def absorbed_universe(age: int) -> set[str]:
    """Bills whose final result is 대안반영폐기 in the processed list or BILLRCP."""
    ids: set[str] = set()
    for name, col in [("nzpltgfqabtcpsmai", "PROC_RESULT_CD"), ("BILLRCP", "PROC_RSLT")]:
        p = RAW_DIR / f"{name}_{age}.parquet"
        if p.exists():
            d = pd.read_parquet(p, columns=["BILL_ID", col])
            ids |= set(d.loc[d[col] == "대안반영폐기", "BILL_ID"].dropna())
    return ids


def build_alternatives(ages, out: Path, allow_missing: bool, report_dir: Path):
    print("\n" + "=" * 60)
    print("2. Alternative absorption links (TVBPMBILL11 BILL_ID_REF)")
    print("=" * 60)
    paths = {age: RAW_DIR / f"alt_absorption_{age}.parquet" for age in ages}
    missing = check_inputs(list(paths.values()), allow_missing, "alternatives")

    frames, cov = [], []
    for age, p in paths.items():
        alts = alternative_ids(age)
        universe = absorbed_universe(age)
        done = fetch_status(FETCHLOG_DIR / f"TVBPMBILL11_{age}.jsonl")
        if done is None:
            n_logged = n_failed = pd.NA
            print(f"  NOTE alternatives {age}: no TVBPMBILL11 fetch log, so collection"
                  f" completeness cannot be checked")
        else:
            n_logged = sum(1 for a in alts if a in done)
            n_failed = sum(1 for a in alts if done.get(a) == "error")
            if n_failed or n_logged < len(alts):
                print(f"  WARNING alternatives {age}: {len(alts) - n_logged} of {len(alts)}"
                      f" alternatives not fetched and {n_failed} failed; rerun"
                      f" collect_structure.py alternatives")
        row = {"age": age, "alternatives": len(alts), "fetchlog_done": n_logged,
               "fetchlog_failed": n_failed, "file": p.name if p not in missing else "MISSING",
               "alts_with_rows": 0, "links": 0, "absorbed_universe": len(universe),
               "absorbed_linked": 0}
        if p in missing:
            cov.append(row)
            continue
        d = pd.read_parquet(p)
        nos = bill_no_lookup(age)
        e = pd.DataFrame({
            "age": age,
            "alt_bill_id": d["ALT_BILL_ID"],
            "alt_bill_no": d["ALT_BILL_ID"].map(nos),
            "absorbed_bill_id": d["BILL_ID"],
            "absorbed_bill_no": d["BILL_NO"],
            "absorbed_proc_rslt": d["PROC_RESULT_CD"],
        })
        n_self = (e["alt_bill_id"] == e["absorbed_bill_id"]).sum()
        e = e[e["alt_bill_id"] != e["absorbed_bill_id"]]
        n_dup = e.duplicated(["alt_bill_id", "absorbed_bill_id"]).sum()
        e = e.drop_duplicates(["alt_bill_id", "absorbed_bill_id"])
        linked = set(e["absorbed_bill_id"])
        row.update({
            "alts_with_rows": e["alt_bill_id"].nunique(),
            "links": len(e),
            "absorbed_linked": len(linked & universe),
            "links_not_대안반영폐기": int((e["absorbed_proc_rslt"] != "대안반영폐기").sum()),
            "absorbed_in_2plus_alts": int((e.groupby("absorbed_bill_id").size() > 1).sum()),
            "alt_bill_no_missing": int(e["alt_bill_no"].isna().sum()),
            "absorbed_not_in_bill_lists": int((~e["absorbed_bill_id"].isin(nos.keys())).sum()),
            "self_links_dropped": int(n_self),
            "duplicates_dropped": int(n_dup),
        })
        cov.append(row)
        frames.append(e)

    cov = pd.DataFrame(cov)
    cov["share_alts_with_rows"] = cov["alts_with_rows"] / cov["alternatives"]
    cov["share_absorbed_linked"] = cov["absorbed_linked"] / cov["absorbed_universe"]
    print(cov.to_string(index=False))
    cov.to_csv(report_dir / "alternative_absorption_coverage.csv", index=False)

    if not frames:
        print("  No absorption data; nothing written.")
        return
    alt = pd.concat(frames, ignore_index=True)
    alt = alt.sort_values(["age", "alt_bill_no", "absorbed_bill_no"],
                          kind="mergesort").reset_index(drop=True)
    outpath = out / "alternative_absorption.parquet"
    alt.to_parquet(outpath, index=False)
    print(f"  Saved: {outpath} ({len(alt):,} links, ages {sorted(alt['age'].unique())})")


# ── 3. Cosponsorship edges ────────────────────────────────────────────────

def load_members(members_dir: Path, age: int) -> pd.DataFrame:
    m = pd.read_parquet(members_dir / f"members_{age}.parquet",
                        columns=["mona_cd", "member_name", "party"])
    return m.drop_duplicates("mona_cd")


def explode_codes(bills: pd.DataFrame, col: str) -> pd.DataFrame:
    x = bills[["BILL_ID", col]].copy()
    x["member_id"] = x[col].map(split_codes)
    x = x.explode("member_id").dropna(subset=["member_id"])
    return x[["BILL_ID", "member_id"]].rename(columns={"BILL_ID": "bill_id"})


def edges_from_ppsr(ppsr: pd.DataFrame, members: pd.DataFrame, age: int) -> pd.DataFrame:
    """Official proposer list; the requested id (_BILL_ID) is the bill id.

    PPSR_ROLE separates proposers (발의자) from supporters (찬성자, the
    '외 M인' of the proposer text). REP_DIV marks the lead proposer(s):
    대표발의, or 1인발의 when one member proposes with supporters only.
    """
    rep = ppsr["REP_DIV"].fillna("")
    known_rep, known_role = {"", "대표발의", "1인발의"}, {"발의자", "찬성자"}
    odd = ppsr[~rep.isin(known_rep) | ~ppsr["PPSR_ROLE"].isin(known_role)]
    if len(odd):
        print(f"    WARNING {age}: {len(odd)} BILLINFOPPSR rows with unexpected codes: "
              f"{odd.groupby(['REP_DIV', 'PPSR_ROLE'], dropna=False).size().to_dict()}")
    role = pd.Series("공동발의", index=ppsr.index)
    role[ppsr["PPSR_ROLE"] == "찬성자"] = "찬성"
    role[rep.str.contains("대표") | (rep == "1인발의")] = "대표발의"
    e = pd.DataFrame({
        "bill_id": ppsr["_BILL_ID"],
        "member_name": ppsr["PPSR_NM"],
        "member_id": ppsr["NASS_CD"],
        "party": ppsr["PPSR_POLY_NM"],
        "role": role,
    })
    # A missing NASS_CD is filled by an unambiguous name match within the assembly
    name_to_id = members.drop_duplicates("member_name", keep=False).set_index("member_name")["mona_cd"]
    no_id = e["member_id"].isna()
    if no_id.any():
        e.loc[no_id, "member_id"] = e.loc[no_id, "member_name"].map(name_to_id)
        print(f"    {age}: {no_id.sum()} BILLINFOPPSR rows without NASS_CD, "
              f"{e.loc[no_id, 'member_id'].notna().sum()} matched by name")
    e["party_source"] = e["party"].notna().map({True: "proposal", False: None})
    e["source"] = "BILLINFOPPSR"
    return e


def edges_from_legacy(legacy: pd.DataFrame, bills: pd.DataFrame) -> pd.DataFrame:
    """Rows of the old edge file for bills it did not truncate.

    The old role column is 대표발의/1인발의 for leads and None for everyone
    else, mixing co-proposers (공동발의) and supporters (찬성). The master's
    PUBL_MONA_CD lists co-proposers only, so a None row is a co-proposer when
    the member is in it and a supporter otherwise.
    """
    e = legacy.copy()
    if "source" in e.columns:
        # A rebuilt file already carries mapped roles; keep its legacy rows as they are
        return e[EDGE_COLS[:5] + ["party_source"]]
    rst = set(explode_codes(bills, "RST_MONA_CD").itertuples(index=False, name=None))
    publ = set(explode_codes(bills, "PUBL_MONA_CD").itertuples(index=False, name=None))
    key = list(zip(e["bill_id"], e["member_id"]))
    role = pd.Series("찬성", index=e.index)
    role[[k in publ for k in key]] = "공동발의"
    role[[k in rst for k in key]] = "대표발의"
    role[e["role"].isin(["대표발의", "1인발의"])] = "대표발의"
    e["role"] = role
    e["party_source"] = e["party"].notna().map({True: "proposal", False: None})
    return e[EDGE_COLS[:5] + ["party_source"]]


def edges_from_codes(bills: pd.DataFrame) -> pd.DataFrame:
    lead = explode_codes(bills, "RST_MONA_CD").assign(role="대표발의")
    cosp = explode_codes(bills, "PUBL_MONA_CD").assign(role="공동발의")
    e = pd.concat([lead, cosp], ignore_index=True)
    e["party_source"] = None
    e["source"] = "master_codes"
    return e


def load_legacy(path: Path, allow_missing: bool) -> tuple[pd.DataFrame, bool]:
    """The old edge file, and whether it is a file this script already rebuilt.

    After the rebuilt file replaces the old one in data/processed, a rerun
    reads back only its legacy_edges rows, which are the old rows it kept.
    Without it, 20th-22nd bills fall back to master codes, which drop the
    supporters and the party at proposal, so a missing file stops the build.
    """
    if not path.exists():
        check_inputs([path], allow_missing, "edges (legacy edge file, --legacy-edges)")
        print("  Sources are BILLINFOPPSR and master codes only.")
        return pd.DataFrame(columns=["bill_id", "member_name", "member_id", "party", "role"]), False
    legacy = pd.read_parquet(path)
    rebuilt = "source" in legacy.columns
    if rebuilt:
        legacy = legacy[legacy["source"] == "legacy_edges"]
        print(f"  Legacy rows read from a rebuilt edge file ({path}): {len(legacy):,}")
    return legacy, rebuilt


def build_edges(ages, out: Path, members_dir: Path, legacy_path: Path,
                allow_missing: bool, report_dir: Path):
    print("\n" + "=" * 60)
    print("3. Cosponsorship edges (BILLINFOPPSR > legacy < 100 > master codes)")
    print("=" * 60)
    bill_paths = [RAW_DIR / f"nzmimeepazxkubdpn_{age}.parquet" for age in ages]
    member_paths = [members_dir / f"members_{age}.parquet" for age in ages]
    ppsr_paths = {age: RAW_DIR / f"BILLINFOPPSR_{age}.parquet" for age in ages}
    check_inputs(bill_paths + member_paths, False, "edges")
    missing = check_inputs(list(ppsr_paths.values()), allow_missing, "edges")

    legacy_all, legacy_rebuilt = load_legacy(legacy_path, allow_missing)
    legacy_n = legacy_all.groupby("bill_id").size()

    frames, checks = [], []
    for age in ages:
        bills = pd.read_parquet(RAW_DIR / f"nzmimeepazxkubdpn_{age}.parquet",
                                columns=["BILL_ID", "BILL_NO", "PROPOSER",
                                         "RST_MONA_CD", "PUBL_MONA_CD"])
        bills = bills.drop_duplicates("BILL_ID")
        members = load_members(members_dir, age)
        ids = set(bills["BILL_ID"])

        # Source 1: official proposer lists
        e1 = pd.DataFrame(columns=EDGE_COLS[:5] + ["party_source", "source"])
        p = ppsr_paths[age]
        if p not in missing:
            ppsr = pd.read_parquet(p)
            ppsr = ppsr[ppsr["_BILL_ID"].isin(ids)]
            e1 = edges_from_ppsr(ppsr, members, age)
        done = set(e1["bill_id"])

        # Source 2: legacy rows of bills the old file did not truncate
        ok_legacy = set(legacy_n[legacy_n < LEGACY_CAP].index) & (ids - done)
        e2 = edges_from_legacy(legacy_all[legacy_all["bill_id"].isin(ok_legacy)],
                               bills[bills["BILL_ID"].isin(ok_legacy)])
        e2["source"] = "legacy_edges"
        done |= set(e2["bill_id"])

        # Source 3: master code lists
        rest = bills[~bills["BILL_ID"].isin(done)]
        e3 = edges_from_codes(rest)

        e = pd.concat([e1, e2, e3], ignore_index=True)
        # Names and missing parties from members_{age} (party at election)
        mem = members.set_index("mona_cd")
        e["member_name"] = e["member_name"].fillna(e["member_id"].map(mem["member_name"]))
        no_party = e["party"].isna()
        e.loc[no_party, "party"] = e.loc[no_party, "member_id"].map(mem["party"])
        e.loc[no_party & e["party"].notna(), "party_source"] = "elected"

        # One row per bill x member, keeping the strongest role
        e["_rank"] = e["role"].map(ROLE_RANK)
        n_before = len(e)
        has_id = e["member_id"].notna()
        e = pd.concat([e[has_id].sort_values(["bill_id", "member_id", "_rank"])
                        .drop_duplicates(["bill_id", "member_id"]), e[~has_id]])
        if n_before != len(e):
            print(f"    {age}: {n_before - len(e)} duplicate bill x member rows dropped")
        e["age"] = age
        e["bill_no"] = e["bill_id"].map(dict(zip(bills["BILL_ID"], bills["BILL_NO"])))
        n_unknown = (~e["member_id"].isin(members["mona_cd"])).sum()
        if n_unknown:
            print(f"    WARNING {age}: {n_unknown} edges with a member_id not in members_{age}")
        frames.append(e)

        # Per-bill validation against the PROPOSER text
        g = e.groupby("bill_id")
        chk = pd.DataFrame({
            "bill_id": bills["BILL_ID"].values,
            "bill_no": bills["BILL_NO"].values,
            "proposer_text": bills["PROPOSER"].values,
        })
        chk["age"] = age
        chk["text_total"] = chk["proposer_text"].map(proposer_count)
        chk["text_supporters"] = chk["proposer_text"].map(supporter_count)
        chk["source"] = chk["bill_id"].map(g["source"].first())
        chk["n_edges"] = chk["bill_id"].map(g.size()).fillna(0).astype(int)
        for r in ROLE_RANK:
            chk[f"n_{r}"] = chk["bill_id"].map(e[e["role"] == r].groupby("bill_id").size()).fillna(0).astype(int)
        chk["legacy_rows"] = chk["bill_id"].map(legacy_n).fillna(0).astype(int)
        # BILLINFOPPSR fetch status: a master_codes mismatch with 'not_fetched'
        # is waiting for the collector, one with 'rows' or 'empty' is final
        status = fetch_status(FETCHLOG_DIR / f"BILLINFOPPSR_{age}.jsonl")
        chk["ppsr_status"] = (chk["bill_id"].map(status).fillna("not_fetched")
                              if status is not None else "no_fetchlog")
        checks.append(chk)

    edges = pd.concat(frames, ignore_index=True)
    edges = edges.sort_values(["age", "bill_no", "_rank", "member_name", "member_id"],
                              kind="mergesort")[EDGE_COLS].reset_index(drop=True)
    chk = pd.concat(checks, ignore_index=True)
    chk["match"] = chk["n_edges"] == chk["text_total"]
    # Role split: 대표발의 + 공동발의 = the proposers, 찬성 = the '외 M인' supporters
    chk["role_match"] = ((chk["n_대표발의"] + chk["n_공동발의"]
                          == chk["text_total"] - chk["text_supporters"])
                         & (chk["n_찬성"] == chk["text_supporters"]))
    chk.loc[chk["n_edges"] == 0, "source"] = "none"

    bad_ids = edges.loc[~edges["member_id"].fillna("").str.match(MONA_RE), "member_id"]
    if len(bad_ids):
        print(f"  WARNING: {len(bad_ids)} edges with a member_id outside ^[0-9A-Z]{{8}}$: "
              f"{bad_ids.unique()[:10].tolist()}")

    # Report
    print("\n  Edges by age and source:")
    print(edges.pivot_table(index="age", columns="source", values="bill_id",
                            aggfunc="size", fill_value=0).to_string())
    print("\n  Edges by age and role:")
    print(edges.pivot_table(index="age", columns="role", values="bill_id",
                            aggfunc="size", fill_value=0).to_string())
    print("\n  Bills by age and source (none = no edges):")
    print(chk.pivot_table(index="age", columns="source", values="bill_id",
                          aggfunc="size", fill_value=0).to_string())
    print("\n  Edge count vs PROPOSER text (bills; role_split = total matches but the"
          " 발의/찬성 split does not):")
    summ = chk.groupby(["age", "source"]).agg(bills=("bill_id", "size"),
                                              match=("match", "sum"))
    summ["mismatch"] = summ["bills"] - summ["match"]
    summ["role_split"] = chk[chk["match"] & ~chk["role_match"]].groupby(["age", "source"]).size()
    summ["role_split"] = summ["role_split"].fillna(0).astype(int)
    print(summ.to_string())
    mism = chk[~chk["match"] | ~chk["role_match"]].copy()
    mism["mismatch_type"] = mism["match"].map({False: "count", True: "role_split"})
    mism["diff"] = mism["n_edges"] - mism["text_total"]
    mism.to_csv(report_dir / "cosponsorship_mismatch.csv", index=False)
    print(f"  Mismatch report: {report_dir / 'cosponsorship_mismatch.csv'} ({len(mism):,} bills)")
    cnt = mism[mism["mismatch_type"] == "count"]
    if len(cnt):
        print("  Count mismatches by source and BILLINFOPPSR fetch status"
              " (master_codes x not_fetched = still waiting for the collector):")
        print(pd.crosstab([cnt["age"], cnt["source"]], cnt["ppsr_status"]).to_string())

    at_cap = chk[(chk["n_edges"] == LEGACY_CAP)]
    print(f"\n  Bills with exactly {LEGACY_CAP} edges: {len(at_cap)} "
          f"(text says {LEGACY_CAP}: {(at_cap['text_total'] == LEGACY_CAP).sum()})")
    capped = at_cap[at_cap["text_total"] != LEGACY_CAP]
    if len(capped):
        raise SystemExit(f"{len(capped)} bills have exactly {LEGACY_CAP} edges while their "
                         f"text says otherwise: {capped['bill_no'].tolist()[:10]}")

    outpath = out / "cosponsorship_edges.parquet"
    edges.to_parquet(outpath, index=False)
    print(f"  Saved: {outpath} ({len(edges):,} edges, {edges['bill_id'].nunique():,} bills)")

    if legacy_rebuilt:
        print("  Degree-bias report skipped: the legacy input is a rebuilt file, not the"
              " original upstream copy.")
    else:
        degree_bias_report(edges, legacy_all, legacy_n, report_dir)


def choseong(name) -> str:
    """Initial consonant of the first syllable (가나다 order key)."""
    if not isinstance(name, str) or not name:
        return "?"
    code = ord(name[0]) - 0xAC00
    if not 0 <= code < 11172:
        return "?"
    return "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"[code // 588]


def degree_bias_report(edges, legacy, legacy_n, report_dir: Path):
    """Degree change (bills per member) against the legacy file, 20th-22nd."""
    if legacy.empty:
        return
    new = edges[edges["age"].isin([20, 21, 22])]
    old = legacy.merge(new[["bill_id", "age"]].drop_duplicates(), on="bill_id")
    capped = set(legacy_n[legacy_n >= LEGACY_CAP].index)
    rows = []
    for (age, mid), g in new.groupby(["age", "member_id"]):
        rows.append((age, mid, g["member_name"].iloc[0], len(g), g["bill_id"].isin(capped).sum()))
    deg = pd.DataFrame(rows, columns=["age", "member_id", "member_name", "deg_new", "deg_new_capped"])
    od = old.groupby(["age", "member_id"]).agg(deg_old=("bill_id", "size"),
                                               deg_old_capped=("bill_id", lambda s: s.isin(capped).sum()))
    deg = deg.merge(od.reset_index(), on=["age", "member_id"], how="outer").fillna(
        {"deg_new": 0, "deg_new_capped": 0, "deg_old": 0, "deg_old_capped": 0})
    old_names = old.drop_duplicates("member_id").set_index("member_id")["member_name"]
    deg["member_name"] = deg["member_name"].fillna(deg["member_id"].map(old_names))
    deg["gain_capped"] = deg["deg_new_capped"] - deg["deg_old_capped"]
    deg["initial"] = deg["member_name"].map(choseong)
    deg.to_csv(report_dir / "cosponsorship_degree_change.csv", index=False)

    print("\n  Truncation bias: edges gained on the bills the legacy file capped at "
          f"{LEGACY_CAP}, by initial consonant of the member's name (20th-22nd):")
    by = deg.groupby("initial").agg(members=("member_id", "size"),
                                    capped_bills_old=("deg_old_capped", "sum"),
                                    capped_bills_new=("deg_new_capped", "sum"),
                                    mean_gain=("gain_capped", "mean"),
                                    share_gaining=("gain_capped", lambda s: (s > 0).mean()))
    print(by.round(2).to_string())
    early = deg[deg["initial"].isin(list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆ"))]["gain_capped"].mean()
    late = deg[deg["initial"].isin(list("ㅇㅈㅉㅊㅋㅌㅍㅎ"))]["gain_capped"].mean()
    print(f"  Mean edges regained per member: ㄱ-ㅆ {early:.2f}, ㅇ-ㅎ {late:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Build structural bill tables")
    parser.add_argument("command", nargs="?", default="all",
                        choices=["subcommittee", "alternatives", "edges", "all"])
    parser.add_argument("--ages", default="17-22")
    parser.add_argument("--out", default=str(PROCESSED_DIR),
                        help="output directory (default data/processed)")
    parser.add_argument("--members-dir", default=str(PROCESSED_DIR),
                        help="directory with members_{age}.parquet (default data/processed)")
    parser.add_argument("--master-dir", default=str(PROCESSED_DIR),
                        help="directory with master_bills_{age}.parquet, for coverage shares only")
    parser.add_argument("--legacy-edges", default=str(PROCESSED_DIR / "cosponsorship_edges.parquet"),
                        help="old edge file (copy of korean-assembly-bills proposers)")
    parser.add_argument("--report-dir", default=str(REPO / "logs" / "structure_reports"))
    parser.add_argument("--allow-missing", action="store_true",
                        help="build from the raw files that exist instead of stopping")
    args = parser.parse_args()

    ages = parse_ages(args.ages)
    if ages != ALL_AGES:
        # Each output is one all-assembly table, so a subset run replaces it
        print(f"WARNING: --ages {args.ages}: the tables written to {args.out} will hold"
              f" these assemblies only")
    out = Path(args.out)
    report_dir = Path(args.report_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    if args.command in ("subcommittee", "all"):
        build_subcommittee(ages, out, Path(args.master_dir), args.allow_missing)
    if args.command in ("alternatives", "all"):
        build_alternatives(ages, out, args.allow_missing, report_dir)
    if args.command in ("edges", "all"):
        build_edges(ages, out, Path(args.members_dir), Path(args.legacy_edges),
                    args.allow_missing, report_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
