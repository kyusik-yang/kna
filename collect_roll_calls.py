"""
Roll Call Collection - Member-level voting records (20-22대)
============================================================
Collects individual legislator votes for each bill that went to plenary vote.

Usage:
    python3 collect_roll_calls.py             # Collect all 20-22대
    python3 collect_roll_calls.py --age 22    # Single assembly

Each bill's answer is appended to data/raw/fetchlog/nojepdqqaweusdfbi_{age}.jsonl,
so an interrupted run resumes, and a rerun of a finished run re-pulls nothing.
Pass --refresh to re-pull every bill (the API back-fills votes of members who
were missing at first, so an ongoing assembly should be re-pulled in full).

After collection the member-level counts of every bill are compared with the
official tallies (ncocpgfiaoituanbr) and the result is written to
data/raw/roll_calls_{age}_tally_check.csv.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

import kna_api
from kna_api import fetch_many, rows_from_log, write_parquet_atomic

# ── Configuration ──────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FETCHLOG_DIR = RAW_DIR / "fetchlog"

ENDPOINT = "nojepdqqaweusdfbi"  # 의원별 표결 (member-level roll calls)
VOTE_ENDPOINT = "ncocpgfiaoituanbr"  # 의안별 표결 (bill-level tallies)

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "roll_calls.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

RENAME = {
    "HG_NM": "member_name",
    "HJ_NM": "member_hanja",
    "POLY_NM": "party",
    "ORIG_NM": "district",
    "MONA_CD": "member_id",
    "RESULT_VOTE_MOD": "vote",
    "BILL_NO": "bill_no",
    "BILL_ID": "bill_id_api",
    "VOTE_DATE": "vote_date",
    "AGE": "age_api",
    "_BILL_ID": "bill_id",
    "_AGE": "age",
}


def get_voted_bill_ids(age: int) -> list[str]:
    """Get BILL_IDs that went to plenary vote for given assembly."""
    path = RAW_DIR / f"{VOTE_ENDPOINT}_{age}.parquet"
    if not path.exists():
        log.error(f"  Vote tallies not found: {path}")
        return []
    df = pd.read_parquet(path)
    bill_ids = df["BILL_ID"].dropna().unique().tolist()
    log.info(f"  {age}대: {len(bill_ids):,} bills with plenary votes")
    return bill_ids


def tally_check(age: int, votes: pd.DataFrame) -> pd.DataFrame:
    """Compare member-level counts per bill with the official tallies."""
    tallies = pd.read_parquet(RAW_DIR / f"{VOTE_ENDPOINT}_{age}.parquet")
    # A bill can carry more than one tally row upstream; keep them all visible
    t = tallies.groupby("BILL_ID").agg(
        proc_dt=("PROC_DT", "first"),
        tally_members=("MEMBER_TCNT", "first"),
        tally_yes=("YES_TCNT", "first"),
        tally_no=("NO_TCNT", "first"),
        tally_abstain=("BLANK_TCNT", "first"),
        n_tally_rows=("BILL_ID", "size"),
    )
    for c in ["tally_members", "tally_yes", "tally_no", "tally_abstain"]:
        t[c] = pd.to_numeric(t[c], errors="coerce")
    v = votes.groupby("bill_id").agg(
        rows=("vote", "size"),
        yes=("vote", lambda s: (s == "찬성").sum()),
        no=("vote", lambda s: (s == "반대").sum()),
        abstain=("vote", lambda s: (s == "기권").sum()),
    )
    out = t.join(v, how="left").fillna({"rows": 0, "yes": 0, "no": 0, "abstain": 0})
    out["rows_short"] = out["tally_members"] - out["rows"]
    out["yna_match"] = ((out["yes"] == out["tally_yes"]) & (out["no"] == out["tally_no"])
                        & (out["abstain"] == out["tally_abstain"]))
    out.index.name = "bill_id"
    return out.reset_index()


def collect_assembly(age: int, refresh: bool = False, workers: int = 4):
    """Collect all member-level roll calls for one assembly."""
    kna_api.get_key()
    log.info(f"{'='*50}")
    log.info(f"Roll Call Collection: {age}대")
    log.info(f"{'='*50}")

    bill_ids = get_voted_bill_ids(age)
    if not bill_ids:
        return

    log_path = FETCHLOG_DIR / f"{ENDPOINT}_{age}.jsonl"
    if refresh and log_path.exists():
        log_path.rename(log_path.with_suffix(".jsonl.prev"))
    done = fetch_many(ENDPOINT, bill_ids,
                      lambda b: {"BILL_ID": b, "AGE": str(age)},
                      log_path, workers=workers, page_size=1000)
    failed = [b for b in bill_ids if done.get(b, {}).get("status") != "ok"]
    if failed:
        log.error(f"  {len(failed):,} bills failed; rerun to retry. Not writing output.")
        return

    rows = rows_from_log({b: done[b] for b in bill_ids})
    for r in rows:
        r["_AGE"] = age
    clean = pd.DataFrame(rows).rename(columns=RENAME)
    dup = clean.duplicated(subset=["bill_id", "member_id"]).sum()
    if dup:
        log.warning(f"  {dup} duplicate (bill_id, member_id) rows from the API, dropped")
        clean = clean.drop_duplicates(subset=["bill_id", "member_id"])

    outpath = RAW_DIR / f"roll_calls_{age}.parquet"
    write_parquet_atomic(clean, outpath)
    log.info(f"  Saved: {outpath.name} ({len(clean):,} rows, "
             f"{clean['bill_id'].nunique():,} bills)")

    check = tally_check(age, clean)
    check.to_csv(RAW_DIR / f"roll_calls_{age}_tally_check.csv", index=False)
    short = (check["rows_short"] > 0).sum()
    mism = (~check["yna_match"]).sum()
    log.info(f"  Tally check: {len(check):,} bills, {short:,} with fewer member rows "
             f"than MEMBER_TCNT, {mism:,} with Y/N/A different from the tally")


def main():
    parser = argparse.ArgumentParser(description="Collect member-level roll calls")
    parser.add_argument("--age", type=int, help="Single assembly (default: all 20-22)")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-pull every bill instead of resuming")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true",
                        help="Kept for compatibility; collection always resumes")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for age in ([args.age] if args.age else [20, 21, 22]):
        collect_assembly(age, args.refresh, args.workers)


if __name__ == "__main__":
    main()
