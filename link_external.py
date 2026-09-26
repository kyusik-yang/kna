"""
Link external datasets to the bill lifecycle master DB.
=========================================================
1. assembly-bills: bill proposal texts (발의 이유)
2. kr-hearings-data: committee meeting speeches
3. ID mapping table across all projects

Cosponsorship edges are no longer copied from korean-assembly-bills. They
are built in this repository by build_structure.py.

Usage:
    python3 link_external.py texts      # Link bill texts
    python3 link_external.py speeches   # Link committee speeches
    python3 link_external.py idmap      # Build ID mapping table
    python3 link_external.py all        # All of the above

    --out DIR          output directory (default data/processed)
    --in-dir DIR       kna inputs: masters, roll calls, ideal points,
                       committee meetings (default data/processed)
    --members-dir DIR  members_{17..22}.parquet (default data/processed)
    --allow-missing    skip a missing external source instead of stopping

External dataset locations (environment variables, defaults in brackets):
    KNA_ASSEMBLY_BILLS_DIR  [../korean-assembly-bills/data, a sibling checkout]
    KNA_HEARINGS_DIR        [../kr-hearings-data/data, a sibling checkout]
    KNA_WITNESSES_DIR       [no default; the member-metadata flag is skipped
                             with --allow-missing when it is not set]
"""

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

from build_hearings_summary import summarize_v9_speeches

PROCESSED = Path(__file__).parent / "data" / "processed"
SIBLINGS = Path(__file__).resolve().parent.parent
AB_PATH = Path(os.environ.get("KNA_ASSEMBLY_BILLS_DIR", SIBLINGS / "korean-assembly-bills" / "data"))
KR_PATH = Path(os.environ.get("KNA_HEARINGS_DIR", SIBLINGS / "kr-hearings-data" / "data"))
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


def link_bill_texts(out: Path, in_dir: Path, allow_missing: bool):
    """Link assembly-bills proposal texts to master DB."""
    print("="*60)
    print("1. Linking bill proposal texts (assembly-bills)")
    print("="*60)

    texts_file = AB_PATH / "bill_texts.parquet"
    if not require(texts_file, "KNA_ASSEMBLY_BILLS_DIR", allow_missing):
        return
    texts = pd.read_parquet(texts_file)

    print(f"  Bill texts: {len(texts):,} bills, {texts['propose_reason'].notna().sum():,} with text")

    # Save linked versions
    outpath = out / "bill_texts_linked.parquet"
    texts.to_parquet(outpath, index=False)
    print(f"  Saved: {outpath.name}")

    # Summary
    for age in [20, 21, 22]:
        master = pd.read_parquet(in_dir / f"master_bills_{age}.parquet")
        matched = master["bill_id"].isin(texts["BILL_ID"]).sum()
        print(f"  {age}대: {matched:,}/{len(master):,} bills have proposal text ({matched/len(master)*100:.1f}%)")


def link_speeches(out: Path, in_dir: Path, allow_missing: bool):
    """Link kr-hearings-data committee speeches to bill lifecycle."""
    print("\n" + "="*60)
    print("2. Linking committee speeches (kr-hearings-data)")
    print("="*60)

    speeches_file = KR_PATH / "all_speeches_16_22_v9.parquet"
    if not require(speeches_file, "KNA_HEARINGS_DIR", allow_missing):
        return

    # Load only metadata columns to save memory
    speeches = pd.read_parquet(speeches_file,
                               columns=["meeting_id", "term", "committee", "hearing_type",
                                        "date", "speaker", "role", "naas_cd", "party"])
    print(f"  Speeches loaded: {len(speeches):,} rows")

    # Committee hearing stats by assembly
    for term in [17, 18, 19, 20, 21, 22]:
        sub = speeches[speeches["term"] == term]
        n_meetings = sub["meeting_id"].nunique()
        n_speeches = len(sub)
        types = sub["hearing_type"].value_counts().to_dict()
        print(f"  {term}대: {n_meetings:,} meetings, {n_speeches:,} speeches")

    # Build meeting-level summary for linking (same aggregation as
    # build_hearings_summary.py --source v9)
    meeting_summary = summarize_v9_speeches(speeches)

    outpath = out / "hearing_meetings_summary.parquet"
    meeting_summary.to_parquet(outpath, index=False)
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
    parser.add_argument("--allow-missing", action="store_true",
                        help="skip a missing external source instead of stopping")
    args = parser.parse_args()

    out, in_dir = Path(args.out), Path(args.in_dir)
    out.mkdir(parents=True, exist_ok=True)

    if args.command in ("texts", "all"):
        link_bill_texts(out, in_dir, args.allow_missing)
    if args.command in ("speeches", "all"):
        link_speeches(out, in_dir, args.allow_missing)
    if args.command in ("idmap", "all"):
        build_id_mapping(out, in_dir, Path(args.members_dir), args.allow_missing)

    print("\nDone.")


if __name__ == "__main__":
    main()
