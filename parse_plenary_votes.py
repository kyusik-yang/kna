"""
Parse individual legislator votes from plenary session transcripts.
================================================================
Extracts member-level roll call data from 국회본회의 회의록 speech text.

Two sources of vote data:
  1. Inline: "찬성의원(N인) 이름1 이름2 ..." directly in speech_text
  2. Appendix: "(찬반의원 성명은 끝에 실음)" - needs raw 회의록 PDF/XML

This script handles Source 1. Source 2 requires a separate pipeline.

Usage:
    python3 parse_plenary_votes.py                 # Parse all assemblies
    python3 parse_plenary_votes.py --term 17       # Single assembly
    python3 parse_plenary_votes.py --test          # Test mode (sample only)
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

# ── Configuration ──────────────────────────────────────────────────────────

KR_HEARINGS_DATA = Path("/Users/kyusik/Desktop/kyusik-github/kr-hearings-data/data")
SPEECHES_FILE = KR_HEARINGS_DATA / "all_speeches_16_22_v9.parquet"
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "parse_votes.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── Vote Parsing ───────────────────────────────────────────────────────────

# Pattern: "찬성의원(210인)" or "반대의원(8인)" or "기권의원(9인)"
VOTE_SECTION_RE = re.compile(
    r'(찬성의원|반대의원|기권의원|투표의원|불참의원)\s*\((\d+)인\)\s*'
)

# Korean name: 2-4 characters of Hangul
KOREAN_NAME_RE = re.compile(r'[가-힣]{2,4}')

# Bill name pattern: appears before vote section
# "N. 법안명(제안자 제의)" or just the agenda item
AGENDA_RE = re.compile(
    r'(?:^|\n)\s*\d+\.\s+(.+?)(?:\(|$)', re.MULTILINE
)


def parse_vote_block(text: str) -> list[dict]:
    """
    Parse a text block containing vote results.

    Expected format:
        투표의원(227인)
        찬성의원(210인) 이름1 이름2 이름3 ...
        반대의원(8인) 이름1 이름2 ...
        기권의원(9인) 이름1 이름2 ...

    Returns list of {name, vote} dicts.
    """
    results = []

    # Find all vote sections
    sections = list(VOTE_SECTION_RE.finditer(text))
    if not sections:
        return results

    for i, match in enumerate(sections):
        vote_type = match.group(1)
        expected_count = int(match.group(2))

        # Skip 투표의원 (it's the total, not a vote category)
        if vote_type == "투표의원":
            continue

        # Map to standardized vote value
        vote_map = {
            "찬성의원": "찬성",
            "반대의원": "반대",
            "기권의원": "기권",
            "불참의원": "불참",
        }
        vote_value = vote_map.get(vote_type, vote_type)

        # Extract name region: from this match to next section or end
        start = match.end()
        if i + 1 < len(sections):
            end = sections[i + 1].start()
        else:
            # Take up to 2000 chars after (enough for ~200 names)
            end = min(start + 2000, len(text))

        name_region = text[start:end]

        # Extract Korean names
        names = KOREAN_NAME_RE.findall(name_region)

        # Filter out common non-name words
        noise = {"의원", "의장", "부의장", "위원", "위원장", "국회", "선포",
                 "가결", "부결", "투표", "재석", "결과", "성명", "본회의",
                 "한나라당", "민주당", "열린우리당", "자유선진당", "민주노동당",
                 "창조한국당", "진보신당", "무소속", "국민의힘", "더불어민주당",
                 "새누리당", "바른미래당", "정의당", "국민의당"}
        names = [n for n in names if n not in noise and len(n) >= 2]

        # Sanity check
        if abs(len(names) - expected_count) > 5:
            log.warning(f"  Name count mismatch: expected {expected_count}, got {len(names)} "
                        f"for {vote_type}")

        for name in names:
            results.append({"member_name": name, "vote": vote_value})

    return results


def extract_bill_context(text: str, vote_start: int) -> str:
    """Try to extract the bill/agenda name from context before the vote block."""
    # Look back from vote_start for agenda items
    lookback = text[max(0, vote_start - 500):vote_start]

    # Try to find "N. bill name" pattern
    agendas = AGENDA_RE.findall(lookback)
    if agendas:
        return agendas[-1].strip()[:100]

    # Try to find "~의건" or "~법률안"
    m = re.search(r'([가-힣\s]{5,50}(?:의건|법률안|동의안|결의안))', lookback)
    if m:
        return m.group(1).strip()[:100]

    return ""


def parse_assembly_votes(plenary_df: pd.DataFrame, term: int) -> pd.DataFrame:
    """Parse all vote records from plenary speeches for one assembly."""
    log.info(f"\n{'='*50}")
    log.info(f"Parsing {term}대 plenary votes")
    log.info(f"{'='*50}")

    all_votes = []
    meetings_with_votes = 0
    vote_events = 0

    for meeting_id in sorted(plenary_df["meeting_id"].unique()):
        meeting = plenary_df[plenary_df["meeting_id"] == meeting_id].sort_values("speech_order")
        date = meeting.iloc[0]["date"] if "date" in meeting.columns else None

        meeting_votes_found = False

        for _, row in meeting.iterrows():
            text = row["speech_text"]
            if not isinstance(text, str):
                continue

            # Find all vote blocks in this speech
            vote_starts = [m.start() for m in VOTE_SECTION_RE.finditer(text)
                           if m.group(1) != "투표의원"]

            if not vote_starts:
                continue

            # Group nearby vote sections (within 1500 chars = one vote event)
            groups = []
            current_group = [vote_starts[0]]
            for vs in vote_starts[1:]:
                if vs - current_group[-1] < 1500:
                    current_group.append(vs)
                else:
                    groups.append(current_group)
                    current_group = [vs]
            groups.append(current_group)

            for group in groups:
                start = group[0]
                end = min(group[-1] + 2000, len(text))
                block = text[start:end]

                votes = parse_vote_block(block)
                if not votes:
                    continue

                meeting_votes_found = True
                vote_events += 1
                bill_context = extract_bill_context(text, start)

                # Find aggregate counts from chair announcement
                agg_match = re.search(
                    r'재석\s*(\d+)\s*인\s*중\s*찬성\s*(\d+)\s*인',
                    text[max(0, start - 300):start]
                )
                agg_yes = int(agg_match.group(2)) if agg_match else None
                agg_total = int(agg_match.group(1)) if agg_match else None

                for v in votes:
                    v.update({
                        "term": term,
                        "meeting_id": meeting_id,
                        "date": date,
                        "bill_context": bill_context,
                        "speech_order": row["speech_order"],
                        "vote_event": vote_events,
                        "agg_total": agg_total,
                        "agg_yes": agg_yes,
                    })
                    all_votes.append(v)

        if meeting_votes_found:
            meetings_with_votes += 1

    df = pd.DataFrame(all_votes)
    log.info(f"  Meetings with votes: {meetings_with_votes}")
    log.info(f"  Vote events: {vote_events}")
    log.info(f"  Total vote records: {len(df):,}")

    if not df.empty:
        log.info(f"  Vote distribution:")
        for vote_val, cnt in df["vote"].value_counts().items():
            log.info(f"    {vote_val}: {cnt:,}")

    return df


def check_appendix_coverage(plenary_df: pd.DataFrame, term: int):
    """Report how many votes are in appendix (not parseable from text)."""
    appendix_count = plenary_df["speech_text"].str.contains(
        "성명은 끝에", na=False
    ).sum()
    inline_count = plenary_df["speech_text"].str.contains(
        "찬성의원", na=False
    ).sum()
    log.info(f"  Inline vote lists: {inline_count}")
    log.info(f"  Appendix references ('성명은 끝에 실음'): {appendix_count}")
    log.info(f"  → {appendix_count} vote events need raw 회의록 PDF/XML for extraction")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse plenary vote records")
    parser.add_argument("--term", type=int, help="Single assembly term")
    parser.add_argument("--test", action="store_true", help="Test mode")
    args = parser.parse_args()

    log.info("Loading speeches...")
    df = pd.read_parquet(SPEECHES_FILE)
    plenary = df[df["hearing_type"] == "국회본회의"]
    log.info(f"  Plenary speeches: {len(plenary):,} across {plenary['term'].nunique()} assemblies")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if args.test:
        # Test with 17대 only (has most inline vote data)
        term = args.term or 17
        sub = plenary[plenary["term"] == term]
        check_appendix_coverage(sub, term)
        result = parse_assembly_votes(sub, term)
        if not result.empty:
            log.info(f"\n  Sample records:")
            for _, r in result.head(10).iterrows():
                log.info(f"    {r['date']} | {r['member_name']:4s} | {r['vote']:3s} | {r['bill_context'][:40]}")
        return

    terms = [args.term] if args.term else [16, 17, 18, 19]
    all_results = []

    for term in terms:
        sub = plenary[plenary["term"] == term]
        if sub.empty:
            log.warning(f"  No plenary data for {term}대")
            continue

        check_appendix_coverage(sub, term)
        result = parse_assembly_votes(sub, term)

        if not result.empty:
            outpath = RAW_DIR / f"plenary_votes_{term}.parquet"
            result.to_parquet(outpath, index=False)
            log.info(f"  Saved: {outpath.name}")
            all_results.append(result)

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        outpath = RAW_DIR / "plenary_votes_16_19.parquet"
        combined.to_parquet(outpath, index=False)
        log.info(f"\nCombined: {outpath.name} ({len(combined):,} rows)")

        log.info(f"\n{'='*50}")
        log.info("Summary")
        log.info(f"{'='*50}")
        summary = combined.groupby("term").agg(
            vote_events=("vote_event", "nunique"),
            total_records=("member_name", "count"),
            unique_members=("member_name", "nunique"),
        )
        log.info(f"\n{summary}")


if __name__ == "__main__":
    main()
