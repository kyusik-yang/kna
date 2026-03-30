"""
kna - Data Integration
==================================================
Join Phase 1 (batch) + Phase 2 (per-bill) data into master database.

Usage:
    python3 integrate.py              # Build master DB
    python3 integrate.py --age 22     # Specify assembly age
"""

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

# ── Configuration ──────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DEFAULT_AGE = 22

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "logs" / "integrate.log",
                            encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── Date columns to parse ─────────────────────────────────────────────────

DATE_COLS = [
    "propose_dt", "ppsl_dt",
    "committee_dt", "bdg_cmmt_dt",
    "cmt_present_dt", "jrcmit_prsnt_dt", "jrcmit_cmmt_dt",
    "cmt_proc_dt", "jrcmit_proc_dt",
    "law_submit_dt", "law_cmmt_dt",
    "law_present_dt", "law_prsnt_dt",
    "law_proc_dt",
    "rgs_prsnt_dt", "rgs_rsln_dt",
    "gvrn_trsf_dt",
    "prom_dt",
    "proc_dt",
]


def safe_date(series: pd.Series) -> pd.Series:
    """Convert to datetime, coercing errors to NaT. Handles '0' and empty strings."""
    s = series.replace({"0": pd.NaT, "": pd.NaT, " ": pd.NaT})
    return pd.to_datetime(s, errors="coerce")


# ── Loading helpers ────────────────────────────────────────────────────────

def load_raw(filename: str) -> pd.DataFrame:
    path = RAW_DIR / filename
    if not path.exists():
        log.warning(f"  File not found: {filename}")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df.columns = df.columns.str.lower()
    return df


# ── Integration Steps ─────────────────────────────────────────────────────

