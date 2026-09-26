"""
kna - Structural data collection (subcommittee stages, alternatives, proposers)
==============================================================================
Raw collection for three official sources that the bill master lacks.

Usage:
    python3 collect_structure.py subcommittee --ages 17-22
    python3 collect_structure.py alternatives --ages 17-22
    python3 collect_structure.py proposers --ages 17-22
    python3 collect_structure.py all --ages 17-22

subcommittee  TVBPMCONFINFO (소위 심사정보, opened 2026-07-07), bulk per AGE.
              -> data/raw/TVBPMCONFINFO_{age}.parquet
alternatives  TVBPMBILL11 with BILL_ID_REF = a committee alternative (대안)
              returns the bills absorbed into it (대안반영폐기). One call per
              alternative. -> data/raw/alt_absorption_{age}.parquet
proposers     BILLINFOPPSR (proposer list with role and party at proposal),
              one call per bill, only where the master's code lists cannot be
              trusted: code count differs from the proposer text, the list was
              truncated at 100 in the old edge file, or the bill is newer than
              the old edge file. -> data/raw/BILLINFOPPSR_{age}.parquet

Per-call answers are logged to data/raw/fetchlog/*.jsonl, so reruns resume.
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

import kna_api
from kna_api import fetch, fetch_many, rows_from_log, write_parquet_atomic

REPO = Path(__file__).parent
RAW_DIR = REPO / "data" / "raw"
PROCESSED_DIR = REPO / "data" / "processed"
FETCHLOG_DIR = RAW_DIR / "fetchlog"

LOG_DIR = REPO / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "structure.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def parse_ages(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def collect_subcommittee(age: int):
    rows = fetch("TVBPMCONFINFO", {"AGE": str(age)})
    if not rows:
        log.info(f"  TVBPMCONFINFO {age}: no data")
        return
    df = pd.DataFrame(rows)
    write_parquet_atomic(df, RAW_DIR / f"TVBPMCONFINFO_{age}.parquet")
    log.info(f"  TVBPMCONFINFO_{age}: {len(df):,} rows, {df['BILL_ID'].nunique():,} bills")


def alternative_ids(age: int) -> list[str]:
    """Committee alternatives of one assembly (bill name ends with '(대안)').

    BILLRCP lists a vetoed alternative under its GOV_ reconsideration record,
    so the original PRC_ record is taken from the processed-bill list too.
    """
    ids: set[str] = set()
    for name, col in [("BILLRCP", "BILL_NM"), ("nzpltgfqabtcpsmai", "BILL_NAME")]:
        p = RAW_DIR / f"{name}_{age}.parquet"
        if p.exists():
            d = pd.read_parquet(p)
            is_alt = d[col].fillna("").str.strip().str.endswith("(대안)")
            ids |= set(d.loc[is_alt, "BILL_ID"].dropna())
    # A vetoed alternative still awaiting its re-vote is in neither list under
    # its own id; its original record shares the GOV_ record's suffix.
    ids |= {"PRC_" + i[4:] for i in ids if i.startswith("GOV_")}
    return sorted(i for i in ids if not i.startswith("GOV_"))


def collect_alternatives(age: int, workers: int):
    alts = alternative_ids(age)
    log.info(f"  {age}대: {len(alts):,} committee alternatives")
    done = fetch_many("TVBPMBILL11", alts,
                      lambda b: {"AGE": str(age), "BILL_ID_REF": b},
                      FETCHLOG_DIR / f"TVBPMBILL11_{age}.jsonl",
                      workers=workers, page_size=1000)
    rows = rows_from_log({k: done[k] for k in alts if k in done}, tag_col="ALT_BILL_ID")
    df = pd.DataFrame(rows)
    covered = sum(1 for k in alts if done.get(k, {}).get("status") == "ok" and done[k]["rows"])
    failed = sum(1 for k in alts if done.get(k, {}).get("status") != "ok")
    if not df.empty:
        write_parquet_atomic(df, RAW_DIR / f"alt_absorption_{age}.parquet")
    log.info(f"  alt_absorption_{age}: {len(df):,} absorbed-bill rows; "
             f"{covered:,}/{len(alts):,} alternatives returned rows, {failed} failed")


def proposer_count(text: str) -> int:
    """'홍길동의원 등 11인' -> 11, '홍길동의원 외 10인' -> 11, 'A의원 등 1인 외 165인' -> 166."""
    text = text or ""
    total = 0
    m = re.search(r"등\s*(\d+)\s*인", text)
    if m:
        total += int(m.group(1))
    m = re.search(r"외\s*(\d+)\s*인", text)
    if m:
        total += int(m.group(1)) + (0 if "등" in text else 1)
    return total


def proposer_target_ids(age: int) -> list[str]:
    d = pd.read_parquet(RAW_DIR / f"nzmimeepazxkubdpn_{age}.parquet")
    n_codes = (d["RST_MONA_CD"].fillna("").str.count(r"[0-9A-Z]{8}")
               + d["PUBL_MONA_CD"].fillna("").str.count(r"[0-9A-Z]{8}"))
    n_text = d["PROPOSER"].map(proposer_count)
    target = set(d.loc[(n_codes != n_text) | (n_codes == 0), "BILL_ID"])
    edges_path = PROCESSED_DIR / "cosponsorship_edges.parquet"
    if age >= 20 and edges_path.exists():
        e = pd.read_parquet(edges_path, columns=["bill_id"])
        per_bill = e.groupby("bill_id").size()
        target |= set(per_bill[per_bill >= 100].index) & set(d["BILL_ID"])
        target |= set(d["BILL_ID"]) - set(per_bill.index)   # newer than the old file
    return sorted(target)


def collect_proposers(age: int, workers: int):
    ids = proposer_target_ids(age)
    log.info(f"  {age}대: {len(ids):,} bills need BILLINFOPPSR")
    done = fetch_many("BILLINFOPPSR", ids, lambda b: {"BILL_ID": b},
                      FETCHLOG_DIR / f"BILLINFOPPSR_{age}.jsonl",
                      workers=workers, page_size=1000)
    rows = rows_from_log({k: done[k] for k in ids if k in done})
    df = pd.DataFrame(rows)
    if not df.empty:
        write_parquet_atomic(df, RAW_DIR / f"BILLINFOPPSR_{age}.parquet")
    failed = sum(1 for k in ids if done.get(k, {}).get("status") != "ok")
    log.info(f"  BILLINFOPPSR_{age}: {len(df):,} rows for {df['_BILL_ID'].nunique() if not df.empty else 0:,} bills, {failed} failed")


def main():
    parser = argparse.ArgumentParser(description="Collect structural bill data")
    parser.add_argument("command", choices=["subcommittee", "alternatives", "proposers", "all"])
    parser.add_argument("--ages", default="17-22")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    kna_api.get_key()
    for age in parse_ages(args.ages):
        log.info(f"=== {age}대 ===")
        if args.command in ("subcommittee", "all"):
            collect_subcommittee(age)
        if args.command in ("alternatives", "all"):
            collect_alternatives(age, args.workers)
        if args.command in ("proposers", "all"):
            collect_proposers(age, args.workers)


if __name__ == "__main__":
    main()
