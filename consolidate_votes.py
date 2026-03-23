"""
Consolidate all vote data into a unified roll call dataset.
============================================================
Merges three sources:
  1. Inline votes (16-17대): parsed from plenary speech text
  2. Appendix votes (17-19대): parsed from plenary PDF appendices
  3. API votes (20-22대): collected from nojepdqqaweusdfbi endpoint

Output: data/processed/roll_calls_all.parquet

Usage:
    python3 consolidate_votes.py
"""

import logging
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_inline_votes() -> pd.DataFrame:
    """Load inline votes parsed from speech text (16-17대)."""
    path = RAW_DIR / "plenary_votes_16_19.parquet"
    if not path.exists():
        log.warning("  Inline votes not found")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["source"] = "inline_text"
    # Standardize vote values
    df["vote"] = df["vote"].str.strip()
    log.info(f"  Inline votes: {len(df):,} rows ({df['term'].nunique()} assemblies)")
    return df


def load_appendix_votes() -> pd.DataFrame:
    """Load appendix votes parsed from PDFs (17-19대)."""
    frames = []
    for term in [17, 18, 19]:
        path = RAW_DIR / f"appendix_votes_{term}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            frames.append(df)

    if not frames:
        log.warning("  Appendix votes not found")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    # Normalize vote values (remove whitespace/newlines from PDF parsing)
    df["vote"] = df["vote"].str.replace(r'\s+', '', regex=True)
    vote_map = {"찬성의원": "찬성", "반대의원": "반대", "기권의원": "기권", "불참의원": "불참"}
    df["vote"] = df["vote"].map(vote_map).fillna(df["vote"])
    if "source" not in df.columns:
        df["source"] = "pdf_appendix"
    log.info(f"  Appendix votes: {len(df):,} rows ({df['term'].nunique()} assemblies)")
    return df


def load_api_votes() -> pd.DataFrame:
    """Load API-collected roll calls (20-22대)."""
    frames = []
    for age in [20, 21, 22]:
        path = RAW_DIR / f"roll_calls_{age}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            frames.append(df)

    if not frames:
        log.warning("  API votes not found")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    # Standardize columns to match other sources
    col_map = {
        "member_name": "member_name",
        "vote": "vote",
        "bill_id": "bill_id",
        "age": "term",
        "party": "party",
        "district": "district",
        "member_id": "member_id",
        "vote_date": "date",
    }
    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename)
    df["source"] = "api"

    # Standardize vote values
    vote_map = {"찬성": "찬성", "반대": "반대", "기권": "기권", "불참": "불참"}
    df["vote"] = df["vote"].map(vote_map).fillna(df["vote"])

    log.info(f"  API votes: {len(df):,} rows ({df['term'].nunique()} assemblies)")
    return df


def consolidate():
    log.info("="*60)
    log.info("Consolidating all vote data")
    log.info("="*60)

    inline = load_inline_votes()
    appendix = load_appendix_votes()
    api = load_api_votes()

    # Standardize columns across sources
    common_cols = ["term", "meeting_id", "date", "member_name", "vote", "source"]
    optional_cols = ["bill_id", "bill_context", "party", "district", "member_id",
                     "vote_event", "agg_total", "agg_yes"]

    frames = []
    for df in [inline, appendix, api]:
        if df.empty:
            continue
        # Ensure common cols exist
        for col in common_cols:
            if col not in df.columns:
                df[col] = None
        # Add optional cols if missing
        for col in optional_cols:
            if col not in df.columns:
                df[col] = None
        frames.append(df[common_cols + [c for c in optional_cols if c in df.columns]])

    if not frames:
        log.error("No vote data found!")
        return

    all_votes = pd.concat(frames, ignore_index=True)

    # Convert term to int
    all_votes["term"] = pd.to_numeric(all_votes["term"], errors="coerce").astype("Int64")

    # Deduplicate within each source type separately
    before = len(all_votes)
    deduped = []

    # API data: dedup on bill_id + member_name (each member votes once per bill)
    api_data = all_votes[all_votes["source"] == "api"]
    if not api_data.empty:
        api_data = api_data.drop_duplicates(subset=["term", "bill_id", "member_name"], keep="first")
        deduped.append(api_data)
        log.info(f"  API after dedup: {len(api_data):,}")

    # Text/PDF data: dedup on meeting_id + member_name + vote_event
    text_data = all_votes[all_votes["source"].isin(["inline_text", "pdf_appendix"])]
    if not text_data.empty:
        # For 17대 (both inline and appendix), prefer appendix (from PDF, more complete)
        text_data = text_data.sort_values("source")  # inline_text first, pdf_appendix second
        text_data = text_data.drop_duplicates(
            subset=["term", "meeting_id", "member_name", "vote_event"],
            keep="last"  # keep pdf_appendix over inline_text
        )
        deduped.append(text_data)
        log.info(f"  Text/PDF after dedup: {len(text_data):,}")

    all_votes = pd.concat(deduped, ignore_index=True) if deduped else pd.DataFrame()
    after = len(all_votes)
    log.info(f"  Total dedup: {before:,} -> {after:,} ({before - after:,} removed)")

    # Summary
    log.info(f"\n{'='*60}")
    log.info("Consolidated Roll Call Dataset")
    log.info(f"{'='*60}")
    log.info(f"  Total records: {len(all_votes):,}")
    log.info(f"  Unique members: {all_votes['member_name'].nunique():,}")

    log.info(f"\n  By assembly:")
    for term in sorted(all_votes["term"].dropna().unique()):
        sub = all_votes[all_votes["term"] == term]
        members = sub["member_name"].nunique()
        events = sub["vote_event"].nunique() if "vote_event" in sub.columns else "?"
        src = sub["source"].value_counts().to_dict()
        log.info(f"    {int(term)}대: {len(sub):>8,} votes | {members:>3} members | source: {src}")

    log.info(f"\n  Vote distribution:")
    for vote_val, cnt in all_votes["vote"].value_counts().items():
        log.info(f"    {vote_val}: {cnt:,}")

    # Save
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    outpath = PROCESSED_DIR / "roll_calls_all.parquet"
    all_votes.to_parquet(outpath, index=False)
    log.info(f"\n  Saved: {outpath.name} ({len(all_votes):,} rows)")

    return all_votes


if __name__ == "__main__":
    consolidate()
