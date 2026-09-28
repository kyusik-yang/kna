"""
Member-level roll calls of the 17th-19th Assemblies from the plenary minutes
============================================================================
The Open Assembly API has no member-level votes before the 20th Assembly. The
plenary minutes (국회본회의 회의록) print them. Every recorded (electronic)
vote announced in the body with '(찬반 의원 성명은 끝에 실음)' has its name
lists in the appendix 【전자투표 찬반 의원 성명】: one ◯ title per vote, the
printed group counts 투표/찬성/반대/기권 의원(N인) and the names under each.
This script downloads the minutes PDFs and turns those lists into tables.

Steps
-----
  list      Meeting list of one assembly from nzbyfwhwaoanttzje (본회의
            회의록, one row per agenda item, with PDF_LINK_URL), queried per
            calendar year. Writes data/raw/minutes_agenda_{age}.parquet.
  download  Each meeting's PDF_LINK_URL into data/pdfs/{age}/{CONFER_NUM}.pdf
            (gitignored). At most one request per second (API calls run with
            KNA_API_RATE=1, downloads sleep so that two requests are never
            less than a second apart). Every answer is appended to
            data/pdfs/{age}/fetch_log.jsonl. A PDF already on disk that starts
            with %PDF is logged as 'exists' and not fetched again, so an
            interrupted run resumes.
  parse     Parse every PDF (minutes_votes.py), link votes to bills and names
            to members, and write
              data/raw/minutes_votes_{age}.parquet        one row per printed name
              data/raw/minutes_vote_events_{age}.parquet  one row per vote
              data/raw/minutes_meetings_{age}.parquet     one row per meeting: the
                PDF's fetch status, size and sha256, and the parse counts
                (roll-call headings, votes, chair announcements, markers).
            The link step reads master_bills_{age}, nzpltgfqabtcpsmai_{age} and
            members_{age} (--members-dir and --master-dir, default data/processed).

The rules for events, counts, bill links and same-name members are in the
docstring of minutes_votes.py.

API key: export ASSEMBLY_API_KEY (see kna_api.py). The key is never printed.

Parsing needs PyMuPDF (import fitz) and the `hanja` package (Hanja bill
titles are read in Hangul for the bill match). build_all.sh does not parse:
it reads the two data/raw tables this script writes.

Usage:
    python3 collect_minutes_votes.py list --ages 17-19
    python3 collect_minutes_votes.py download --ages 17-19
    python3 collect_minutes_votes.py parse --ages 17-19
    python3 collect_minutes_votes.py all --ages 17-19
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ["KNA_API_RATE"] = "1"   # at most one API call per second, whatever the environment says

import pandas as pd  # noqa: E402
import requests  # noqa: E402

import kna_api  # noqa: E402

REPO = Path(__file__).resolve().parent
DATA_DIR = REPO / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
PDF_DIR = DATA_DIR / "pdfs"

ENDPOINT = "nzbyfwhwaoanttzje"
TERM_YEARS = {17: range(2004, 2009), 18: range(2008, 2013), 19: range(2012, 2017)}
MIN_INTERVAL = 1.0   # seconds between two requests, API or PDF
HEADERS = {"User-Agent": "Mozilla/5.0"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("collect_minutes_votes")


def parse_ages(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        ages = list(range(int(a), int(b) + 1))
    else:
        ages = [int(x) for x in s.split(",")]
    bad = [a for a in ages if a not in TERM_YEARS]
    if bad:
        raise SystemExit(f"assemblies {bad} not supported (17-19 only)")
    return ages


# ── list ────────────────────────────────────────────────────────────────

def meetings_path(age: int) -> Path:
    return RAW_DIR / f"minutes_meetings_{age}.parquet"


def agenda_path(age: int) -> Path:
    return RAW_DIR / f"minutes_agenda_{age}.parquet"


def list_meetings(age: int, refresh: bool = False) -> pd.DataFrame:
    """Agenda rows of every plenary meeting of one assembly (one API call per year)."""
    path = agenda_path(age)
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    rows = []
    for y in TERM_YEARS[age]:
        got = kna_api.fetch(ENDPOINT, {"DAE_NUM": str(age), "CONF_DATE": str(y)})
        log.info(f"  {ENDPOINT} DAE_NUM={age} CONF_DATE={y}: {len(got)} agenda rows")
        rows += got
    df = pd.DataFrame(rows)
    df = df[df["DAE_NUM"].astype(str) == str(age)].copy()
    df["CONFER_NUM"] = df["CONFER_NUM"].astype(int)
    df = df.drop_duplicates().sort_values(["CONF_DATE", "CONFER_NUM"], kind="mergesort")
    kna_api.write_parquet_atomic(df.reset_index(drop=True), path)
    log.info(f"  {age}th: {len(df)} agenda rows, {df['CONFER_NUM'].nunique()} meetings -> {path}")
    return df


def meeting_table(agenda: pd.DataFrame) -> pd.DataFrame:
    """One row per meeting from the agenda rows."""
    g = agenda.groupby("CONFER_NUM", sort=False)
    urls = g["PDF_LINK_URL"].nunique()
    if (urls > 1).any():
        raise SystemExit(f"meetings with more than one PDF_LINK_URL: {list(urls[urls > 1].index)[:5]}")
    mt = g.agg(conf_id=("CONF_ID", "first"), title=("TITLE", "first"),
               date=("CONF_DATE", "first"), pdf_link_url=("PDF_LINK_URL", "first"),
               n_agenda_rows=("SUB_NAME", "size")).reset_index()
    mt = mt.rename(columns={"CONFER_NUM": "confer_num"})
    return mt.sort_values(["date", "confer_num"], kind="mergesort").reset_index(drop=True)


# ── download ────────────────────────────────────────────────────────────

class Throttle:
    def __init__(self, interval: float = MIN_INTERVAL):
        self.interval = interval
        self.last = 0.0

    def wait(self):
        d = self.last + self.interval - time.monotonic()
        if d > 0:
            time.sleep(d)
        self.last = time.monotonic()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_fetch_log(path: Path) -> dict[int, dict]:
    done: dict[int, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[int(rec["confer_num"])] = rec
    return done


def download(age: int, retries: int = 3) -> pd.DataFrame:
    mt = meeting_table(list_meetings(age))
    out_dir = PDF_DIR / str(age)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "fetch_log.jsonl"
    done = read_fetch_log(log_path)
    sess = requests.Session()
    sess.headers.update(HEADERS)
    throttle = Throttle()
    n_new = n_exist = n_fail = 0
    with open(log_path, "a", encoding="utf-8") as logf:
        for _, r in mt.iterrows():
            cn = int(r["confer_num"])
            pdf = out_dir / f"{cn}.pdf"
            if pdf.exists() and pdf.read_bytes()[:4] == b"%PDF":
                if done.get(cn, {}).get("status") not in ("ok", "exists"):
                    rec = {"confer_num": cn, "url": r["pdf_link_url"], "status": "exists",
                           "bytes": pdf.stat().st_size, "sha256": sha256(pdf),
                           "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                    logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    done[cn] = rec
                n_exist += 1
                continue
            rec = {"confer_num": cn, "url": r["pdf_link_url"]}
            for attempt in range(retries):
                throttle.wait()
                t0 = time.time()
                try:
                    resp = sess.get(r["pdf_link_url"], timeout=180)
                    rec.update(http=resp.status_code, bytes=len(resp.content),
                               secs=round(time.time() - t0, 2))
                    if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                        tmp = pdf.with_suffix(".pdf.tmp")
                        tmp.write_bytes(resp.content)
                        os.replace(tmp, pdf)
                        rec.update(status="ok", sha256=hashlib.sha256(resp.content).hexdigest())
                        break
                    rec.update(status="not_pdf", head=resp.content[:16].decode("latin-1"))
                except requests.RequestException as e:
                    rec.update(status="download_error", error=f"{type(e).__name__}: {e}")
                time.sleep(min(60, 5 * 2 ** attempt))
            rec["logged_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logf.flush()
            done[cn] = rec
            if rec["status"] == "ok":
                n_new += 1
            else:
                n_fail += 1
            log.info(f"  {age}th {cn}: {rec['status']} {rec.get('bytes')} bytes")
    log.info(f"  {age}th: {len(mt)} meetings, {n_new} downloaded, {n_exist} already on disk, "
             f"{n_fail} failed (rerun to retry)")
    return mt


# ── parse ───────────────────────────────────────────────────────────────

def parse(age: int, members_dir: Path, master_dir: Path) -> None:
    import minutes_votes as mv  # needs PyMuPDF and hanja

    mt = meeting_table(list_meetings(age))
    fetched = read_fetch_log(PDF_DIR / str(age) / "fetch_log.jsonl")
    ev, votes, meet = mv.build_term(age, mt, PDF_DIR / str(age), fetched,
                                    members_dir=members_dir, master_dir=master_dir,
                                    raw_dir=RAW_DIR)
    kna_api.write_parquet_atomic(ev, RAW_DIR / f"minutes_vote_events_{age}.parquet")
    kna_api.write_parquet_atomic(votes, RAW_DIR / f"minutes_votes_{age}.parquet")
    kna_api.write_parquet_atomic(meet, meetings_path(age))
    log.info(f"  {age}th: {len(meet)} meetings, {len(ev):,} votes, {len(votes):,} member-vote rows")
    for line in mv.summary_lines(age, ev, votes, meet):
        log.info("    " + line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("step", choices=["list", "download", "parse", "all"])
    ap.add_argument("--ages", default="17-19")
    ap.add_argument("--refresh-list", action="store_true",
                    help="Query the meeting list again even if it is on disk")
    ap.add_argument("--members-dir", type=Path, default=PROCESSED_DIR)
    ap.add_argument("--master-dir", type=Path, default=PROCESSED_DIR)
    args = ap.parse_args()
    for age in parse_ages(args.ages):
        if args.step in ("list", "all"):
            list_meetings(age, refresh=args.refresh_list)
        if args.step in ("download", "all"):
            download(age)
        if args.step in ("parse", "all"):
            parse(age, args.members_dir, args.master_dir)


if __name__ == "__main__":
    main()