def build_master(age: int = DEFAULT_AGE) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the master bills table + satellite tables.

    Returns: (master_bills, committee_meetings, judiciary_meetings)
    """
    log.info(f"{'='*60}")
    log.info(f"Phase 3: Building Master Database (AGE={age})")
    log.info(f"{'='*60}")

    era_label = f"제{age}대"

    # ── Step 1: Start with member-proposed bills (richest fields) ──────
    log.info("\n[Step 1] Load member-proposed bills (nzmimeepazxkubdpn)")
    proposed = load_raw(f"nzmimeepazxkubdpn_{age}.parquet")
    log.info(f"  {len(proposed):,} rows")

    # Standardize: this becomes the core of the master table
    master = proposed.rename(columns={
        "bill_name": "bill_nm",
        "committee": "committee_nm",
        "propose_dt": "ppsl_dt",
        "proc_result": "proc_rslt",
        "proposer": "proposer_text",
        "detail_link": "link_url",
    }).copy()
    master["bill_kind"] = "법률안"
    master["ppsr_kind"] = "의원"

    # ── Step 2: Add non-member bills from BILLRCP ──────────────────────
    log.info("\n[Step 2] Add government/chair bills from BILLRCP")
    rcp = load_raw(f"BILLRCP_{age}.parquet")
    if not rcp.empty:
        rcp_22 = rcp[rcp["eraco"] == era_label].copy()
        # Only add bills NOT already in master
        existing_ids = set(master["bill_id"])
        new_bills = rcp_22[~rcp_22["bill_id"].isin(existing_ids)].copy()
        log.info(f"  BILLRCP {age}대: {len(rcp_22):,} total, {len(new_bills):,} new")

        if not new_bills.empty:
            new_bills = new_bills.rename(columns={
                "bill_nm": "bill_nm",
                "ppsl_dt": "ppsl_dt",
                "proc_rslt": "proc_rslt",
            })
            # Align columns: add missing columns as NaN
            for col in master.columns:
                if col not in new_bills.columns:
                    new_bills[col] = pd.NA
            for col in new_bills.columns:
                if col not in master.columns:
                    master[col] = pd.NA

            master = pd.concat([master, new_bills[master.columns]], ignore_index=True)
            log.info(f"  Master now: {len(master):,} rows")

    # ── Step 3: Merge committee review info (BILLJUDGE) ────────────────
    log.info("\n[Step 3] Merge standing committee review (BILLJUDGE)")
    judge = load_raw(f"BILLJUDGE_{age}.parquet")
    if not judge.empty:
        judge_22 = judge[judge["eraco"] == era_label].copy()
        log.info(f"  BILLJUDGE {age}대: {len(judge_22):,} rows")

        # Select columns not already in master (avoid duplication)
        judge_cols = ["bill_id", "jrcmit_nm", "bdg_cmmt_dt",
                      "jrcmit_prsnt_dt", "jrcmit_proc_dt", "jrcmit_proc_rslt"]
        judge_subset = judge_22[[c for c in judge_cols if c in judge_22.columns]].copy()

        before = len(master)
        master = master.merge(judge_subset, on="bill_id", how="left", suffixes=("", "_judge"))
        log.info(f"  Merged: {before} -> {len(master)} rows "
                 f"({master['jrcmit_proc_rslt'].notna().sum():,} with committee result)")

    # ── Step 4: Merge vote tallies (ncocpgfiaoituanbr) ─────────────────
    log.info("\n[Step 4] Merge plenary vote tallies")
    votes = load_raw(f"ncocpgfiaoituanbr_{age}.parquet")
    if not votes.empty:
        log.info(f"  Votes: {len(votes):,} rows")
        vote_cols = ["bill_id", "proc_result_cd", "member_tcnt",
                     "vote_tcnt", "yes_tcnt", "no_tcnt", "blank_tcnt"]
        vote_subset = votes[[c for c in vote_cols if c in votes.columns]].copy()
        vote_subset = vote_subset.rename(columns={
            "proc_result_cd": "vote_result_cd",
            "member_tcnt": "vote_member_total",
            "vote_tcnt": "vote_total",
            "yes_tcnt": "vote_yes",
            "no_tcnt": "vote_no",
            "blank_tcnt": "vote_abstain",
        })
        master = master.merge(vote_subset, on="bill_id", how="left")
        log.info(f"  Bills with vote data: {master['vote_total'].notna().sum():,}")

    # ── Step 5: Merge processed bills info (nzpltgfqabtcpsmai) ─────────
    log.info("\n[Step 5] Merge processed bills info")
    processed = load_raw(f"nzpltgfqabtcpsmai_{age}.parquet")
    if not processed.empty:
        log.info(f"  Processed: {len(processed):,} rows")
        # This endpoint has overlapping columns; only take what's new
        proc_cols = ["bill_id", "proposer_kind"]
        proc_subset = processed[[c for c in proc_cols if c in processed.columns]].copy()
        # Fill ppsr_kind for non-member bills using proposer_kind
        proc_map = proc_subset.set_index("bill_id")["proposer_kind"].to_dict()
        mask = master["ppsr_kind"].isna()
        master.loc[mask, "ppsr_kind"] = master.loc[mask, "bill_id"].map(proc_map)
        log.info(f"  Filled ppsr_kind for {mask.sum():,} rows")

    # ── Step 6: Merge BILLINFODETAIL (full lifecycle) ──────────────────
    log.info("\n[Step 6] Merge bill detail (BILLINFODETAIL) - full lifecycle dates")
    detail = load_raw(f"BILLINFODETAIL_{age}.parquet")
    if not detail.empty:
        log.info(f"  Detail: {len(detail):,} rows")
        # These are the core lifecycle columns from BILLINFODETAIL
        detail_cols = [
            "bill_id",
            "jrcmit_cmmt_dt",   # 소관위 회부일
            "law_cmmt_dt",      # 법사위 회부일
            "law_prsnt_dt",     # 법사위 상정일
            "law_proc_dt",      # 법사위 처리일
            "law_proc_rslt",    # 법사위 처리결과
            "rgs_prsnt_dt",     # 본회의 상정일
            "rgs_rsln_dt",      # 본회의 의결일
            "rgs_conf_nm",      # 본회의 회차
            "rgs_conf_rslt",    # 본회의 결과
            "gvrn_trsf_dt",     # 정부이송일
            "prom_dt",          # 공포일
            "prom_no",          # 공포번호
            "prom_law_nm",      # 공포법률명
        ]
        # Use _bill_id if present (tagged by collector)
        if "_bill_id" in detail.columns:
            detail = detail.rename(columns={"_bill_id": "bill_id_check"})

        available_cols = [c for c in detail_cols if c in detail.columns]
        if "bill_id" not in detail.columns and "bill_id_check" in detail.columns:
            detail["bill_id"] = detail["bill_id_check"]

        # Deduplicate on bill_id (should be 1:1 but just in case)
        detail_subset = detail[available_cols].drop_duplicates(subset=["bill_id"], keep="first")

        before = len(master)
        master = master.merge(detail_subset, on="bill_id", how="left",
                              suffixes=("", "_detail"))
        log.info(f"  Merged: {len(master)} rows, "
                 f"{master['rgs_rsln_dt'].notna().sum() if 'rgs_rsln_dt' in master.columns else 0:,} "
                 f"with plenary vote date")
    else:
        log.warning("  BILLINFODETAIL not found - Phase 2 may still be running")

    # ── Step 7: Compute derived variables ──────────────────────────────
    log.info("\n[Step 7] Compute derived variables")

    # Parse date columns
    for col in master.columns:
        if col.lower() in DATE_COLS or col.endswith("_dt"):
            master[col] = safe_date(master[col])

    # Age
    master["age"] = age

    # Final status classification
    master["status"] = master["proc_rslt"].fillna("계류중")

    # Duration: proposal to final processing (days)
    if "ppsl_dt" in master.columns and "proc_dt" in master.columns:
        master["proc_dt"] = safe_date(master["proc_dt"])
        master["days_to_proc"] = (master["proc_dt"] - master["ppsl_dt"]).dt.days

    # Duration: proposal to committee referral
    if "ppsl_dt" in master.columns and "bdg_cmmt_dt" in master.columns:
        master["days_to_committee"] = (master["bdg_cmmt_dt"] - master["ppsl_dt"]).dt.days

    # Passed flag
    passed_keywords = ["원안가결", "수정가결", "대안반영폐기"]
    master["passed"] = master["proc_rslt"].isin(passed_keywords).astype(int)
    # Alternative: count only 원안가결 + 수정가결
    master["enacted"] = master["proc_rslt"].isin(["원안가결", "수정가결"]).astype(int)

    log.info(f"  Total bills: {len(master):,}")
    log.info(f"  Passed (원안/수정가결/대안반영폐기): {master['passed'].sum():,}")
    log.info(f"  Enacted (원안/수정가결): {master['enacted'].sum():,}")
    log.info(f"  계류중: {(master['status'] == '계류중').sum():,}")

    # ── Step 8: Load satellite tables ──────────────────────────────────
    log.info("\n[Step 8] Load satellite tables (committee meetings)")

    committee_meetings = load_raw(f"BILLJUDGECONF_{age}.parquet")
    if not committee_meetings.empty:
        if "_bill_id" in committee_meetings.columns:
            committee_meetings = committee_meetings.rename(
                columns={"_bill_id": "bill_id_tagged"})
        log.info(f"  Committee meetings: {len(committee_meetings):,} rows")
    else:
        log.warning("  BILLJUDGECONF not found")

    judiciary_meetings = load_raw(f"BILLLWJUDGECONF_{age}.parquet")
    if not judiciary_meetings.empty:
        if "_bill_id" in judiciary_meetings.columns:
            judiciary_meetings = judiciary_meetings.rename(
                columns={"_bill_id": "bill_id_tagged"})
        log.info(f"  Judiciary meetings: {len(judiciary_meetings):,} rows")
    else:
        log.warning("  BILLLWJUDGECONF not found")

    # ── Column ordering ────────────────────────────────────────────────
    id_cols = ["bill_id", "bill_no", "age", "bill_kind", "bill_nm"]
    proposer_cols = ["ppsr_kind", "proposer_text", "rst_proposer", "rst_mona_cd",
                     "publ_proposer", "publ_mona_cd"]
    date_cols_ordered = ["ppsl_dt", "committee_dt", "bdg_cmmt_dt",
                         "cmt_present_dt", "jrcmit_prsnt_dt", "jrcmit_cmmt_dt",
                         "cmt_proc_dt", "jrcmit_proc_dt",
                         "law_submit_dt", "law_cmmt_dt",
                         "law_present_dt", "law_prsnt_dt",
                         "law_proc_dt",
                         "rgs_prsnt_dt", "rgs_rsln_dt",
                         "gvrn_trsf_dt", "prom_dt", "proc_dt"]
    result_cols = ["jrcmit_proc_rslt", "cmt_proc_result_cd",
                   "law_proc_rslt", "law_proc_result_cd",
                   "rgs_conf_nm", "rgs_conf_rslt",
                   "proc_rslt", "status", "passed", "enacted"]
    vote_cols = ["vote_result_cd", "vote_member_total", "vote_total",
                 "vote_yes", "vote_no", "vote_abstain"]
    meta_cols = ["prom_no", "prom_law_nm", "committee_nm", "committee_id",
                 "jrcmit_nm", "link_url", "member_list",
                 "days_to_proc", "days_to_committee"]

    preferred_order = id_cols + proposer_cols + date_cols_ordered + result_cols + vote_cols + meta_cols
    existing = [c for c in preferred_order if c in master.columns]
    remaining = [c for c in master.columns if c not in existing]
    master = master[existing + remaining]

    # Drop redundant/internal columns
    drop_cols = [c for c in master.columns if c.endswith("_judge") or c.endswith("_detail")
                 or c in ["eraco", "bill_kind_cd"]]
    master = master.drop(columns=[c for c in drop_cols if c in master.columns], errors="ignore")

    return master, committee_meetings, judiciary_meetings


# ── Save ───────────────────────────────────────────────────────────────────

def save_outputs(master: pd.DataFrame,
                 committee_meetings: pd.DataFrame,
                 judiciary_meetings: pd.DataFrame,
                 age: int):
    """Save master table as Parquet + SQLite, satellite tables as Parquet."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Parquet
    pq_path = PROCESSED_DIR / f"master_bills_{age}.parquet"
    master.to_parquet(pq_path, index=False)
    log.info(f"\n  Saved: {pq_path.name} ({len(master):,} rows, {len(master.columns)} cols)")

    # SQLite
    db_path = PROCESSED_DIR / f"master_bills_{age}.sqlite"
    with sqlite3.connect(db_path) as conn:
        master.to_sql("bills", conn, if_exists="replace", index=False)
        if not committee_meetings.empty:
            committee_meetings.to_sql("committee_meetings", conn,
                                      if_exists="replace", index=False)
        if not judiciary_meetings.empty:
            judiciary_meetings.to_sql("judiciary_meetings", conn,
                                      if_exists="replace", index=False)

        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_bill_id ON bills(bill_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_bill_no ON bills(bill_no)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_ppsr_kind ON bills(ppsr_kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_committee ON bills(committee_nm)")
        if not committee_meetings.empty:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cm_bill_id ON committee_meetings(bill_id)")
        if not judiciary_meetings.empty:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jm_bill_id ON judiciary_meetings(bill_id)")

    log.info(f"  Saved: {db_path.name}")

    # Satellite tables
    if not committee_meetings.empty:
        cm_path = PROCESSED_DIR / f"committee_meetings_{age}.parquet"
        committee_meetings.to_parquet(cm_path, index=False)
        log.info(f"  Saved: {cm_path.name} ({len(committee_meetings):,} rows)")

    if not judiciary_meetings.empty:
        jm_path = PROCESSED_DIR / f"judiciary_meetings_{age}.parquet"
        judiciary_meetings.to_parquet(jm_path, index=False)
        log.info(f"  Saved: {jm_path.name} ({len(judiciary_meetings):,} rows)")


def print_summary(master: pd.DataFrame):
    """Print summary statistics of the master table."""
    log.info(f"\n{'='*60}")
    log.info("Master Database Summary")
    log.info(f"{'='*60}")
    log.info(f"  Total bills: {len(master):,}")
    log.info(f"  Columns: {len(master.columns)}")

    if "bill_kind" in master.columns:
        log.info(f"\n  Bill types:")
        for kind, cnt in master["bill_kind"].value_counts().items():
            log.info(f"    {kind}: {cnt:,}")

    if "ppsr_kind" in master.columns:
        log.info(f"\n  Proposer types:")
        for kind, cnt in master["ppsr_kind"].value_counts().items():
            log.info(f"    {kind}: {cnt:,}")

    if "status" in master.columns:
        log.info(f"\n  Processing status:")
        for status, cnt in master["status"].value_counts().head(10).items():
            log.info(f"    {status}: {cnt:,}")

    if "passed" in master.columns:
        total = len(master)
        passed = master["passed"].sum()
        log.info(f"\n  Passage rate: {passed:,}/{total:,} ({passed/total*100:.1f}%)")

    if "days_to_proc" in master.columns:
        valid = master["days_to_proc"].dropna()
        if len(valid) > 0:
            log.info(f"\n  Processing duration (days):")
            log.info(f"    Mean: {valid.mean():.0f}")
            log.info(f"    Median: {valid.median():.0f}")
            log.info(f"    Min: {valid.min():.0f}, Max: {valid.max():.0f}")

    if "committee_nm" in master.columns:
        log.info(f"\n  Top committees:")
        for comm, cnt in master["committee_nm"].value_counts().head(5).items():
            log.info(f"    {comm}: {cnt:,}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build master bill lifecycle database")
    parser.add_argument("--age", type=int, default=DEFAULT_AGE)
    args = parser.parse_args()

    start = time.time()
    master, cm, jm = build_master(args.age)
    save_outputs(master, cm, jm, args.age)
    print_summary(master)

    elapsed = time.time() - start
    log.info(f"\nIntegration completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
