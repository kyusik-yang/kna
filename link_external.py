"""
Link external datasets to the bill lifecycle master DB.
=========================================================
1. bill texts: 제안이유 및 주요내용 of the 17th-22nd law bills, from the
   LIKMS scrape of korean-assembly-bills and BPMBILLSUMMARY (data/raw)
2. kr-hearings-data: hearing_meetings_summary.parquet from version 10
3. ID mapping table across all projects

Cosponsorship edges are no longer copied from korean-assembly-bills. They
are built in this repository by build_structure.py.

Usage:
    python3 link_external.py texts      # Bill texts (writes reports/bill_texts_*.csv)
    python3 link_external.py speeches   # Hearing meetings summary (kr-hearings-data v10)
    python3 link_external.py idmap      # Build ID mapping table
    python3 link_external.py all        # All of the above

    --out DIR          output directory (default data/processed)
    --in-dir DIR       kna inputs: masters, roll calls, ideal points,
                       committee meetings (default data/processed)
    --members-dir DIR  members_{17..22}.parquet (default data/processed)
    --report-dir DIR   texts coverage reports (default OUT/reports)
    --allow-missing    skip a missing external source instead of stopping

External dataset locations (environment variables, defaults in brackets):
    KNA_ASSEMBLY_BILLS_DIR  [../korean-assembly-bills/data, a sibling checkout]
    KNA_HEARINGS_V10_DIR    [../kr-hearings-data/v10/build/release; a directory of
                             v10 release assets also works, see
                             build_hearings_summary.py]
    KNA_WITNESSES_DIR       [no default; the member-metadata flag is skipped
                             with --allow-missing when it is not set]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

import build_hearings_summary as bhs

PROCESSED = Path(__file__).parent / "data" / "processed"
RAW_DIR = Path(__file__).parent / "data" / "raw"
FETCHLOG_DIR = RAW_DIR / "fetchlog"
SIBLINGS = Path(__file__).resolve().parent.parent
AB_PATH = Path(os.environ.get("KNA_ASSEMBLY_BILLS_DIR", SIBLINGS / "korean-assembly-bills" / "data"))
CW_PATH = Path(os.environ.get("KNA_WITNESSES_DIR", "/nonexistent/KNA_WITNESSES_DIR-not-set"))
ASSEMBLIES = [17, 18, 19, 20, 21, 22]
MONA_RE = re.compile(r"^[0-9A-Z]{8}$")


def require(path: Path, env_name: str, allow_missing: bool) -> bool:
    """True if an external file exists; otherwise stop unless allow_missing."""
    if path.exists():
        return True
    msg = f"{path} not found. Set {env_name} to the dataset directory"
    if not allow_missing:
        raise SystemExit(f"ERROR: {msg}, or pass --allow-missing to skip it.")
    print(f"  WARNING: {msg}. Skipped (--allow-missing).")
    return False


def _text_or_null(s: pd.Series) -> pd.Series:
    """Keep texts as returned, but store an empty or whitespace-only text as null."""
    s = s.astype("object")
    return s.where(s.fillna("").astype(str).str.strip() != "", None)


def _summary_fetch_status(age: int) -> "dict[str, str] | None":
    """BILL_NO -> 'rows', 'no_rows' or 'error' from the collector's fetch log.

    The logs are git-ignored, so a fresh clone has none and the report then
    cannot tell a bill the API answered with no rows from one never queried.
    """
    path = FETCHLOG_DIR / f"BPMBILLSUMMARY_{age}.jsonl"
    if not path.exists():
        return None
    status: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue          # a half-written last line while collection runs
            if rec.get("status") != "ok":
                status.setdefault(rec["key"], "error")
            else:
                status[rec["key"]] = "rows" if rec.get("rows") else "no_rows"
    return status


def link_bill_texts(out: Path, in_dir: Path, allow_missing: bool, report_dir: Path):
    """Propose-reason texts of the 17th-22nd law bills, one row per bill.

    Two sources, the scraped one first:
      likms_scrape    korean-assembly-bills/data/bill_texts.parquet, the 제안이유
                      of 20th-22nd member law bills scraped from LIKMS. Every
                      row of it is kept with its text and scrape_status.
      BPMBILLSUMMARY  data/raw/BPMBILLSUMMARY_{age}, collected by
                      collect_structure.py summaries for the law bills without a
                      scraped text. It fills scrape rows that have no text and
                      adds a row for every other law bill with a text.
    age and bill_no come from master_bills_{age} in --in-dir. The one scrape
    row whose BILL_ID is in no master (a re-keyed bill) keeps them null.
    """
    print("=" * 60)
    print("1. Linking bill proposal texts (LIKMS scrape + BPMBILLSUMMARY)")
    print("=" * 60)

    texts_file = AB_PATH / "bill_texts.parquet"
    if not require(texts_file, "KNA_ASSEMBLY_BILLS_DIR", allow_missing):
        return
    summary_paths = {age: RAW_DIR / f"BPMBILLSUMMARY_{age}.parquet" for age in ASSEMBLIES}
    missing = [p.name for p in summary_paths.values() if not p.exists()]
    if missing:
        if not allow_missing:
            raise SystemExit(f"ERROR: missing raw input(s): {', '.join(missing)}. Run "
                             f"collect_structure.py summaries, or pass --allow-missing.")
        print(f"  WARNING: built without {', '.join(missing)} (--allow-missing)")

    scrape = pd.read_parquet(texts_file)
    scrape = scrape[["BILL_ID", "propose_reason", "scrape_status"]].copy()
    if scrape["BILL_ID"].duplicated().any():
        raise SystemExit("ERROR: the scraped texts repeat a BILL_ID")
    scrape["propose_reason"] = _text_or_null(scrape["propose_reason"])
    scrape["source"] = "likms_scrape"

    masters = pd.concat(
        [pd.read_parquet(in_dir / f"master_bills_{age}.parquet",
                         columns=["bill_id", "bill_no", "bill_kind", "ppsr_kind", "bill_nm"]).assign(age=age)
         for age in ASSEMBLIES], ignore_index=True)
    laws = masters[masters["bill_kind"] == "법률안"]

    # API texts, matched on BILL_ID: an answer lists every record that shares
    # the BILL_NO, GOV_ reconsideration records included
    api_frames = []
    for age, p in summary_paths.items():
        if not p.exists():
            continue
        raw = pd.read_parquet(p, columns=["BILL_ID", "BILL_NO", "SUMMARY"])
        raw = raw.merge(laws.loc[laws["age"] == age, ["bill_id", "bill_no"]],
                        left_on=["BILL_ID", "BILL_NO"], right_on=["bill_id", "bill_no"])
        api_frames.append(raw.assign(text=_text_or_null(raw["SUMMARY"]))[["bill_id", "text"]])
    api = pd.concat(api_frames, ignore_index=True) if api_frames else pd.DataFrame(columns=["bill_id", "text"])
    api_n_texts = api.dropna(subset=["text"]).groupby("bill_id")["text"].nunique()
    conflicts = api_n_texts[api_n_texts > 1]
    if len(conflicts):
        print(f"  NOTE: {len(conflicts)} bills have two or more different API texts; the first is kept")
    api_text = api.dropna(subset=["text"]).drop_duplicates("bill_id").set_index("bill_id")["text"]

    fill = scrape["propose_reason"].isna() & scrape["BILL_ID"].isin(api_text.index)
    scrape.loc[fill, "propose_reason"] = scrape.loc[fill, "BILL_ID"].map(api_text)
    scrape.loc[fill, "source"] = "BPMBILLSUMMARY"
    add = api_text[~api_text.index.isin(scrape["BILL_ID"])]
    added = pd.DataFrame({"BILL_ID": add.index, "propose_reason": add.values,
                          "scrape_status": None, "source": "BPMBILLSUMMARY"})
    texts = pd.concat([scrape, added], ignore_index=True)

    key = masters.drop_duplicates("bill_id").set_index("bill_id")
    texts["age"] = texts["BILL_ID"].map(key["age"]).astype("Int64")
    texts["bill_no"] = texts["BILL_ID"].map(key["bill_no"])
    texts = (texts.sort_values(["age", "bill_no", "BILL_ID"], na_position="last", kind="mergesort")
             [["BILL_ID", "propose_reason", "scrape_status", "age", "bill_no", "source"]]
             .reset_index(drop=True))
    print(f"  Scraped rows: {len(scrape):,}, of which {int(fill.sum()):,} without a scraped "
          f"text filled from BPMBILLSUMMARY")
    print(f"  Rows added from BPMBILLSUMMARY: {len(added):,}")
    print(f"  Rows not in any master: {int(texts['age'].isna().sum())}")

    outpath = out / "bill_texts_linked.parquet"
    texts.to_parquet(outpath, index=False)
    print(f"  Saved: {outpath.name} ({len(texts):,} rows, "
          f"{texts['propose_reason'].notna().sum():,} with text)")

    # Coverage of law bills, by assembly and proposer kind
    has_text = set(texts.loc[texts["propose_reason"].notna(), "BILL_ID"])
    scraped = set(texts.loc[texts["source"] == "likms_scrape", "BILL_ID"]) & has_text
    lw = laws.assign(text=laws["bill_id"].isin(has_text), scraped=laws["bill_id"].isin(scraped))
    lw["api"] = lw["text"] & ~lw["scraped"]
    cov = (lw.groupby(["age", "ppsr_kind"])
           .agg(law_bills=("bill_id", "size"), with_text=("text", "sum"),
                likms_scrape=("scraped", "sum"), bpmbillsummary=("api", "sum"))
           .reset_index())
    tot = (lw.groupby("age").agg(law_bills=("bill_id", "size"), with_text=("text", "sum"),
                                 likms_scrape=("scraped", "sum"), bpmbillsummary=("api", "sum"))
           .reset_index().assign(ppsr_kind="all"))
    cov = pd.concat([cov, tot], ignore_index=True).sort_values(["age", "ppsr_kind"], kind="mergesort")
    cov["share_with_text"] = (cov["with_text"] / cov["law_bills"]).round(4)
    print(cov.to_string(index=False))

    # Law bills without a text, with the reason
    status = {age: _summary_fetch_status(age) for age in ASSEMBLIES}
    api_ids: set = set()
    for age, p in summary_paths.items():
        if p.exists():
            api_ids |= set(pd.read_parquet(p, columns=["BILL_ID"])["BILL_ID"])
    no_text = lw[~lw["text"]].copy()

    def reason(r) -> str:
        if r["bill_id"] in api_ids:
            return "api_text_empty"
        if not summary_paths[r["age"]].exists():
            return "raw_file_missing"
        st = status.get(r["age"])
        if st is None:
            return "no_api_row"
        return {"rows": "api_no_row_for_bill_id", "no_rows": "api_no_rows",
                "error": "api_error"}.get(st.get(r["bill_no"]), "not_queried")

    no_text["reason"] = no_text.apply(reason, axis=1) if len(no_text) else pd.Series(dtype=str)
    no_text = no_text[["age", "bill_id", "bill_no", "ppsr_kind", "bill_nm", "reason"]]
    print(f"  Law bills without a text: {len(no_text):,}")
    if len(no_text):
        print(no_text.groupby(["age", "reason"]).size().to_string())

    report_dir.mkdir(parents=True, exist_ok=True)
    cov.to_csv(report_dir / "bill_texts_coverage.csv", index=False)
    no_text.to_csv(report_dir / "bill_texts_missing.csv", index=False)
    print(f"  Reports: {report_dir / 'bill_texts_coverage.csv'}, {report_dir / 'bill_texts_missing.csv'}")


def link_speeches(out: Path, in_dir: Path, allow_missing: bool):
    """Hearing meetings summary from kr-hearings-data version 10.

    The same table as build_hearings_summary.py --source v10.
    """
    print("\n" + "="*60)
    print("2. Hearing meetings summary (kr-hearings-data v10)")
    print("="*60)

    if not require(bhs.V10_DIR, "KNA_HEARINGS_V10_DIR", allow_missing):
        return
    meetings, turns, info = bhs.load_v10(bhs.V10_DIR)
    print(f"  v10 source: {info}")
    meeting_summary = bhs.summarize_v10(meetings, turns)
    del turns

    for term, sub in meeting_summary.groupby("term"):
        print(f"  {term}대: {len(sub):,} meetings, {sub['n_speeches'].sum():,} turns")

    outpath = out / "hearing_meetings_summary.parquet"
    meeting_summary[bhs.V10_COLUMNS].to_parquet(outpath, index=False)
    print(f"\n  Saved: {outpath.name} ({len(meeting_summary):,} meetings)")

    # Link potential: committee meetings in bill lifecycle ↔ hearing meetings
    for age in [20, 21, 22]:
        cm = pd.read_parquet(in_dir / f"committee_meetings_{age}.parquet")
        # Meeting date column, upper- or lowercase depending on the file vintage;
        # both sides compared as YYYY-MM-DD strings
        conf_col = next(c for c in cm.columns if c.lower() == "jrcmit_conf_dt")
        cm_dates = set(pd.to_datetime(cm[conf_col], errors="coerce").dropna().dt.strftime("%Y-%m-%d"))
        hearing_dates = set(pd.to_datetime(meeting_summary.loc[meeting_summary["term"] == age, "date"],
                                           errors="coerce").dropna().dt.strftime("%Y-%m-%d"))
        overlap = len(cm_dates & hearing_dates)
        print(f"  {age}대 date overlap: {overlap} dates (cm={len(cm_dates)}, hearing={len(hearing_dates)})")


def build_id_mapping(out: Path, in_dir: Path, members_dir: Path, allow_missing: bool):
    """Build unified legislator ID mapping across all projects.

    members_{17..22} define the universe of legislators. The other sources
    only set coverage flags; an ID a source holds outside the universe is
    reported, never added, so composite or stray codes cannot enter the map.

    Columns: mona_cd, member_name, terms, then one in_{source} flag per
    source (ideal_points, roll_calls, bill_masters, mp_metadata,
    assembly_bills). A flag is NA when its source was skipped.

    in_dw_nominate is a deprecated alias of in_ideal_points, kept for one
    release (0.7.0) so code written against the old file keeps working. The
    old name repeated the retracted DW-NOMINATE label. The flag marks
    membership in ideal_points_bridged.csv. Read in_ideal_points instead,
    since in_dw_nominate will be removed in the next release.
    """
    print("\n" + "="*60)
    print("3. Building unified legislator ID mapping")
    print("="*60)

    # Authority: members_{17..22}
    mem = pd.concat(
        [pd.read_parquet(members_dir / f"members_{age}.parquet",
                         columns=["mona_cd", "member_name"]).assign(term=age)
         for age in ASSEMBLIES],
        ignore_index=True)
    bad = mem.loc[~mem["mona_cd"].astype(str).str.match(MONA_RE), "mona_cd"]
    if len(bad):
        raise SystemExit(f"ERROR: members files hold malformed mona_cd: {bad.unique()[:10].tolist()}")
    all_ids = (mem.sort_values("term")
               .groupby("mona_cd", as_index=False)
               .agg(member_name=("member_name", "last"),
                    first_term=("term", "min"),
                    terms=("term", lambda s: ",".join(str(t) for t in sorted(set(s))))))
    print(f"  members_17-22: {len(all_ids):,} unique legislators")

    sources: dict[str, "set | None"] = {}

    # Source 1: ideal points (member_id = MONA_CD)
    ip = pd.read_csv(in_dir / "ideal_points_bridged.csv", usecols=["member_id"])
    sources["ideal_points"] = set(ip["member_id"].dropna())

    # Source 2: Roll calls (member_id)
    rc = pd.read_parquet(in_dir / "roll_calls_all.parquet", columns=["member_id"])
    sources["roll_calls"] = set(rc["member_id"].dropna())

    # Source 3: Bill masters (rst_mona_cd; joint leads are comma-joined)
    codes: set = set()
    for age in ASSEMBLIES:
        df = pd.read_parquet(in_dir / f"master_bills_{age}.parquet", columns=["rst_mona_cd"])
        for s in df["rst_mona_cd"].dropna():
            codes.update(c.strip() for c in s.split(",") if c.strip())
    sources["bill_masters"] = codes

    # Source 4: mp_metadata (naas_cd)
    mp_file = CW_PATH / "mp_metadata_16_22.csv"
    sources["mp_metadata"] = (set(pd.read_csv(mp_file, usecols=["naas_cd"])["naas_cd"].dropna())
                              if require(mp_file, "KNA_WITNESSES_DIR", allow_missing) else None)

    # Source 5: assembly-bills proposers (NASS_CD)
    prop_file = AB_PATH / "proposers.parquet"
    sources["assembly_bills"] = (set(pd.read_parquet(prop_file, columns=["NASS_CD"])["NASS_CD"].dropna())
                                 if require(prop_file, "KNA_ASSEMBLY_BILLS_DIR", allow_missing) else None)

    # Add source flags (NA when the source was skipped)
    universe = set(all_ids["mona_cd"])
    print(f"\n  {'source':20s} {'ids':>6} {'in map':>7} {'outside':>8} {'malformed':>10}")
    for src_name, src_codes in sources.items():
        col = f"in_{src_name}"
        if src_codes is None:
            all_ids[col] = pd.Series(pd.NA, index=all_ids.index, dtype="boolean")
            print(f"  {src_name:20s} {'skipped':>6}")
            continue
        all_ids[col] = all_ids["mona_cd"].isin(src_codes)
        outside = src_codes - universe
        malformed = [c for c in outside if not MONA_RE.match(str(c))]
        print(f"  {src_name:20s} {len(src_codes):>6,} {len(src_codes & universe):>7,} "
              f"{len(outside):>8,} {len(malformed):>10,}")

    # Deprecated alias of in_ideal_points, kept for one release (see docstring)
    all_ids.insert(all_ids.columns.get_loc("in_ideal_points") + 1,
                   "in_dw_nominate", all_ids["in_ideal_points"])

    print(f"\n  Unified mapping: {len(all_ids):,} unique legislators")

    # Coverage matrix
    print(f"\n  Cross-source coverage:")
    for src in sources:
        if sources[src] is None:
            print(f"    {src:20s}: skipped (flag is NA)")
            continue
        n = all_ids[f"in_{src}"].sum()
        print(f"    {src:20s}: {n:>5,} ({n/len(all_ids)*100:.1f}%)")

    all_ids = (all_ids.sort_values(["first_term", "member_name", "mona_cd"])
               .drop(columns="first_term").reset_index(drop=True))

    # Save
    outpath = out / "legislator_id_mapping.parquet"
    all_ids.to_parquet(outpath, index=False)
    print(f"\n  Saved: {outpath}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["texts", "speeches", "idmap", "all"])
    parser.add_argument("--out", default=str(PROCESSED))
    parser.add_argument("--in-dir", default=str(PROCESSED))
    parser.add_argument("--members-dir", default=str(PROCESSED))
    parser.add_argument("--report-dir", default=None,
                        help="texts coverage reports (default OUT/reports)")
    parser.add_argument("--allow-missing", action="store_true",
                        help="skip a missing external source instead of stopping")
    args = parser.parse_args()

    out, in_dir = Path(args.out), Path(args.in_dir)
    out.mkdir(parents=True, exist_ok=True)

    if args.command in ("texts", "all"):
        report_dir = Path(args.report_dir) if args.report_dir else out / "reports"
        link_bill_texts(out, in_dir, args.allow_missing, report_dir)
    if args.command in ("speeches", "all"):
        link_speeches(out, in_dir, args.allow_missing)
    if args.command in ("idmap", "all"):
        build_id_mapping(out, in_dir, Path(args.members_dir), args.allow_missing)

    print("\nDone.")


if __name__ == "__main__":
    main()
