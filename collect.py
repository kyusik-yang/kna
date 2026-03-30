"""
kna - Data Collection Pipeline
=================================================
열린국회정보 Open API 8개를 수집하여 법안 생애주기 마스터 DB 구축.

Usage:
    python collect.py phase1              # Batch collection (5 APIs)
    python collect.py phase2              # Per-bill detail (3 APIs, ~2.2h)
    python collect.py phase2 --resume     # Resume interrupted Phase 2
    python collect.py validate            # Validate collected data
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
API_KEY = os.environ.get("ASSEMBLY_API_KEY", "")
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

RATE_LIMIT_SEC = 0.5   # 0.5s between requests
PAGE_SIZE = 1000        # rows per page
DEFAULT_AGE = 22        # 22대 국회

HEADERS = {"User-Agent": "Mozilla/5.0"}

# Batch APIs (Phase 1): endpoint -> (display name, AGE param name)
BATCH_APIS = {
    "nzmimeepazxkubdpn": ("의원발의법률안", "AGE"),
    "BILLRCP":           ("접수목록",       "AGE"),
    "BILLJUDGE":         ("심사정보",       "AGE"),
    "ncocpgfiaoituanbr": ("의안별표결현황", "AGE"),
    "nzpltgfqabtcpsmai": ("처리의안",       "AGE"),
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

# ── HTTP Session ───────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    """Create session with retry logic."""
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ── Core API Fetcher ───────────────────────────────────────────────────────

def fetch_endpoint(session: requests.Session, endpoint: str,
                   params: dict, page_size: int = PAGE_SIZE) -> list[dict]:
    """
    Fetch all pages from an endpoint. Returns list of row dicts.

    The API response structure:
    {
      "ENDPOINT": [
        {"head": [{"list_total_count": N}, {"RESULT": {"CODE": "...", "MESSAGE": "..."}}]},
        {"row": [...]}
      ]
    }
    """
    all_rows = []
    page = 1
    total_count = None

    while True:
        query = {
            "KEY": API_KEY,
            "Type": "json",
            "pIndex": page,
            "pSize": page_size,
            **params,
        }
        url = f"{BASE_URL}/{endpoint}"

        try:
            resp = session.get(url, params=query, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error(f"  Request failed: {endpoint} page {page}: {e}")
            # For batch APIs, break on persistent failure
            break

        try:
            data = resp.json()
        except json.JSONDecodeError:
            log.error(f"  JSON decode failed: {endpoint} page {page}")
            break

        # Find the data key - it matches the endpoint name
        data_key = None
        for key in data:
            if key.upper() == endpoint.upper() or key == endpoint:
                data_key = key
                break

        if data_key is None:
            # Try to find any key that has the expected structure
            for key in data:
                if isinstance(data[key], list) and len(data[key]) > 0:
                    data_key = key
                    break

        if data_key is None:
            log.error(f"  No data key found in response: {list(data.keys())}")
            break

        entries = data[data_key]

        # Extract head info (total count)
        head = None
        rows = None
        for entry in entries:
            if isinstance(entry, dict):
                if "head" in entry:
                    head = entry["head"]
                if "row" in entry:
                    rows = entry["row"]

        if head and total_count is None:
            for h in head:
                if isinstance(h, dict) and "list_total_count" in h:
                    total_count = h["list_total_count"]
                    break

        # Check for API error
        if head:
            for h in head:
                if isinstance(h, dict) and "RESULT" in h:
                    result = h["RESULT"]
                    if result.get("CODE") not in ("INFO-000", "INFO-200"):
                        log.warning(f"  API result: {result.get('CODE')} - {result.get('MESSAGE')}")
                        if result.get("CODE") == "INFO-200":
                            # No data
                            return all_rows
                        if "ERROR" in result.get("CODE", ""):
                            return all_rows

        if rows is None:
            # Possibly last page or no data
            if page == 1:
                log.warning(f"  No rows returned for {endpoint} page 1")
            break

        all_rows.extend(rows)

        if page == 1 and total_count:
            total_pages = (total_count + page_size - 1) // page_size
            log.info(f"  Total: {total_count:,} rows, {total_pages} pages")

        # Check if we've got all rows
        if total_count and len(all_rows) >= total_count:
            break

        # Check if this was the last page (fewer rows than page_size)
        if len(rows) < page_size:
            break

        page += 1
        time.sleep(RATE_LIMIT_SEC)

    return all_rows


def fetch_single_bill(session: requests.Session, endpoint: str,
                      bill_id: str) -> list[dict]:
    """Fetch data for a single BILL_ID. Returns list of row dicts (may be multiple for 1:N APIs)."""
    params = {"BILL_ID": bill_id}
    # For single bill queries, use small page size
    rows = fetch_endpoint(session, endpoint, params, page_size=100)
    return rows


# ── Phase 1: Batch Collection ─────────────────────────────────────────────

def run_phase1(age: int = DEFAULT_AGE):
    """Collect all batch APIs for given assembly age."""
    log.info(f"{'='*60}")
    log.info(f"Phase 1: Batch Collection (AGE={age})")
    log.info(f"{'='*60}")

    session = make_session()
    results = {}

    for endpoint, (name, age_param) in BATCH_APIS.items():
        log.info(f"\n[{name}] Fetching {endpoint}...")
        start = time.time()

        params = {age_param: str(age)}
        rows = fetch_endpoint(session, endpoint, params)

        elapsed = time.time() - start
        log.info(f"  Fetched {len(rows):,} rows in {elapsed:.1f}s")

        if rows:
            df = pd.DataFrame(rows)
            outpath = RAW_DIR / f"{endpoint}_{age}.parquet"
            df.to_parquet(outpath, index=False)
            log.info(f"  Saved: {outpath.name} ({len(df):,} rows, {len(df.columns)} cols)")
            results[endpoint] = {
                "name": name,
                "rows": len(df),
                "columns": list(df.columns),
            }
        else:
            log.warning(f"  No data collected for {endpoint}")
            results[endpoint] = {"name": name, "rows": 0, "columns": []}

        time.sleep(RATE_LIMIT_SEC)

    # Save collection metadata
    meta = {
        "phase": 1,
        "age": age,
        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoints": results,
    }
    meta_path = RAW_DIR / f"phase1_meta_{age}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    log.info(f"\n{'='*60}")
    log.info("Phase 1 Summary:")
    for ep, info in results.items():
        log.info(f"  {info['name']:12s}: {info['rows']:>10,} rows")
    log.info(f"{'='*60}")

    return results


# ── Phase 2: Per-Bill Detail Collection ────────────────────────────────────

def get_unique_bill_ids(age: int = DEFAULT_AGE) -> list[str]:
    """Extract unique BILL_IDs scoped to the target assembly.

    Phase 1 discovery showed:
      - nzmimeepazxkubdpn: correctly filtered to target assembly (AGE param works)
      - BILLRCP, BILLJUDGE: AGE param does NOT filter; returns all assemblies.
        Must filter via ERACO column (e.g., '제22대').
      - ncocpgfiaoituanbr, nzpltgfqabtcpsmai: correctly filtered (AGE param works)

    Strategy (Option B - 22대 전체):
      1. All IDs from nzmimeepazxkubdpn (member-proposed, already 22대 only)
      2. BILLRCP filtered to ERACO == '제{age}대' for 정부+위원장 bills
      3. IDs from votes and processed (already 22대 only)
    """
    bill_ids = set()
    era_label = f"제{age}대"

    # APIs where AGE param works correctly - take all IDs
    correct_age_apis = ["nzmimeepazxkubdpn", "ncocpgfiaoituanbr", "nzpltgfqabtcpsmai"]
    for endpoint in correct_age_apis:
        path = RAW_DIR / f"{endpoint}_{age}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            ids = df["BILL_ID"].dropna().unique()
            bill_ids.update(ids)
            log.info(f"  {endpoint}: {len(ids):,} BILL_IDs (AGE={age} native)")

    # APIs where AGE param doesn't filter - must use ERACO
    eraco_apis = ["BILLRCP", "BILLJUDGE"]
    for endpoint in eraco_apis:
        path = RAW_DIR / f"{endpoint}_{age}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            if "ERACO" in df.columns:
                filtered = df[df["ERACO"] == era_label]
                ids = filtered["BILL_ID"].dropna().unique()
                new_ids = set(ids) - bill_ids
                bill_ids.update(ids)
                log.info(f"  {endpoint}: {len(ids):,} BILL_IDs (ERACO={era_label}), "
                         f"{len(new_ids):,} new")
            else:
                log.warning(f"  {endpoint}: no ERACO column, skipping")

    result = sorted(bill_ids)
    log.info(f"  Total unique BILL_IDs for {age}대: {len(result):,}")
    return result


def load_checkpoint(age: int) -> dict:
    """Load Phase 2 checkpoint (which bill_ids are already done)."""
    ckpt_path = RAW_DIR / f"phase2_checkpoint_{age}.json"
    if ckpt_path.exists():
        with open(ckpt_path, "r") as f:
            return json.load(f)
    return {"completed": {}, "failed": []}


def save_checkpoint(age: int, checkpoint: dict):
    """Save Phase 2 checkpoint."""
    ckpt_path = RAW_DIR / f"phase2_checkpoint_{age}.json"
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False)


def run_phase2(age: int = DEFAULT_AGE, resume: bool = False):
    """Collect per-bill detail APIs for all BILL_IDs."""
    log.info(f"{'='*60}")
    log.info(f"Phase 2: Per-Bill Detail Collection (AGE={age})")
    log.info(f"{'='*60}")

    bill_ids = get_unique_bill_ids(age)
    if not bill_ids:
        log.error("No BILL_IDs found. Run Phase 1 first.")
        return

    # Load checkpoint
    checkpoint = load_checkpoint(age) if resume else {"completed": {}, "failed": []}
    done_ids = set(checkpoint["completed"].keys())

    # On resume, load existing partial data into accumulators
    accum = {ep: [] for ep in PERBILL_APIS}
    if resume:
        for ep in PERBILL_APIS:
            partial = RAW_DIR / f"{ep}_{age}_partial.parquet"
            if partial.exists():
                df = pd.read_parquet(partial)
                accum[ep] = df.to_dict("records")
                log.info(f"  Loaded {len(accum[ep]):,} existing rows for {ep}")

    if done_ids:
        log.info(f"  Resuming: {len(done_ids):,} completed, "
                 f"{len(bill_ids) - len(done_ids):,} remaining")

    remaining = [bid for bid in bill_ids if bid not in done_ids]
    total = len(remaining)

    if total == 0:
        log.info("  All BILL_IDs already collected!")
        return

    log.info(f"  Collecting {total:,} bills across {len(PERBILL_APIS)} endpoints")
    estimated_time = total * RATE_LIMIT_SEC * len(PERBILL_APIS)
    log.info(f"  Estimated time: {estimated_time/3600:.1f} hours")

    session = make_session()
    start_time = time.time()
    save_interval = 200
    error_count = 0

    for i, bill_id in enumerate(remaining):
        if (i + 1) % 100 == 0 or i == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate / 60 if rate > 0 else 0
            log.info(f"  Progress: {i+1:,}/{total:,} ({(i+1)/total*100:.1f}%) "
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
                log.error(f"  Exception fetching {endpoint} for {bill_id}: {e}")
                bill_results[endpoint] = -1
                error_count += 1
            time.sleep(RATE_LIMIT_SEC)

        checkpoint["completed"][bill_id] = bill_results

        # Periodic save
        if (i + 1) % save_interval == 0:
            save_checkpoint(age, checkpoint)
            for ep in PERBILL_APIS:
                if accum[ep]:
                    df = pd.DataFrame(accum[ep])
                    outpath = RAW_DIR / f"{ep}_{age}_partial.parquet"
                    df.to_parquet(outpath, index=False)
            log.info(f"  Checkpoint saved at {i+1:,} bills "
                     f"(errors so far: {error_count})")

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
        else:
            log.warning(f"  No data for {ep}")

    elapsed = time.time() - start_time
    log.info(f"\nPhase 2 completed in {elapsed/3600:.1f} hours")
    log.info(f"  Bills processed: {len(checkpoint['completed']):,}")
    log.info(f"  Errors: {error_count}")


# ── Validation ─────────────────────────────────────────────────────────────

def validate(age: int = DEFAULT_AGE):
    """Validate collected data against expected counts."""
    log.info(f"{'='*60}")
    log.info(f"Data Validation (AGE={age})")
    log.info(f"{'='*60}")

    expected = {
        "nzmimeepazxkubdpn": 16_100,
        "BILLRCP": 118_458,
        "BILLJUDGE": 35_158,
        "ncocpgfiaoituanbr": 1_286,
        "nzpltgfqabtcpsmai": 4_413,
    }

    print(f"\n{'Endpoint':<25} {'Name':<15} {'Expected':>10} {'Actual':>10} {'Status':<8}")
    print("-" * 75)

    for endpoint in list(BATCH_APIS.keys()) + list(PERBILL_APIS.keys()):
        name = BATCH_APIS.get(endpoint, (PERBILL_APIS.get(endpoint, "?"), None))
        if isinstance(name, tuple):
            name = name[0]

        path = RAW_DIR / f"{endpoint}_{age}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            actual = len(df)
            exp = expected.get(endpoint, "N/A")

            if isinstance(exp, int):
                diff_pct = abs(actual - exp) / exp * 100
                status = "OK" if diff_pct < 10 else "CHECK"
            else:
                status = "OK"
                exp = "-"

            print(f"{endpoint:<25} {name:<15} {str(exp):>10} {actual:>10,} {status:<8}")

            # Check for duplicates on BILL_ID
            id_col = None
            for col in df.columns:
                if col.upper() == "BILL_ID":
                    id_col = col
                    break
            if id_col:
                n_unique = df[id_col].nunique()
                n_null = df[id_col].isna().sum()
                if n_null > 0:
                    print(f"  {'':25} BILL_ID null: {n_null}")
                if n_unique < len(df) and endpoint not in ("BILLJUDGECONF", "BILLLWJUDGECONF"):
                    print(f"  {'':25} BILL_ID duplicates: {len(df) - n_unique}")

            # Missing values summary
            missing = df.isna().sum()
            high_missing = missing[missing > len(df) * 0.05]
            if len(high_missing) > 0:
                for col, cnt in high_missing.items():
                    print(f"  {'':25} Missing {col}: {cnt:,} ({cnt/len(df)*100:.1f}%)")
        else:
            print(f"{endpoint:<25} {name:<15} {'':>10} {'NOT FOUND':>10} {'MISSING':<8}")

    print()


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="kna Data Collector")
    parser.add_argument("command", choices=["phase1", "phase2", "validate"],
                        help="Which phase to run")
    parser.add_argument("--age", type=int, default=DEFAULT_AGE,
                        help="Assembly age (default: 22)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume Phase 2 from checkpoint")

    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "phase1":
        run_phase1(args.age)
    elif args.command == "phase2":
        run_phase2(args.age, resume=args.resume)
    elif args.command == "validate":
        validate(args.age)


if __name__ == "__main__":
    main()
