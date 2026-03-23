"""
Roll Call Collection - Member-level voting records (20-22대)
============================================================
Collects individual legislator votes for each bill that went to plenary vote.

Usage:
    python3 collect_roll_calls.py             # Collect all 20-22대
    python3 collect_roll_calls.py --age 22    # Single assembly
    python3 collect_roll_calls.py --resume    # Resume from checkpoint
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Configuration ──────────────────────────────────────────────────────────

BASE_URL = "https://open.assembly.go.kr/portal/openapi"
API_KEY = os.environ["ASSEMBLY_API_KEY"]  # Set via: export ASSEMBLY_API_KEY=your_key
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

ENDPOINT = "nojepdqqaweusdfbi"  # 의원별 표결 (member-level roll calls)
VOTE_ENDPOINT = "ncocpgfiaoituanbr"  # 의안별 표결 (bill-level tallies)

RATE_LIMIT_SEC = 0.3
HEADERS = {"User-Agent": "Mozilla/5.0"}

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


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(total=5, backoff_factor=1.0,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_member_votes(session: requests.Session,
                       bill_id: str, age: int) -> list[dict]:
    """Fetch all member votes for a single bill."""
    all_rows = []
    page = 1

    while True:
        params = {
            "KEY": API_KEY,
            "Type": "json",
            "pIndex": page,
            "pSize": 300,  # Max ~300 members per bill
            "BILL_ID": bill_id,
            "AGE": str(age),
        }
        try:
            resp = session.get(f"{BASE_URL}/{ENDPOINT}",
                               params=params, timeout=30)
            data = resp.json()
        except Exception as e:
            log.error(f"  Request failed for {bill_id}: {e}")
            break

        # Parse response
        body = data.get(ENDPOINT)
        if body is None:
            # Check for error
            result = data.get("RESULT", {})
            if result.get("CODE") == "ERROR-300":
                break
            break

        rows = None
        total = None
        for entry in body:
            if isinstance(entry, dict):
                if "head" in entry:
                    for h in entry["head"]:
                        if "list_total_count" in h:
                            total = h["list_total_count"]
                        if "RESULT" in h and h["RESULT"]["CODE"] != "INFO-000":
                            return all_rows
                if "row" in entry:
                    rows = entry["row"]

        if rows is None:
            break

        all_rows.extend(rows)

        if total and len(all_rows) >= total:
            break
        if len(rows) < 300:
            break

        page += 1
        time.sleep(RATE_LIMIT_SEC)

    return all_rows


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


def load_checkpoint(age: int) -> dict:
    path = RAW_DIR / f"rollcall_checkpoint_{age}.json"
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {"completed": [], "failed": []}


def save_checkpoint(age: int, ckpt: dict):
    path = RAW_DIR / f"rollcall_checkpoint_{age}.json"
    with open(path, "w") as f:
        json.dump(ckpt, f)


def collect_assembly(age: int, resume: bool = False):
    """Collect all member-level roll calls for one assembly."""
    log.info(f"{'='*50}")
    log.info(f"Roll Call Collection: {age}대")
    log.info(f"{'='*50}")

    bill_ids = get_voted_bill_ids(age)
    if not bill_ids:
        return

    ckpt = load_checkpoint(age) if resume else {"completed": [], "failed": []}
    done = set(ckpt["completed"])

    if resume and done:
        log.info(f"  Resuming: {len(done):,} done, {len(bill_ids) - len(done):,} remaining")

    remaining = [b for b in bill_ids if b not in done]
    total = len(remaining)

    if total == 0:
        log.info("  All done!")
        return

    log.info(f"  Collecting {total:,} bills x ~300 members")
    log.info(f"  Estimated time: {total * RATE_LIMIT_SEC / 60:.1f} min")

    session = make_session()
    all_rows = []
    start = time.time()
    errors = 0

    for i, bill_id in enumerate(remaining):
        if (i + 1) % 100 == 0 or i == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate / 60 if rate > 0 else 0
            log.info(f"  [{age}대] {i+1:,}/{total:,} ({(i+1)/total*100:.1f}%) "
                     f"| {rate:.1f} bills/s | ETA: {eta:.0f} min "
                     f"| {len(all_rows):,} votes collected")

        try:
            rows = fetch_member_votes(session, bill_id, age)
            if rows:
                for r in rows:
                    r["_BILL_ID"] = bill_id
                    r["_AGE"] = age
                all_rows.extend(rows)
            ckpt["completed"].append(bill_id)
        except Exception as e:
            log.error(f"  Exception for {bill_id}: {e}")
            ckpt["failed"].append(bill_id)
            errors += 1

        time.sleep(RATE_LIMIT_SEC)

        # Periodic save
        if (i + 1) % 500 == 0:
            save_checkpoint(age, ckpt)
            if all_rows:
                pd.DataFrame(all_rows).to_parquet(
                    RAW_DIR / f"roll_calls_{age}_partial.parquet", index=False)
            log.info(f"  Checkpoint at {i+1:,} (errors: {errors})")

    # Final save
    save_checkpoint(age, ckpt)

    if all_rows:
        df = pd.DataFrame(all_rows)

        # Clean columns
        clean = df.rename(columns={
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
        })

        outpath = RAW_DIR / f"roll_calls_{age}.parquet"
        clean.to_parquet(outpath, index=False)
        log.info(f"  Saved: {outpath.name} ({len(clean):,} rows)")

        # Remove partial
        partial = RAW_DIR / f"roll_calls_{age}_partial.parquet"
        if partial.exists():
            partial.unlink()

    elapsed = time.time() - start
    log.info(f"\n[{age}대] Done in {elapsed/60:.1f} min | "
             f"{len(all_rows):,} votes | {errors} errors")


def main():
    parser = argparse.ArgumentParser(description="Collect member-level roll calls")
    parser.add_argument("--age", type=int, help="Single assembly (default: all 20-22)")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.age:
        collect_assembly(args.age, args.resume)
    else:
        for age in [20, 21, 22]:
            collect_assembly(age, args.resume)


if __name__ == "__main__":
    main()
