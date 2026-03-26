"""
Link external datasets to the bill lifecycle master DB.
=========================================================
1. assembly-bills: bill proposal texts (발의 이유)
2. kr-hearings-data: committee meeting speeches
3. ID mapping table across all projects

Usage:
    python3 link_external.py texts      # Link bill texts
    python3 link_external.py speeches   # Link committee speeches
    python3 link_external.py idmap      # Build ID mapping table
    python3 link_external.py all        # All of the above
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

PROCESSED = Path(__file__).parent / "data" / "processed"
AB_PATH = Path("/Users/kyusik/Desktop/kyusik-github/korean-assembly-bills/data")
KR_PATH = Path("/Users/kyusik/Desktop/kyusik-github/kr-hearings-data/data")
CW_PATH = Path("/Users/kyusik/Desktop/kyusik-claude/projects/committee-witnesses-korea/data/processed")


def link_bill_texts():
    """Link assembly-bills proposal texts to master DB."""
    print("="*60)
    print("1. Linking bill proposal texts (assembly-bills)")
    print("="*60)

    texts = pd.read_parquet(AB_PATH / "bill_texts.parquet")
    proposers = pd.read_parquet(AB_PATH / "proposers.parquet")

    print(f"  Bill texts: {len(texts):,} bills, {texts['propose_reason'].notna().sum():,} with text")
    print(f"  Proposers: {len(proposers):,} records (individual co-sponsors)")

    # Save linked versions
    outpath = PROCESSED / "bill_texts_linked.parquet"
    texts.to_parquet(outpath, index=False)
    print(f"  Saved: {outpath.name}")

    # Proposer edge list (for cosponsorship network)
    edges = proposers[["BILL_ID", "PPSR_NM", "NASS_CD", "PPSR_POLY_NM", "REP_DIV"]].copy()
    edges.columns = ["bill_id", "member_name", "member_id", "party", "role"]
    outpath2 = PROCESSED / "cosponsorship_edges.parquet"
    edges.to_parquet(outpath2, index=False)
    print(f"  Saved: {outpath2.name} ({len(edges):,} edges)")

    # Summary
    for age in [20, 21, 22]:
        master = pd.read_parquet(PROCESSED / f"master_bills_{age}.parquet")
        matched = master["bill_id"].isin(texts["BILL_ID"]).sum()
        print(f"  {age}대: {matched:,}/{len(master):,} bills have proposal text ({matched/len(master)*100:.1f}%)")


def link_speeches():
    """Link kr-hearings-data committee speeches to bill lifecycle."""
    print("\n" + "="*60)
    print("2. Linking committee speeches (kr-hearings-data)")
    print("="*60)

    speeches_file = KR_PATH / "all_speeches_16_22_v9.parquet"
    if not speeches_file.exists():
        print(f"  NOT FOUND: {speeches_file}")
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

    # Build meeting-level summary for linking
    meeting_summary = speeches.groupby(["meeting_id", "term", "committee", "hearing_type", "date"]).agg(
        n_speeches=("speaker", "count"),
        n_legislators=("naas_cd", "nunique"),
        parties=("party", lambda x: ",".join(sorted(x.dropna().unique()))),
    ).reset_index()

    outpath = PROCESSED / "hearing_meetings_summary.parquet"
    meeting_summary.to_parquet(outpath, index=False)
    print(f"\n  Saved: {outpath.name} ({len(meeting_summary):,} meetings)")

    # Link potential: committee meetings in bill lifecycle ↔ hearing meetings
    for age in [20, 21, 22]:
        cm = pd.read_parquet(PROCESSED / f"committee_meetings_{age}.parquet")
        cm_dates = set()
        for col in cm.columns:
            if "dt" in col.lower() or "date" in col.lower():
                cm_dates = set(cm[col].dropna().unique())
                break
        hearing_dates = set(meeting_summary[meeting_summary["term"] == age]["date"].dropna().unique())
        overlap = len(cm_dates & hearing_dates)
        print(f"  {age}대 date overlap: {overlap} dates (cm={len(cm_dates)}, hearing={len(hearing_dates)})")


def build_id_mapping():
    """Build unified legislator ID mapping across all projects."""
    print("\n" + "="*60)
    print("3. Building unified legislator ID mapping")
    print("="*60)

    sources = {}

    # Source 1: DW-NOMINATE (member_id = MONA_CD)
    dw = pd.read_csv(PROCESSED / "dw_ideal_points_20_22.csv")
    dw_ids = dw[["member_id", "member_name", "party", "term"]].drop_duplicates()
    dw_ids = dw_ids.rename(columns={"member_id": "mona_cd"})
    sources["dw_nominate"] = dw_ids
    print(f"  DW-NOMINATE: {dw_ids['mona_cd'].nunique()} unique legislators")

    # Source 2: Roll calls (member_id)
    rc = pd.read_parquet(PROCESSED / "roll_calls_all.parquet",
                         columns=["member_id", "member_name", "party", "term"])
    rc_ids = rc.dropna(subset=["member_id"]).drop_duplicates(subset=["member_id", "term"])
    rc_ids = rc_ids.rename(columns={"member_id": "mona_cd"})
    sources["roll_calls"] = rc_ids
    print(f"  Roll calls: {rc_ids['mona_cd'].nunique()} unique legislators")

    # Source 3: Bill masters (rst_mona_cd)
    master_ids = []
    for age in [17, 18, 19, 20, 21, 22]:
        df = pd.read_parquet(PROCESSED / f"master_bills_{age}.parquet")
        if "rst_mona_cd" in df.columns:
            sub = df[["rst_mona_cd", "rst_proposer", "age"]].dropna(subset=["rst_mona_cd"])
            sub = sub.rename(columns={"rst_mona_cd": "mona_cd", "rst_proposer": "member_name", "age": "term"})
            master_ids.append(sub.drop_duplicates(subset=["mona_cd", "term"]))
    if master_ids:
        bill_ids = pd.concat(master_ids, ignore_index=True)
        sources["bill_masters"] = bill_ids
        print(f"  Bill masters: {bill_ids['mona_cd'].nunique()} unique legislators")

    # Source 4: mp_metadata (naas_cd)
    if CW_PATH.exists():
        mp = pd.read_csv(CW_PATH / "mp_metadata_16_22.csv")
        mp_ids = mp[["naas_cd", "name", "party", "term"]].rename(
            columns={"naas_cd": "mona_cd", "name": "member_name"})
        sources["mp_metadata"] = mp_ids
        print(f"  mp_metadata: {mp_ids['mona_cd'].nunique()} unique legislators")

    # Source 5: assembly-bills proposers (NASS_CD)
    if AB_PATH.exists():
        prop = pd.read_parquet(AB_PATH / "proposers.parquet")
        prop_ids = prop[["NASS_CD", "PPSR_NM", "PPSR_POLY_NM"]].dropna(subset=["NASS_CD"])
        prop_ids = prop_ids.rename(columns={"NASS_CD": "mona_cd", "PPSR_NM": "member_name",
                                            "PPSR_POLY_NM": "party"})
        prop_ids = prop_ids.drop_duplicates(subset=["mona_cd"])
        sources["assembly_bills"] = prop_ids
        print(f"  assembly-bills: {prop_ids['mona_cd'].nunique()} unique legislators")

    # Combine into unified mapping
    all_ids = pd.concat(
        [df[["mona_cd", "member_name"]].drop_duplicates("mona_cd") for df in sources.values()],
        ignore_index=True
    ).drop_duplicates("mona_cd")

    # Add source flags
    for src_name, src_df in sources.items():
        src_codes = set(src_df["mona_cd"].unique())
        all_ids[f"in_{src_name}"] = all_ids["mona_cd"].isin(src_codes)

    print(f"\n  Unified mapping: {len(all_ids):,} unique legislators")

    # Coverage matrix
    print(f"\n  Cross-source coverage:")
    for src in sources:
        n = all_ids[f"in_{src}"].sum()
        print(f"    {src:20s}: {n:>5,} ({n/len(all_ids)*100:.1f}%)")

    # Save
    outpath = PROCESSED / "legislator_id_mapping.parquet"
    all_ids.to_parquet(outpath, index=False)
    print(f"\n  Saved: {outpath.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["texts", "speeches", "idmap", "all"])
    args = parser.parse_args()

    PROCESSED.mkdir(parents=True, exist_ok=True)

    if args.command in ("texts", "all"):
        link_bill_texts()
    if args.command in ("speeches", "all"):
        link_speeches()
    if args.command in ("idmap", "all"):
        build_id_mapping()

    print("\nDone.")


if __name__ == "__main__":
    main()
