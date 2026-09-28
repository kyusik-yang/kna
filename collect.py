"""
kna - Data Collection Pipeline
=================================================
열린국회정보 Open API를 수집하여 법안 생애주기 마스터 DB의 원자료(data/raw)를 만든다.

Usage:
    python collect.py phase1 --age 22           # Batch APIs for one assembly
    python collect.py phase1 --ages 17-22       # Batch APIs for several
    python collect.py phase2 --age 22           # Per-bill APIs, all bills
    python collect.py phase2 --age 18 --endpoints BILLJUDGECONF --ids-file ids.txt
    python collect.py validate --age 22         # Local raw counts vs live totals

Phase 2 resumes automatically. Each per-bill answer is appended to
data/raw/fetchlog/{ENDPOINT}_{age}.jsonl, so an interrupted run picks up where
it stopped, and failed bills are retried on the next run. The parquet for an
endpoint is rewritten only by merging: rows of the bills fetched in this run
replace their old rows, and rows of all other bills are kept.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

import kna_api
from kna_api import fetch, fetch_many, rows_from_log, total_count, write_parquet_atomic

# ── Configuration ──────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FETCHLOG_DIR = RAW_DIR / "fetchlog"

DEFAULT_AGE = 22        # 22대 국회

# Batch APIs (Phase 1): endpoint -> (display name, filter builder)
# BILLRCP and BILLJUDGE ignore AGE and return every era; ERACO filters them
# server side. ncocpgfiaoituanbr has no data before the 20th assembly.
BATCH_APIS = {
    "nzmimeepazxkubdpn": ("의원발의법률안", lambda age: {"AGE": str(age)}),
    "BILLRCP":           ("접수목록",       lambda age: {"ERACO": f"제{age}대"}),
    "BILLJUDGE":         ("심사정보",       lambda age: {"ERACO": f"제{age}대"}),
    "ncocpgfiaoituanbr": ("의안별표결현황", lambda age: {"AGE": str(age)}),
    "nzpltgfqabtcpsmai": ("처리의안",       lambda age: {"AGE": str(age)}),
}

# Per-bill APIs (Phase 2): endpoint -> display name
PERBILL_APIS = {
    "BILLINFODETAIL":  "의안상세정보",
    "BILLJUDGECONF":   "위원회회의정보",
    "BILLLWJUDGECONF": "법사위회의정보",
}

# ── Logging ────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "collect.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def parse_ages(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


# ── Phase 1: Batch Collection ─────────────────────────────────────────────

def run_phase1(age: int = DEFAULT_AGE):
    """Collect all batch APIs for given assembly age."""
    kna_api.get_key()
    log.info(f"{'='*60}")
    log.info(f"Phase 1: Batch Collection (AGE={age})")
    log.info(f"{'='*60}")

    results = {}
    for endpoint, (name, params_for) in BATCH_APIS.items():
        params = params_for(age)
        log.info(f"\n[{name}] Fetching {endpoint} {params}...")
        start = time.time()
        rows = fetch(endpoint, params)
        log.info(f"  Fetched {len(rows):,} rows in {time.time() - start:.1f}s")

        outpath = RAW_DIR / f"{endpoint}_{age}.parquet"
        if rows:
            df = pd.DataFrame(rows)
            if "BILL_ID" in df.columns and endpoint != "ncocpgfiaoituanbr":
                dup = df.duplicated().sum()
                if dup:
                    log.warning(f"  {dup} exact duplicate rows from the API, dropped")
                    df = df.drop_duplicates()
            write_parquet_atomic(df, outpath)
            log.info(f"  Saved: {outpath.name} ({len(df):,} rows, {len(df.columns)} cols)")
        else:
            log.info(f"  No data for {endpoint} {params} (INFO-200)")
        results[endpoint] = {"name": name, "params": params, "rows": len(rows),
                             "columns": list(rows[0].keys()) if rows else []}

    meta = {
        "phase": 1,
        "age": age,
        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoints": results,
    }
    with open(RAW_DIR / f"phase1_meta_{age}.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    log.info(f"\n{'='*60}")
    log.info("Phase 1 Summary:")
    for ep, info in results.items():
        log.info(f"  {info['name']:12s}: {info['rows']:>10,} rows")
    log.info(f"{'='*60}")
    return results


# ── Phase 2: Per-Bill Detail Collection ────────────────────────────────────

def get_unique_bill_ids(age: int = DEFAULT_AGE) -> list[str]:
    """All BILL_IDs of one assembly, from the Phase 1 files of that assembly."""
    bill_ids: set[str] = set()
    for endpoint in BATCH_APIS:
        path = RAW_DIR / f"{endpoint}_{age}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if "ERACO" in df.columns:
            df = df[df["ERACO"] == f"제{age}대"]
        ids = set(df["BILL_ID"].dropna().unique())
        log.info(f"  {endpoint}: {len(ids):,} BILL_IDs ({len(ids - bill_ids):,} new)")
        bill_ids |= ids
    # A vetoed bill is listed only under its GOV_ reconsideration record while
    # the re-vote is pending; its original record usually shares the suffix.
    originals = {"PRC_" + b[4:] for b in bill_ids if b.startswith("GOV_")} - bill_ids
    if originals:
        log.info(f"  {len(originals):,} original records of vetoed bills (PRC_ + GOV_ suffix)")
        bill_ids |= originals
    result = sorted(bill_ids)
    log.info(f"  Total unique BILL_IDs for {age}대: {len(result):,}")
    return result


def judiciary_bill_ids(age: int) -> list[str]:
    """Bills referred to the Legislation and Judiciary Committee (법사위)."""
    ids: set[str] = set()
    detail = RAW_DIR / f"BILLINFODETAIL_{age}.parquet"
    if detail.exists():
        d = pd.read_parquet(detail, columns=["_BILL_ID", "LAW_CMMT_DT", "LAW_PRSNT_DT", "LAW_PROC_DT"])
        has = d[["LAW_CMMT_DT", "LAW_PRSNT_DT", "LAW_PROC_DT"]].notna().any(axis=1)
        ids |= set(d.loc[has, "_BILL_ID"])
    existing = RAW_DIR / f"BILLLWJUDGECONF_{age}.parquet"
    if existing.exists():
        ids |= set(pd.read_parquet(existing, columns=["_BILL_ID"])["_BILL_ID"])
    return sorted(ids)


def merge_into_raw(endpoint: str, age: int, done: dict[str, dict]):
    """Replace the rows of every successfully fetched bill in {endpoint}_{age}.parquet."""
    outpath = RAW_DIR / f"{endpoint}_{age}.parquet"
    fetched_ok = {k for k, r in done.items() if r.get("status") == "ok"}
    new = pd.DataFrame(rows_from_log(done))
    if outpath.exists():
        old = pd.read_parquet(outpath)
        kept = old[~old["_BILL_ID"].isin(fetched_ok)]
        merged = pd.concat([kept, new], ignore_index=True) if not new.empty else kept
        log.info(f"  {endpoint}_{age}: kept {len(kept):,} rows of "
                 f"{old['_BILL_ID'].nunique():,} bills, added {len(new):,} rows of "
                 f"{new['_BILL_ID'].nunique() if not new.empty else 0:,} bills")
    else:
        merged = new
    if merged.empty:
        log.warning(f"  {endpoint}_{age}: nothing to write")
        return
    write_parquet_atomic(merged, outpath)
    log.info(f"  Saved: {outpath.name} ({len(merged):,} rows, "
             f"{merged['_BILL_ID'].nunique():,} bills)")


def run_phase2(age: int = DEFAULT_AGE, endpoints: list[str] | None = None,
               ids_file: str | None = None, workers: int = 4, refresh: bool = False):
    """Collect per-bill detail APIs and merge them into data/raw."""
    kna_api.get_key()
    log.info(f"{'='*60}")
    log.info(f"Phase 2: Per-Bill Detail Collection (AGE={age})")
    log.info(f"{'='*60}")

    if ids_file:
        bill_ids = [l.strip() for l in open(ids_file, encoding="utf-8") if l.strip()]
        log.info(f"  {len(bill_ids):,} BILL_IDs from {ids_file}")
    else:
        bill_ids = get_unique_bill_ids(age)
    if not bill_ids:
        log.error("No BILL_IDs found. Run Phase 1 first.")
        return

    for endpoint in endpoints or list(PERBILL_APIS):
        keys = bill_ids
        if endpoint == "BILLLWJUDGECONF" and not ids_file:
            # Only bills that reached the judiciary committee can have its meetings
            jud = set(judiciary_bill_ids(age))
            keys = [b for b in bill_ids if b in jud]
            log.info(f"  {endpoint}: {len(keys):,} bills referred to 법사위")
        log_path = FETCHLOG_DIR / f"{endpoint}_{age}.jsonl"
        if refresh and log_path.exists():
            # Re-fetch every bill: bills of an ongoing assembly keep changing
            log_path.rename(log_path.with_suffix(".jsonl.prev"))
        done = fetch_many(endpoint, keys, lambda b: {"BILL_ID": b}, log_path,
                          workers=workers, page_size=100)
        failed = [k for k in keys if done.get(k, {}).get("status") != "ok"]
        # Merge only the keys of this run, so an older log never re-adds stale rows
        this_run = {k: done[k] for k in keys if k in done}
        merge_into_raw(endpoint, age, this_run)
        if failed:
            log.error(f"  {endpoint}: {len(failed):,} bills failed; rerun to retry")


# ── Validation ─────────────────────────────────────────────────────────────

def validate(age: int = DEFAULT_AGE):
    """Compare local raw row counts with the live list_total_count."""
    kna_api.get_key()
    print(f"\n{'Endpoint':<20} {'Local':>10} {'Live':>10} {'Status':<8}")
    print("-" * 52)
    for endpoint, (name, params_for) in BATCH_APIS.items():
        path = RAW_DIR / f"{endpoint}_{age}.parquet"
        local = len(pd.read_parquet(path)) if path.exists() else 0
        live = total_count(endpoint, params_for(age))
        status = "OK" if local == live else "STALE" if local < live else "CHECK"
        print(f"{endpoint:<20} {local:>10,} {live:>10,} {status:<8}")

    universe = set(get_unique_bill_ids(age))
    for endpoint in PERBILL_APIS:
        path = RAW_DIR / f"{endpoint}_{age}.parquet"
        if not path.exists():
            print(f"{endpoint:<20} {'NOT FOUND':>10}")
            continue
        df = pd.read_parquet(path)
        bills = set(df["_BILL_ID"])
        print(f"{endpoint:<20} {len(df):>10,} rows, {len(bills):,} bills, "
              f"{len(universe - bills):,} universe bills without rows")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="kna Data Collector")
    parser.add_argument("command", choices=["phase1", "phase2", "validate"],
                        help="Which phase to run")
    parser.add_argument("--age", type=int, default=DEFAULT_AGE,
                        help="Assembly age (default: 22)")
    parser.add_argument("--ages", help="Several assemblies, e.g. 17-22 or 20,22")
    parser.add_argument("--endpoints", nargs="+", choices=list(PERBILL_APIS),
                        help="Phase 2 endpoints (default: all three)")
    parser.add_argument("--ids-file", help="Phase 2: fetch only these BILL_IDs")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true",
                        help="Phase 2: re-fetch every bill instead of resuming")
    parser.add_argument("--resume", action="store_true",
                        help="Kept for compatibility; Phase 2 always resumes")

    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ages = parse_ages(args.ages) if args.ages else [args.age]

    for age in ages:
        if args.command == "phase1":
            run_phase1(age)
        elif args.command == "phase2":
            run_phase2(age, args.endpoints, args.ids_file, args.workers, args.refresh)
        elif args.command == "validate":
            validate(age)


if __name__ == "__main__":
    main()
