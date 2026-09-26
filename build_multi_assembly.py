"""
kna - Multi-Assembly Builder (DEPRECATED)
===============================================
Superseded. integrate.py now builds the master of every assembly (17th-22nd)
from data/raw, and collect.py collects the raw files per assembly (Phase 1
with the ERACO filter, Phase 2 per bill). The former steps read BILLRCP_22 as
an all-era file and bill_proposals.json from another project; both inputs are
gone, so the steps below only point to their replacements.

    lite    -> python3 integrate.py --ages 17-22
    batch   -> python3 collect.py phase1 --ages 17-21
    phase2  -> python3 collect.py phase2 --age 21

The one remaining step tests which 17th-assembly BILL_ID formats the per-bill
APIs accept (needs ASSEMBLY_API_KEY, 18 calls):

    python3 build_multi_assembly.py test17
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

import kna_api

RAW_DIR = Path(__file__).parent / "data" / "raw"

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "multi_assembly.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

SUPERSEDED = {
    "lite": "python3 integrate.py --ages 17-22 (builds the full master of every assembly)",
    "batch": "python3 collect.py phase1 --ages 17-21",
    "phase2": "python3 collect.py phase2 --age N",
}


# ── Data Loaders ───────────────────────────────────────────────────────────

def load_billrcp(age: int) -> pd.DataFrame:
    path = RAW_DIR / f"BILLRCP_{age}.parquet"
    df = pd.read_parquet(path)
    df.columns = df.columns.str.lower()
    return df


# ── Step 3: Test 17대 BILL_ID Formats ─────────────────────────────────────

def run_test17():
    """Test if non-PRC BILL_IDs work with per-bill APIs."""
    log.info("Testing 17대 BILL_ID format compatibility...")
    kna_api.get_key()

    rcp = load_billrcp(17)
    rcp_17 = rcp[rcp["eraco"] == "제17대"]

    # Get sample IDs of each format
    prc_ids = rcp_17[rcp_17["bill_id"].str.startswith("PRC_")]["bill_id"].head(3).tolist()
    arc_ids = rcp_17[rcp_17["bill_id"].str.startswith("ARC_")]["bill_id"].head(3).tolist()
    num_ids = rcp_17[~rcp_17["bill_id"].str.startswith(("PRC_", "ARC_", "GOV_"))]["bill_id"].head(3).tolist()

    results = []

    for label, ids in [("PRC_", prc_ids), ("ARC_", arc_ids), ("Numeric", num_ids)]:
        for bid in ids:
            for endpoint in ["BILLINFODETAIL", "BILLJUDGECONF"]:
                try:
                    n = len(kna_api.fetch(endpoint, {"BILL_ID": bid}, page_size=100))
                except kna_api.ApiError as e:
                    log.error(f"  {endpoint} {bid}: {e.code} {e.message}")
                    n = -1
                results.append({
                    "format": label,
                    "bill_id": bid[:20] + "...",
                    "endpoint": endpoint,
                    "rows": n,
                    "success": n > 0,
                })

    log.info(f"\n{'Format':<10} {'Endpoint':<18} {'Success':>8} {'Rows':>6}")
    log.info("-" * 45)
    for r in results:
        log.info(f"{r['format']:<10} {r['endpoint']:<18} {str(r['success']):>8} {r['rows']:>6}")

    # Summary
    for fmt in ["PRC_", "ARC_", "Numeric"]:
        fmt_results = [r for r in results if r["format"] == fmt]
        success = sum(1 for r in fmt_results if r["success"])
        total = len(fmt_results)
        log.info(f"\n{fmt}: {success}/{total} successful")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-Assembly Builder (deprecated)")
    parser.add_argument("command", choices=["lite", "batch", "test17", "phase2"])
    parser.add_argument("--age", type=int, help="Assembly age for phase2")
    parser.add_argument("--resume", action="store_true")

    args = parser.parse_args()

    if args.command in SUPERSEDED:
        sys.exit(f"build_multi_assembly.py {args.command} is deprecated. "
                 f"Use: {SUPERSEDED[args.command]}")
    run_test17()


if __name__ == "__main__":
    main()
