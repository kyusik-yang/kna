"""
kna - Shared Open Assembly API client
=====================================
Every collector in this repository goes through fetch() so that an API error
is never mistaken for an empty result. Three behaviours of the Open Assembly
portal (open.assembly.go.kr) make this necessary:

1. Errors come back as HTTP 200 with a top-level {"RESULT": {"CODE": ...}}
   object, not inside the endpoint envelope, so HTTP-level retry never sees
   them.
2. A request without a valid KEY returns INFO-000 with the true
   list_total_count but only a 5-row sample. Collection therefore refuses to
   run without a key, and every fetch checks that the rows received equal
   list_total_count.
3. The portal rejects some default User-Agents (curl's gets HTTP 400).

Rate limiting is shared by all threads of a process through KNA_API_RATE
(calls per second, default 3).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable, Optional

import requests

BASE_URL = "https://open.assembly.go.kr/portal/openapi"
MAX_PAGE_SIZE = 1000
HEADERS = {"User-Agent": "Mozilla/5.0"}

# INFO-200: no data. ERROR-337: traffic limit. ERROR-5xx/6xx: server side.
TRANSIENT_PREFIXES = ("ERROR-337", "ERROR-5", "ERROR-6")

log = logging.getLogger("kna_api")


class ApiError(RuntimeError):
    """A non-retryable API answer, or a retryable one that kept failing."""

    def __init__(self, endpoint: str, params: dict, code: str, message: str):
        self.endpoint = endpoint
        self.params = params
        self.code = code
        self.message = message
        super().__init__(f"{endpoint} {params}: {code} {message}")


def get_key() -> str:
    key = os.environ.get("ASSEMBLY_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "ASSEMBLY_API_KEY is not set. Without a key the API returns a "
            "5-row sample per request, so collection stops here."
        )
    return key


class RateLimiter:
    """Thread-safe minimum interval between calls."""

    def __init__(self, rate_per_sec: float):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        delay = slot - now
        if delay > 0:
            time.sleep(delay)


_limiter = RateLimiter(float(os.environ.get("KNA_API_RATE", "3")))
_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        _local.session = s
    return s


def parse_response(endpoint: str, payload: dict) -> tuple[str, str, int, list[dict]]:
    """Return (code, message, list_total_count, rows) from a JSON payload."""
    key = next((k for k in payload if k.upper() == endpoint.upper()), None)
    if key is not None:
        entries = payload[key]
        head = entries[0].get("head", []) if entries else []
        total, code, message = 0, "", ""
        for h in head:
            if "list_total_count" in h:
                total = int(h["list_total_count"])
            if "RESULT" in h:
                code = h["RESULT"].get("CODE", "")
                message = h["RESULT"].get("MESSAGE", "")
        rows: list[dict] = []
        for entry in entries[1:]:
            if isinstance(entry, dict) and "row" in entry:
                r = entry["row"]
                rows.extend([r] if isinstance(r, dict) else r)
        return code, message, total, rows
    if "RESULT" in payload:
        res = payload["RESULT"]
        return res.get("CODE", ""), res.get("MESSAGE", ""), 0, []
    raise ApiError(endpoint, {}, "UNEXPECTED", f"keys={list(payload)[:5]}")


def request_page(endpoint: str, params: dict, page: int, page_size: int,
                 retries: int = 8) -> tuple[int, list[dict]]:
    """One page. Returns (list_total_count, rows); raises ApiError."""
    query = {"KEY": get_key(), "Type": "json", "pIndex": page,
             "pSize": page_size, **params}
    last = ""
    for attempt in range(retries):
        _limiter.wait()
        try:
            resp = _session().get(f"{BASE_URL}/{endpoint}", params=query, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            code, message, total, rows = parse_response(endpoint, resp.json())
        except (requests.RequestException, ValueError) as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(min(120, 2 ** attempt))
            continue
        if code == "INFO-000":
            return total, rows
        if code == "INFO-200":
            return 0, []
        if code.startswith(TRANSIENT_PREFIXES):
            last = f"{code} {message}"
            time.sleep(min(300, 5 * 2 ** attempt))
            continue
        raise ApiError(endpoint, params, code, message)
    raise ApiError(endpoint, params, "GAVE-UP", last)


def fetch(endpoint: str, params: Optional[dict] = None,
          page_size: int = MAX_PAGE_SIZE, attempts: int = 3) -> list[dict]:
    """All rows for (endpoint, params). Raises unless rows == list_total_count.

    A list that grows while it is being paged (new bills arrive) makes the
    count check fail, so the whole fetch is retried a few times.
    """
    params = dict(params or {})
    for attempt in range(attempts):
        total, rows = request_page(endpoint, params, 1, page_size)
        page = 1
        while len(rows) < total:
            page += 1
            t, batch = request_page(endpoint, params, page, page_size)
            if not batch:
                break
            rows.extend(batch)
        if len(rows) == total:
            return rows
        log.warning(f"{endpoint} {params}: {len(rows)} rows vs list_total_count "
                    f"{total} (attempt {attempt + 1}/{attempts})")
    raise ApiError(endpoint, params, "COUNT-MISMATCH",
                   f"{len(rows)} rows vs list_total_count {total}")


def total_count(endpoint: str, params: Optional[dict] = None) -> int:
    total, _ = request_page(endpoint, dict(params or {}), 1, 1)
    return total


# ── Per-key collection with a crash-safe JSONL log ─────────────────────────

def read_jsonl(path: Path) -> dict[str, dict]:
    """Last record per key from a JSONL log written by fetch_many()."""
    done: dict[str, dict] = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    done[rec["key"]] = rec
    return done


def fetch_many(endpoint: str, keys: Iterable[str],
               params_for: Callable[[str], dict], log_path: Path,
               workers: int = 4, page_size: int = 100,
               progress_every: int = 500) -> dict[str, dict]:
    """Fetch one request per key, appending {"key", "status", "rows"} lines.

    Keys already logged with status "ok" are skipped, so a rerun resumes.
    Failed keys are logged with status "error" and retried on the next run.
    Returns the full log (all keys ever fetched) as {key: record}.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    done = read_jsonl(log_path)
    todo = [k for k in dict.fromkeys(keys) if done.get(k, {}).get("status") != "ok"]
    log.info(f"{endpoint}: {len(todo):,} to fetch ({len(done):,} already logged)")
    if not todo:
        return done

    lock = threading.Lock()
    errors = 0
    start = time.time()

    def work(k: str) -> dict:
        try:
            rows = fetch(endpoint, params_for(k), page_size=page_size)
            return {"key": k, "status": "ok", "rows": rows}
        except ApiError as e:
            return {"key": k, "status": "error", "code": e.code, "message": e.message}

    with open(log_path, "a", encoding="utf-8") as out, \
            ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, k) for k in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            with lock:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                done[rec["key"]] = rec
                if rec["status"] != "ok":
                    errors += 1
                    if rec.get("code") == "ERROR-337":
                        log.error(f"{endpoint}: traffic limit reached, stopping")
                        for f in futures:
                            f.cancel()
                        break
            if i % progress_every == 0 or i == len(todo):
                out.flush()
                rate = i / max(time.time() - start, 1e-9)
                log.info(f"{endpoint}: {i:,}/{len(todo):,} "
                         f"({rate:.1f}/s, errors {errors})")
    if errors:
        log.warning(f"{endpoint}: {errors} keys failed; rerun to retry them")
    return done


def rows_from_log(done: dict[str, dict], tag_col: str = "_BILL_ID") -> list[dict]:
    """Flatten the ok records of a fetch_many() log, tagging each row with its key."""
    out = []
    for k, rec in done.items():
        if rec.get("status") == "ok":
            for r in rec["rows"]:
                r = dict(r)
                r[tag_col] = k
                out.append(r)
    return out


def write_parquet_atomic(df, path: Path):
    """Write to a temp file and rename, so a crash never leaves a half file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)
