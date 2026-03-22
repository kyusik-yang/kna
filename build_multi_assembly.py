"""
Korean Bill Lifecycle - Multi-Assembly Builder
===============================================
Step 0: Build lite master tables for 17-21대 from existing data.
Step 1A: Collect remaining batch APIs (votes + processed) for 17-21대.
Step 3: Test 17대 BILL_ID format compatibility with per-bill APIs.

Usage:
    python3 build_multi_assembly.py lite          # Step 0: build from existing data
    python3 build_multi_assembly.py batch         # Step 1A: collect votes + processed
    python3 build_multi_assembly.py test17        # Step 3: test 17대 ID formats
    python3 build_multi_assembly.py phase2 --age 21  # Phase 2 for specific assembly
    python3 build_multi_assembly.py phase2 --age 21 --resume  # Resume
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

# Reuse collect.py infrastructure
from collect import (
    make_session, fetch_endpoint, fetch_single_bill,
    load_checkpoint, save_checkpoint,
    BASE_URL, API_KEY, HEADERS, RATE_LIMIT_SEC,
    PERBILL_APIS, RAW_DIR, PROCESSED_DIR,
)

BP_PATH = Path("/Users/kyusik/Desktop/kyusik-claude/projects/"
               "na-legislative-events-korea/data/raw/bill_proposals.json")

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


# ── Data Loaders ───────────────────────────────────────────────────────────

def load_bill_proposals() -> pd.DataFrame:
    """Load bill_proposals.json from na-legislative-events-korea."""
    log.info(f"Loading bill_proposals.json ({BP_PATH.stat().st_size / 1e6:.0f} MB)...")
    with open(BP_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df.columns = df.columns.str.lower()
    # AGE is int64 in this file
    df["age"] = df["age"].astype(int)
    log.info(f"  Loaded {len(df):,} records, ages: {sorted(df['age'].unique())}")
    return df


def load_billrcp() -> pd.DataFrame:
    path = RAW_DIR / "BILLRCP_22.parquet"
    df = pd.read_parquet(path)
    df.columns = df.columns.str.lower()
    return df


def load_billjudge() -> pd.DataFrame:
    path = RAW_DIR / "BILLJUDGE_22.parquet"
    df = pd.read_parquet(path)
    df.columns = df.columns.str.lower()
    return df


# ── Step 0: Lite Master ───────────────────────────────────────────────────

def build_lite_master(age: int, bp: pd.DataFrame,
                      rcp: pd.DataFrame, judge: pd.DataFrame) -> pd.DataFrame:
    """Build lite master for one assembly from existing data only."""
    era = f"제{age}대"
    log.info(f"\n{'='*50}")
    log.info(f"Building lite master for {age}대")
    log.info(f"{'='*50}")

    # 1. Start from bill_proposals (member-proposed, rich fields)
    bp_age = bp[bp["age"] == age].copy()
    log.info(f"  bill_proposals: {len(bp_age):,} member-proposed bills")

    master = bp_age.rename(columns={
        "bill_name": "bill_nm",
        "committee": "committee_nm",
        "propose_dt": "ppsl_dt",
        "proc_result": "proc_rslt",
        "proposer": "proposer_text",
        "detail_link": "link_url",
    }).copy()
    master["bill_kind"] = "법률안"
    master["ppsr_kind"] = "의원"

    # 2. Add non-member bills from BILLRCP
    rcp_age = rcp[rcp["eraco"] == era].copy()
    existing_ids = set(master["bill_id"])
    new_bills = rcp_age[~rcp_age["bill_id"].isin(existing_ids)].copy()
    log.info(f"  BILLRCP: {len(rcp_age):,} total, {len(new_bills):,} non-member bills to add")

    if not new_bills.empty:
        new_bills = new_bills.rename(columns={
            "bill_nm": "bill_nm",
            "ppsl_dt": "ppsl_dt",
            "proc_rslt": "proc_rslt",
        })
        for col in master.columns:
            if col not in new_bills.columns:
                new_bills[col] = pd.NA
        for col in new_bills.columns:
            if col not in master.columns:
                master[col] = pd.NA
        master = pd.concat([master, new_bills[master.columns]], ignore_index=True)

    log.info(f"  Combined: {len(master):,} bills")

    # 3. Merge BILLJUDGE (committee review)
    judge_age = judge[judge["eraco"] == era].copy()
    if not judge_age.empty:
        judge_cols = ["bill_id", "jrcmit_nm", "bdg_cmmt_dt",
                      "jrcmit_prsnt_dt", "jrcmit_proc_dt", "jrcmit_proc_rslt"]
        judge_subset = judge_age[[c for c in judge_cols if c in judge_age.columns]]
        master = master.merge(judge_subset, on="bill_id", how="left",
                              suffixes=("", "_judge"))
        log.info(f"  BILLJUDGE: {len(judge_age):,} matched")

    # 4. Set age
    master["age"] = age

    # 5. Derive status and flags
    master["status"] = master["proc_rslt"].fillna("임기만료폐기" if age < 22 else "계류중")
    passed_kw = ["원안가결", "수정가결", "대안반영폐기"]
    master["passed"] = master["proc_rslt"].isin(passed_kw).astype(int)
    master["enacted"] = master["proc_rslt"].isin(["원안가결", "수정가결"]).astype(int)

    # Parse dates
    for col in master.columns:
        if col.endswith("_dt"):
            master[col] = master[col].replace({"0": pd.NaT, "": pd.NaT})
            master[col] = pd.to_datetime(master[col], errors="coerce")

    if "ppsl_dt" in master.columns and "proc_dt" in master.columns:
        master["days_to_proc"] = (master["proc_dt"] - master["ppsl_dt"]).dt.days

    # Summary
    n_passed = master["passed"].sum()
    n_enacted = master["enacted"].sum()
    log.info(f"  Status: passed={n_passed:,} ({n_passed/len(master)*100:.1f}%), "
             f"enacted={n_enacted:,} ({n_enacted/len(master)*100:.1f}%)")

    return master


def run_step0():
    """Build lite master tables for all assemblies 17-21."""
    bp = load_bill_proposals()
    rcp = load_billrcp()
    judge = load_billjudge()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    summary = []
    for age in [17, 18, 19, 20, 21]:
        master = build_lite_master(age, bp, rcp, judge)

        # Save
        out = PROCESSED_DIR / f"master_bills_{age}_lite.parquet"
        master.to_parquet(out, index=False)
        log.info(f"  Saved: {out.name} ({len(master):,} rows, {len(master.columns)} cols)")

        summary.append({
            "age": age,
            "total": len(master),
            "member": (master["ppsr_kind"] == "의원").sum(),
            "govt": (master["ppsr_kind"] == "정부").sum() if "ppsr_kind" in master.columns else 0,
            "passed": master["passed"].sum(),
            "enacted": master["enacted"].sum(),
        })

    # Summary table
    log.info(f"\n{'='*60}")
    log.info("Step 0 Complete - Lite Master Tables")
    log.info(f"{'='*60}")
    log.info(f"{'Age':>5} {'Total':>8} {'Member':>8} {'Govt':>6} {'Passed':>8} {'Enacted':>8} {'Pass%':>7}")
    log.info("-" * 60)
    for s in summary:
        pct = s["passed"] / s["total"] * 100 if s["total"] > 0 else 0
        log.info(f"{s['age']:>5} {s['total']:>8,} {s['member']:>8,} {s['govt']:>6,} "
                 f"{s['passed']:>8,} {s['enacted']:>8,} {pct:>6.1f}%")


# ── Step 1A: Batch Collection ─────────────────────────────────────────────

BATCH_APIS_FILTERED = {
    "ncocpgfiaoituanbr": ("의안별표결현황", "AGE"),
    "nzpltgfqabtcpsmai": ("처리의안", "AGE"),
}


def run_batch(ages: list[int] = None):
    """Collect votes + processed bills for 17-21대."""
    if ages is None:
        ages = [17, 18, 19, 20, 21]

    session = make_session()

    for age in ages:
        log.info(f"\n{'='*50}")
        log.info(f"Batch collection for {age}대")
        log.info(f"{'='*50}")

        for endpoint, (name, age_param) in BATCH_APIS_FILTERED.items():
            outpath = RAW_DIR / f"{endpoint}_{age}.parquet"
            if outpath.exists():
                existing = pd.read_parquet(outpath)
                log.info(f"  [{name}] Already exists: {len(existing):,} rows, skipping")
                continue

            log.info(f"  [{name}] Fetching {endpoint} AGE={age}...")
            params = {age_param: str(age)}
            rows = fetch_endpoint(session, endpoint, params)
            log.info(f"  Fetched {len(rows):,} rows")

            if rows:
                df = pd.DataFrame(rows)
                df.to_parquet(outpath, index=False)
                log.info(f"  Saved: {outpath.name}")

            time.sleep(RATE_LIMIT_SEC)


# ── Step 3: Test 17대 BILL_ID Formats ─────────────────────────────────────

def run_test17():
    """Test if non-PRC BILL_IDs work with per-bill APIs."""
    log.info("Testing 17대 BILL_ID format compatibility...")

    rcp = load_billrcp()
    rcp_17 = rcp[rcp["eraco"] == "제17대"]

    # Get sample IDs of each format
    prc_ids = rcp_17[rcp_17["bill_id"].str.startswith("PRC_")]["bill_id"].head(3).tolist()
    arc_ids = rcp_17[rcp_17["bill_id"].str.startswith("ARC_")]["bill_id"].head(3).tolist()
    num_ids = rcp_17[~rcp_17["bill_id"].str.startswith(("PRC_", "ARC_"))]["bill_id"].head(3).tolist()

    session = make_session()
    results = []

    for label, ids in [("PRC_", prc_ids), ("ARC_", arc_ids), ("Numeric", num_ids)]:
        for bid in ids:
            for endpoint in ["BILLINFODETAIL", "BILLJUDGECONF"]:
                rows = fetch_single_bill(session, endpoint, bid)
                results.append({
                    "format": label,
                    "bill_id": bid[:20] + "...",
                    "endpoint": endpoint,
                    "rows": len(rows),
                    "success": len(rows) > 0,
                })
                time.sleep(RATE_LIMIT_SEC)

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


# ── Phase 2 for specific assembly ─────────────────────────────────────────

def get_bill_ids_for_age(age: int) -> list[str]:
    """Get all unique BILL_IDs for a given assembly."""
    bill_ids = set()
    era = f"제{age}대"

    # From bill_proposals (member-proposed)
    bp = load_bill_proposals()
    bp_age = bp[bp["age"] == age]
    bill_ids.update(bp_age["bill_id"].dropna().unique())
    log.info(f"  bill_proposals: {len(bp_age):,} IDs")

    # From BILLRCP (all types)
    rcp = load_billrcp()
    rcp_age = rcp[rcp["eraco"] == era]
    new = set(rcp_age["bill_id"].dropna().unique()) - bill_ids
    bill_ids.update(rcp_age["bill_id"].dropna().unique())
    log.info(f"  BILLRCP: {len(rcp_age):,} IDs ({len(new):,} new)")

    # From BILLJUDGE
    judge = load_billjudge()
    judge_age = judge[judge["eraco"] == era]
    new2 = set(judge_age["bill_id"].dropna().unique()) - bill_ids
    bill_ids.update(judge_age["bill_id"].dropna().unique())
    log.info(f"  BILLJUDGE: {len(judge_age):,} IDs ({len(new2):,} new)")

    result = sorted(bill_ids)
    log.info(f"  Total unique: {len(result):,}")
    return result


def run_phase2(age: int, resume: bool = False):
    """Run Phase 2 per-bill collection for a specific assembly."""
    log.info(f"{'='*60}")
    log.info(f"Phase 2: Per-Bill Detail Collection (AGE={age})")
    log.info(f"{'='*60}")

    bill_ids = get_bill_ids_for_age(age)
    if not bill_ids:
        log.error("No BILL_IDs found.")
        return

    checkpoint = load_checkpoint(age) if resume else {"completed": {}, "failed": []}
    done_ids = set(checkpoint["completed"].keys())

    # On resume, load partial data
    accum = {ep: [] for ep in PERBILL_APIS}
    if resume:
        for ep in PERBILL_APIS:
            partial = RAW_DIR / f"{ep}_{age}_partial.parquet"
            if partial.exists():
                df = pd.read_parquet(partial)
                accum[ep] = df.to_dict("records")
                log.info(f"  Loaded {len(accum[ep]):,} existing rows for {ep}")

    remaining = [bid for bid in bill_ids if bid not in done_ids]
    total = len(remaining)

    if done_ids:
        log.info(f"  Resuming: {len(done_ids):,} done, {total:,} remaining")

    if total == 0:
        log.info("  All done!")
        return

    estimated_hours = total * RATE_LIMIT_SEC * len(PERBILL_APIS) / 3600
    log.info(f"  Collecting {total:,} bills, est. {estimated_hours:.1f} hours")

    session = make_session()
    start_time = time.time()
    error_count = 0

    for i, bill_id in enumerate(remaining):
        if (i + 1) % 100 == 0 or i == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate / 60 if rate > 0 else 0
            log.info(f"  [{age}대] {i+1:,}/{total:,} ({(i+1)/total*100:.1f}%) "
                     f"| {rate:.1f} bills/s | ETA: {eta:.0f} min")

        bill_results = {}
        for endpoint, name in PERBILL_APIS.items():
            try:
                rows = fetch_single_bill(session, endpoint, bill_id)
                if rows:
                    for row in rows:
                        row["_BILL_ID"] = bill_id
                    accum[endpoint].extend(rows)
                bill_results[endpoint] = len(rows)
            except Exception as e:
                log.error(f"  Exception {endpoint} for {bill_id}: {e}")
                bill_results[endpoint] = -1
                error_count += 1
            time.sleep(RATE_LIMIT_SEC)

        checkpoint["completed"][bill_id] = bill_results

        if (i + 1) % 200 == 0:
            save_checkpoint(age, checkpoint)
            for ep in PERBILL_APIS:
                if accum[ep]:
                    pd.DataFrame(accum[ep]).to_parquet(
                        RAW_DIR / f"{ep}_{age}_partial.parquet", index=False)
            log.info(f"  Checkpoint at {i+1:,} (errors: {error_count})")

    # Final save
    save_checkpoint(age, checkpoint)
    for ep, name in PERBILL_APIS.items():
        if accum[ep]:
            df = pd.DataFrame(accum[ep])
            outpath = RAW_DIR / f"{ep}_{age}.parquet"
            df.to_parquet(outpath, index=False)
            log.info(f"  Saved: {outpath.name} ({len(df):,} rows)")
            partial = RAW_DIR / f"{ep}_{age}_partial.parquet"
            if partial.exists():
                partial.unlink()

    elapsed = time.time() - start_time
    log.info(f"\n[{age}대] Phase 2 done in {elapsed/3600:.1f}h, errors: {error_count}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-Assembly Builder")
    parser.add_argument("command", choices=["lite", "batch", "test17", "phase2"])
    parser.add_argument("--age", type=int, help="Assembly age for phase2")
    parser.add_argument("--resume", action="store_true")

    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "lite":
        run_step0()
    elif args.command == "batch":
        run_batch()
    elif args.command == "test17":
        run_test17()
    elif args.command == "phase2":
        if not args.age:
            parser.error("--age required for phase2")
        run_phase2(args.age, args.resume)


if __name__ == "__main__":
    main()
