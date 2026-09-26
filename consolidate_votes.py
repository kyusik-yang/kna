"""
Consolidate roll call votes into the unified member-level dataset.
==================================================================
roll_calls_all.parquet holds the recorded votes of the 20th-22nd Assemblies
collected from the nojepdqqaweusdfbi endpoint (collect_roll_calls.py), one row
per member per vote, unique on (term, bill_id, member_id).

  - Rows are keyed on member_id (MONA_CD), never on member_name. Four pairs of
    legislators share a name (20th 김성태 and 최경환, 21st 김병욱 and 이수진),
    and the 22nd adds 박지원 (8BF5855P, and H7X3372O from a by-election).
    An earlier version deduplicated on member_name and silently dropped
    12,418 of their rows (8,292 찬성/반대/기권 and 4,126 불참).
  - party is the party at election, from members_{term}.parquet (ALLNAMEMBER).
    The API's POLY_NM is the member's party at collection time, rewritten
    retroactively on every past vote, and is kept as party_api. Members
    missing from members_{term} fall back to party_api (counted in the log).
  - Rows are sorted by (term, date, bill_id, member_id). Ideal-point estimates
    depend on the row order, so the order is part of the output.

16th-19th Assemblies (experimental, not in roll_calls_all)
----------------------------------------------------------
The 16th-19th votes parsed from plenary speech text and minutes appendices
are NOT roll calls. extract_appendix_votes.py merges every vote in a meeting
into one pseudo-event, and each member keeps one arbitrary vote per meeting.
They are copied unchanged from the previously shipped roll_calls_all.parquet
(their member_id backfill cannot be reproduced from data/raw) into
roll_calls_16_19_experimental.parquet with
quality_flag = 'meeting_level_pseudo_event'. Do not build a vote matrix,
cohesion score or ideal point from them. A rebuild from the appendix PDFs is
deferred.

Outputs (in --out):
    roll_calls_all.parquet
    roll_calls_16_19_experimental.parquet
    reports/rollcall_tally_check.csv   member-level 찬성/반대/기권 per vote
                                       against the official tallies
                                       (ncocpgfiaoituanbr)

The run stops without writing roll_calls_all if a 20th or 21st Assembly vote
disagrees with its official tally, or is missing from either side, for a
reason not explained in the report. 22nd Assembly disagreements are reported
but do not stop the run: the member-level feed omits some members seated
during the term, so recent votes can have fewer member rows than MEMBER_TCNT.

Usage:
    python3 consolidate_votes.py
    python3 consolidate_votes.py --out data/_build --members-dir data/_build \\
        --legacy-text-from data/processed/roll_calls_all.parquet
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

API_TERMS = [20, 21, 22]
# Assemblies whose member-level votes must reproduce the official tallies
STRICT_TERMS = [20, 21]
TEXT_SOURCES = ["inline_text", "pdf_appendix"]
QUALITY_FLAG = "meeting_level_pseudo_event"
EXPERIMENTAL_NAME = "roll_calls_16_19_experimental.parquet"

# Column names and types of roll_calls_all as shipped up to 0.6.x. The API
# rows leave the text-only columns (meeting_id, bill_context, vote_event,
# agg_total, agg_yes) null.
LEGACY_SCHEMA = [
    ("term", pa.int64()),
    ("meeting_id", pa.string()),
    ("date", pa.string()),
    ("member_name", pa.string()),
    ("vote", pa.string()),
    ("source", pa.string()),
    ("bill_id", pa.string()),
    ("bill_context", pa.string()),
    ("party", pa.string()),
    ("district", pa.string()),
    ("member_id", pa.string()),
    ("vote_event", pa.float64()),
    ("agg_total", pa.null()),
    ("agg_yes", pa.null()),
]
LEGACY_COLS = [name for name, _ in LEGACY_SCHEMA]
ALL_SCHEMA = pa.schema(LEGACY_SCHEMA + [("bill_no", pa.string()),
                                        ("party_api", pa.string())])
EXPERIMENTAL_SCHEMA = pa.schema(LEGACY_SCHEMA + [("quality_flag", pa.string())])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def write_table_atomic(df: pd.DataFrame, schema: pa.Schema, path: Path):
    """Write df with an explicit schema to a temp file, then rename."""
    table = pa.Table.from_pandas(df[schema.names], schema=schema,
                                 preserve_index=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp)
    os.replace(tmp, path)


def load_api_votes() -> pd.DataFrame:
    """Load API-collected roll calls (20-22대), one row per member per vote."""
    cols = ["member_name", "party", "district", "member_id", "vote_date",
            "bill_no", "bill_id", "vote", "age"]
    frames = []
    for age in API_TERMS:
        path = RAW_DIR / f"roll_calls_{age}.parquet"
        if not path.exists():
            log.warning(f"  {path.name} not found, {age}대 skipped")
            continue
        df = pd.read_parquet(path, columns=cols)
        log.info(f"  {path.name}: {len(df):,} rows, {df['bill_id'].nunique():,} votes, "
                 f"dates {df['vote_date'].min()} to {df['vote_date'].max()}")
        frames.append(df)

    if not frames:
        log.warning("  API votes not found")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"age": "term", "vote_date": "date", "party": "party_api"})
    df["term"] = df["term"].astype("int64")
    df["source"] = "api"
    df["vote"] = df["vote"].str.strip()

    for col in ["member_id", "bill_id"]:
        n_na = df[col].isna().sum()
        if n_na:
            log.warning(f"  {n_na:,} API rows without {col}")

    # Each member votes once per vote. Never deduplicate on member_name.
    key = ["term", "bill_id", "member_id"]
    dup = df.duplicated(subset=key, keep="first")
    if dup.any():
        conflicts = (df[df.duplicated(subset=key, keep=False)]
                     .groupby(key)["vote"].nunique().gt(1).sum())
        log.warning(f"  {dup.sum():,} duplicate (term, bill_id, member_id) rows dropped, "
                    f"{conflicts:,} of those keys carry conflicting votes")
        df = df[~dup]
    else:
        log.info("  Duplicate (term, bill_id, member_id) rows: 0")

    log.info(f"  API votes: {len(df):,} rows ({df['term'].nunique()} assemblies)")
    return df


def attach_party(df: pd.DataFrame, members_dir: Path) -> pd.DataFrame:
    """Set party to the party at election (members_{term}), keep the API label."""
    parts = []
    for term in sorted(df["term"].unique()):
        path = members_dir / f"members_{term}.parquet"
        if not path.exists():
            log.warning(f"  {path} not found, {term}대 keeps the API party")
            continue
        m = pd.read_parquet(path, columns=["mona_cd", "party"])
        if m["mona_cd"].duplicated().any():
            raise SystemExit(f"{path} has more than one row per mona_cd")
        m = m.rename(columns={"mona_cd": "member_id", "party": "party_elected"})
        m["term"] = int(term)
        parts.append(m)

    if parts:
        members = pd.concat(parts, ignore_index=True)
        df = df.merge(members, on=["term", "member_id"], how="left",
                      validate="many_to_one")
    else:
        df = df.assign(party_elected=None)

    fallback = df["party_elected"].isna()
    df["party"] = df["party_elected"].where(~fallback, df["party_api"])
    for term, sub in df.groupby("term"):
        fb = sub[fallback.loc[sub.index]]
        log.info(f"    {term}대: party from members_{term} for "
                 f"{sub['member_id'].nunique() - fb['member_id'].nunique():,} members, "
                 f"fallback to API party for {fb['member_id'].nunique():,} members "
                 f"({len(fb):,} rows)")
    return df.drop(columns=["party_elected"])


def tally_check(api: pd.DataFrame, members_dir: Path) -> pd.DataFrame:
    """Compare member-level 찬성/반대/기권 per vote with the official tallies."""
    frames = []
    for term in API_TERMS:
        path = RAW_DIR / f"ncocpgfiaoituanbr_{term}.parquet"
        sub = api[api["term"] == term]
        if not path.exists():
            log.warning(f"  {path.name} not found, {term}대 not checked")
            continue
        t = pd.read_parquet(path)
        t = t.rename(columns={"BILL_ID": "bill_id", "BILL_NO": "bill_no",
                              "PROC_DT": "proc_dt", "MEMBER_TCNT": "tally_members",
                              "VOTE_TCNT": "tally_voted", "YES_TCNT": "tally_yes",
                              "NO_TCNT": "tally_no", "BLANK_TCNT": "tally_abstain"})
        for c in ["tally_members", "tally_voted", "tally_yes", "tally_no", "tally_abstain"]:
            t[c] = pd.to_numeric(t[c], errors="coerce")

        v = sub.groupby("bill_id")["vote"].agg(
            rows="size",
            yes=lambda s: (s == "찬성").sum(),
            no=lambda s: (s == "반대").sum(),
            abstain=lambda s: (s == "기권").sum(),
            absent=lambda s: (s == "불참").sum(),
        )
        t = t.merge(v, left_on="bill_id", right_index=True, how="left")
        t["row_match"] = ((t["yes"] == t["tally_yes"]) & (t["no"] == t["tally_no"])
                          & (t["abstain"] == t["tally_abstain"]))

        # One row per vote. A vote can carry more than one tally row upstream.
        g = t.groupby("bill_id", sort=False)
        out = g.first()[["bill_no", "proc_dt", "tally_members", "tally_voted",
                         "tally_yes", "tally_no", "tally_abstain",
                         "rows", "yes", "no", "abstain", "absent"]]
        out["n_tally_rows"] = g.size()
        out["any_row_match"] = g["row_match"].any()
        out["first_row_match"] = g["row_match"].first()
        out = out.reset_index()

        status = pd.Series("mismatch", index=out.index)
        status[out["first_row_match"] & (out["n_tally_rows"] == 1)] = "match"
        status[out["any_row_match"] & (out["n_tally_rows"] > 1)] = "match_one_of_duplicate_tally_rows"
        status[out["rows"].isna()] = "no_member_rows"
        out["status"] = status

        # Deficits only (member-level counts at or below every tally count) mean
        # members are missing from the member-level feed.
        d_yes = out["tally_yes"] - out["yes"]
        d_no = out["tally_no"] - out["no"]
        d_abs = out["tally_abstain"] - out["abstain"]
        out["missing_yes"], out["missing_no"], out["missing_abstain"] = d_yes, d_no, d_abs
        deficit = ((out["status"] == "mismatch") & (d_yes >= 0) & (d_no >= 0) & (d_abs >= 0)
                   & (out["rows"] < out["tally_members"]))
        # Anything else means a recorded vote itself differs from the tally.
        excess = (out["status"] == "mismatch") & ~deficit
        out["explanation"] = ""
        out.loc[out["status"] == "match_one_of_duplicate_tally_rows", "explanation"] = (
            "the API lists more than one tally row for this vote, and the "
            "member-level counts equal one of them")
        out.loc[deficit, "explanation"] = (
            "member rows missing from the member-level feed (rows < MEMBER_TCNT, "
            "counts at or below the tally)")
        out.loc[excess, "explanation"] = (
            "UNEXPLAINED: counts differ from the tally beyond missing member rows, "
            "so at least one recorded vote differs from the tally")
        out.loc[out["status"] == "no_member_rows", "explanation"] = (
            "vote in the tally list but not in roll_calls (not collected yet)")

        # Votes in the member-level data without a tally row
        extra = sorted(set(sub["bill_id"]) - set(out["bill_id"]))
        if extra:
            e = v.loc[extra].reset_index()
            e["status"] = "no_tally"
            e["explanation"] = "vote not in the tally list"
            out = pd.concat([out, e], ignore_index=True)

        out.insert(0, "term", term)
        frames.append(out)

        # Report
        counts = out["status"].value_counts().to_dict()
        log.info(f"  {term}대 tally check: {len(out):,} votes | {counts}")
        mism = out[out["status"] == "mismatch"]
        if len(mism):
            n_deficit = int(deficit.sum())
            log.info(f"    mismatches: {len(mism):,} votes, {n_deficit:,} of them only "
                     f"missing member rows | missing 찬성 {int(mism['missing_yes'].sum()):,}, "
                     f"반대 {int(mism['missing_no'].sum()):,}, "
                     f"기권 {int(mism['missing_abstain'].sum()):,} | "
                     f"dates {mism['proc_dt'].min()} to {mism['proc_dt'].max()}")
            for _, r in mism[mism["explanation"].str.startswith("UNEXPLAINED")].iterrows():
                log.warning(f"    {r['bill_id']} ({r['bill_no']}, {r['proc_dt']}): member-level "
                            f"찬성/반대/기권 {int(r['yes'])}/{int(r['no'])}/{int(r['abstain'])} vs "
                            f"tally {int(r['tally_yes'])}/{int(r['tally_no'])}/"
                            f"{int(r['tally_abstain'])}, {int(r['rows'])} member rows vs "
                            f"MEMBER_TCNT {int(r['tally_members'])}")
        dup_rows = out[out["status"] == "match_one_of_duplicate_tally_rows"]
        for _, r in dup_rows.iterrows():
            log.info(f"    {r['bill_id']} ({r['bill_no']}): {int(r['n_tally_rows'])} tally rows, "
                     f"member-level counts equal one of them")
        mpath = members_dir / f"members_{term}.parquet"
        if mpath.exists() and len(sub):
            m = pd.read_parquet(mpath, columns=["mona_cd", "member_name"])
            unseen = m[~m["mona_cd"].isin(sub["member_id"])]
            if len(unseen):
                log.info(f"    members_{term} members with no roll-call row: {len(unseen)} "
                         f"({', '.join(unseen['member_name'].astype(str))})")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_legacy_text(path: Path) -> pd.DataFrame:
    """Copy the shipped 16th-19th text/PDF rows unchanged (see module docstring)."""
    if not path.exists():
        log.warning(f"  {path} not found")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    text = df[df["source"].isin(TEXT_SOURCES)][LEGACY_COLS].copy()
    text["quality_flag"] = QUALITY_FLAG
    log.info(f"  16th-19th text/PDF rows from {path}: {len(text):,} "
             f"({ {int(k): v for k, v in text.groupby('term').size().items()} })")
    return text


def consolidate(out_dir: Path, members_dir: Path, legacy_text_from: Path):
    log.info("="*60)
    log.info("Consolidating roll call data")
    log.info("="*60)

    # Read the legacy rows first: out_dir may hold the file being replaced.
    text = load_legacy_text(legacy_text_from)

    api = load_api_votes()
    if api.empty:
        log.error("No API vote data found!")
        return
    api = attach_party(api, members_dir)
    for col in ["meeting_id", "bill_context", "agg_total", "agg_yes"]:
        api[col] = None
    api["vote_event"] = float("nan")
    api["term"] = api["term"].astype("Int64")
    api = api.sort_values(["term", "date", "bill_id", "member_id"],
                          kind="mergesort").reset_index(drop=True)
    api = api[ALL_SCHEMA.names]

    # Validation against the official tallies
    log.info("\n  Tally check (ncocpgfiaoituanbr)")
    check = tally_check(api, members_dir)
    reports = out_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    check.to_csv(reports / "rollcall_tally_check.csv", index=False)
    log.info(f"  Saved: reports/rollcall_tally_check.csv ({len(check):,} votes)")
    if not check.empty:
        bad = check[check["term"].isin(STRICT_TERMS)
                    & check["status"].isin(["mismatch", "no_tally", "no_member_rows"])]
        if len(bad):
            log.error(f"  {len(bad):,} votes of the {STRICT_TERMS} Assemblies disagree with "
                      f"the official tallies without an explanation. Not writing output.")
            sys.exit(1)

    # Summary
    log.info(f"\n{'='*60}")
    log.info("Consolidated Roll Call Dataset (API, 20-22대)")
    log.info(f"{'='*60}")
    log.info(f"  Total records: {len(api):,}")
    log.info(f"  Unique members: {api['member_id'].nunique():,}")
    log.info(f"\n  By assembly:")
    for term, sub in api.groupby("term"):
        log.info(f"    {int(term)}대: {len(sub):>9,} rows | {sub['member_id'].nunique():>3} members "
                 f"| {sub['bill_id'].nunique():>5,} recorded votes "
                 f"| party != party_api for "
                 f"{sub.loc[sub['party'] != sub['party_api'], 'member_id'].nunique()} members")
    log.info(f"\n  Vote distribution:")
    for vote_val, cnt in api["vote"].value_counts().items():
        log.info(f"    {vote_val}: {cnt:,}")

    # Save
    out_dir.mkdir(parents=True, exist_ok=True)
    outpath = out_dir / "roll_calls_all.parquet"
    write_table_atomic(api, ALL_SCHEMA, outpath)
    log.info(f"\n  Saved: {outpath} ({len(api):,} rows)")

    if text.empty:
        log.warning(f"  No 16th-19th rows found, {EXPERIMENTAL_NAME} not written")
    else:
        exp_path = out_dir / EXPERIMENTAL_NAME
        write_table_atomic(text, EXPERIMENTAL_SCHEMA, exp_path)
        log.info(f"  Saved: {exp_path} ({len(text):,} rows, quality_flag = {QUALITY_FLAG})")

    return api


def main():
    parser = argparse.ArgumentParser(description="Consolidate roll call votes")
    parser.add_argument("--out", type=Path, default=PROCESSED_DIR,
                        help="Output directory (default: data/processed)")
    parser.add_argument("--members-dir", type=Path, default=PROCESSED_DIR,
                        help="Directory with members_{term}.parquet (default: data/processed)")
    parser.add_argument("--legacy-text-from", type=Path, default=None,
                        help="File holding the shipped 16th-19th text/PDF rows (default: "
                             f"data/processed/{EXPERIMENTAL_NAME} if present, "
                             "else data/processed/roll_calls_all.parquet)")
    args = parser.parse_args()

    legacy = args.legacy_text_from
    if legacy is None:
        legacy = PROCESSED_DIR / EXPERIMENTAL_NAME
        if not legacy.exists():
            legacy = PROCESSED_DIR / "roll_calls_all.parquet"

    consolidate(args.out, args.members_dir, legacy)


if __name__ == "__main__":
    main()
