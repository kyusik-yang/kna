"""
Extract individual legislator votes from plenary session PDF appendices.
========================================================================
For 18-19대 (and 17대 appendix cases), vote name lists appear in the
부록 (appendix) section of the meeting record PDF, not in the speech text.

Pipeline:
  1. Identify plenary meetings with appendix vote references
  2. Get PDF download URLs via VCONFDETAIL API (CONF_ID -> DOWN_URL)
  3. Download PDFs
  4. Parse appendix sections with PyMuPDF for voter name lists
  5. Output parquet with member-level roll call data

Usage:
    python3 extract_appendix_votes.py --term 18          # Single assembly
    python3 extract_appendix_votes.py --term 18 --test   # Test with 3 PDFs
    python3 extract_appendix_votes.py                    # All 17-19대
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF required: pip install PyMuPDF")
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────

KR_HEARINGS = Path("/Users/kyusik/Desktop/kyusik-github/kr-hearings-data/data")
SPEECHES_FILE = KR_HEARINGS / "all_speeches_16_22_v9.parquet"

API_KEY = os.environ.get("ASSEMBLY_API_KEY", "REDACTED")
BASE_URL = "https://open.assembly.go.kr/portal/openapi"
HEADERS = {"User-Agent": "Mozilla/5.0"}

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PDF_DIR = DATA_DIR / "pdfs"

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "appendix_votes.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

VOTE_SECTION_RE = re.compile(
    r'(찬성\s*의원|반대\s*의원|기권\s*의원|불참\s*의원|투표\s*의원)\s*[\(（]?\s*(\d+)\s*인\s*[\)）]?\s*'
)
KOREAN_NAME_RE = re.compile(r'[가-힣]{2,4}')
NOISE_WORDS = {"의원", "의장", "부의장", "위원", "위원장", "국회", "선포",
               "가결", "부결", "투표", "재석", "결과", "성명", "본회의",
               "한나라당", "민주당", "열린우리당", "자유선진당", "민주노동당",
               "새누리당", "통합민주당", "민주통합당", "새정치민주연합",
               "바른미래당", "정의당", "국민의당", "무소속", "진보신당",
               "창조한국당", "선진통일당", "자유한국당", "친박연대"}


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1.0, status_forcelist=[500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


# ── Step 1: Identify meetings ─────────────────────────────────────────────

def find_appendix_meetings(term: int) -> pd.DataFrame:
    """Find plenary meetings that reference appendix vote lists."""
    log.info(f"Loading speeches for {term}대...")
    df = pd.read_parquet(SPEECHES_FILE)
    plenary = df[(df["hearing_type"] == "국회본회의") & (df["term"] == term)]

    # Find meetings with "성명은 끝에 실음" references
    has_ref = plenary[plenary["speech_text"].str.contains("성명은 끝에", na=False)]
    meetings = has_ref.groupby("meeting_id").agg(
        date=("date", "first"),
        n_vote_refs=("speech_text", lambda x: sum(s.count("성명은 끝에") for s in x)),
        session=("session", "first"),
    ).reset_index()

    log.info(f"  {term}대: {len(meetings)} meetings with appendix vote references "
             f"({meetings['n_vote_refs'].sum()} total vote events)")
    return meetings


# ── Step 2: Get PDF URLs ──────────────────────────────────────────────────

def get_pdf_urls(meetings: pd.DataFrame) -> pd.DataFrame:
    """Get PDF download URLs from VCONFDETAIL API."""
    session = make_session()
    urls = []

    for _, row in meetings.iterrows():
        mid = str(row["meeting_id"]).zfill(6)
        params = {
            "KEY": API_KEY, "Type": "json", "pIndex": 1, "pSize": 1,
            "CONF_ID": mid,
        }
        try:
            resp = session.get(f"{BASE_URL}/VCONFDETAIL", params=params, timeout=15)
            data = resp.json()

            down_url = None
            for key in data:
                if isinstance(data[key], list):
                    for entry in data[key]:
                        if isinstance(entry, dict) and "row" in entry:
                            for r in entry["row"]:
                                if "DOWN_URL" in r:
                                    down_url = r["DOWN_URL"]
                                    break

            urls.append({"meeting_id": row["meeting_id"], "down_url": down_url})
        except Exception as e:
            log.error(f"  VCONFDETAIL failed for {mid}: {e}")
            urls.append({"meeting_id": row["meeting_id"], "down_url": None})

        time.sleep(0.3)

    url_df = pd.DataFrame(urls)
    found = url_df["down_url"].notna().sum()
    log.info(f"  PDF URLs found: {found}/{len(meetings)}")
    return meetings.merge(url_df, on="meeting_id")


# ── Step 3: Download PDFs ─────────────────────────────────────────────────

def download_pdfs(meetings: pd.DataFrame, term: int) -> list[Path]:
    """Download plenary session PDFs."""
    pdf_dir = PDF_DIR / f"plenary_{term}"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    session = make_session()
    paths = []

    for _, row in meetings.iterrows():
        if pd.isna(row.get("down_url")):
            paths.append(None)
            continue

        pdf_path = pdf_dir / f"{row['meeting_id']}.pdf"
        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            paths.append(pdf_path)
            continue

        try:
            resp = session.get(row["down_url"], timeout=30)
            if resp.status_code == 200 and len(resp.content) > 1000:
                pdf_path.write_bytes(resp.content)
                paths.append(pdf_path)
            else:
                log.warning(f"  PDF download failed for {row['meeting_id']}: "
                            f"status={resp.status_code}, size={len(resp.content)}")
                paths.append(None)
        except Exception as e:
            log.error(f"  PDF download error for {row['meeting_id']}: {e}")
            paths.append(None)

        time.sleep(0.3)

    meetings["pdf_path"] = paths
    downloaded = sum(1 for p in paths if p is not None)
    log.info(f"  PDFs downloaded: {downloaded}/{len(meetings)}")
    return paths


# ── Step 4: Parse PDF appendix ────────────────────────────────────────────

def parse_pdf_votes(pdf_path: Path, meeting_id: str, date: str,
                    term: int) -> list[dict]:
    """Extract voter name lists from PDF appendix."""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        log.error(f"  Cannot open PDF {pdf_path}: {e}")
        return []

    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()

    # Find all vote sections in the PDF
    all_votes = []
    vote_event = 0

    sections = list(VOTE_SECTION_RE.finditer(full_text))
    if not sections:
        return []

    # Group sections into vote events (찬성+반대+기권 within ~3000 chars)
    events = []
    current_event = [sections[0]]
    for s in sections[1:]:
        if s.start() - current_event[-1].end() < 3000:
            current_event.append(s)
        else:
            events.append(current_event)
            current_event = [s]
    events.append(current_event)

    for event_sections in events:
        vote_event += 1

        # Try to find bill context before this vote event
        event_start = event_sections[0].start()
        lookback = full_text[max(0, event_start - 500):event_start]
        bill_ctx = ""
        m = re.search(r'(\d+\.\s*.+?(?:의건|법률안|동의안|결의안))', lookback)
        if m:
            bill_ctx = m.group(1).strip()[:100]

        # Parse each section in this event
        for i, match in enumerate(event_sections):
            vote_type = match.group(1)
            expected = int(match.group(2))

            if vote_type == "투표의원":
                continue

            # Normalize vote_type (remove whitespace/newlines)
            vote_type_clean = re.sub(r'\s+', '', vote_type)
            vote_map = {
                "찬성의원": "찬성", "반대의원": "반대",
                "기권의원": "기권", "불참의원": "불참",
                "투표의원": "_skip",
            }
            if vote_map.get(vote_type_clean) == "_skip":
                continue
            vote_val = vote_map.get(vote_type_clean, vote_type_clean)

            start = match.end()
            if i + 1 < len(event_sections):
                end = event_sections[i + 1].start()
            else:
                end = min(start + 3000, len(full_text))

            name_region = full_text[start:end]
            names = KOREAN_NAME_RE.findall(name_region)
            names = [n for n in names if n not in NOISE_WORDS and len(n) >= 2]

            # Truncate to expected count if overshoot
            if len(names) > expected * 1.2 and expected > 0:
                names = names[:expected]

            for name in names:
                all_votes.append({
                    "term": term,
                    "meeting_id": meeting_id,
                    "date": date,
                    "vote_event": vote_event,
                    "bill_context": bill_ctx,
                    "member_name": name,
                    "vote": vote_val,
                    "source": "pdf_appendix",
                })

    return all_votes


# ── Main pipeline ─────────────────────────────────────────────────────────

def run(term: int, test: bool = False):
    log.info(f"\n{'='*60}")
    log.info(f"Appendix Vote Extraction: {term}대")
    log.info(f"{'='*60}")

    # Step 1
    meetings = find_appendix_meetings(term)
    if meetings.empty:
        log.info("  No meetings with appendix references found.")
        return

    if test:
        meetings = meetings.head(3)
        log.info(f"  [TEST MODE] Processing first 3 meetings only")

    # Step 2
    meetings = get_pdf_urls(meetings)

    # Step 3
    download_pdfs(meetings, term)

    # Step 4
    all_votes = []
    for _, row in meetings.iterrows():
        if row.get("pdf_path") is None:
            continue
        votes = parse_pdf_votes(
            Path(row["pdf_path"]), str(row["meeting_id"]),
            str(row["date"]), term
        )
        all_votes.extend(votes)
        if votes:
            log.info(f"  Meeting {row['meeting_id']} ({row['date']}): "
                     f"{len(votes)} vote records from {len(set(v['vote_event'] for v in votes))} events")

    if all_votes:
        df = pd.DataFrame(all_votes)
        outpath = RAW_DIR / f"appendix_votes_{term}.parquet"
        df.to_parquet(outpath, index=False)
        log.info(f"\n  Saved: {outpath.name} ({len(df):,} rows)")
        log.info(f"  Vote distribution: {df['vote'].value_counts().to_dict()}")
        log.info(f"  Unique members: {df['member_name'].nunique()}")
    else:
        log.warning("  No votes extracted from PDFs")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--term", type=int)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    if args.term:
        run(args.term, args.test)
    else:
        for term in [18, 19]:
            run(term, args.test)


if __name__ == "__main__":
    main()
