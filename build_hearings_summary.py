"""
kna - Hearing meetings summary
==============================
Builds hearing_meetings_summary.parquet, one row per meeting of the
kr-hearings-data speech corpus.

Usage:
    python3 build_hearings_summary.py --source v9 --out data/_build \
        --compare data/processed/hearing_meetings_summary.parquet
    python3 build_hearings_summary.py --source v10 --out data/_build \
        --v10-dir ../kr-hearings-data/v10/build \
        --compare data/processed/hearing_meetings_summary.parquet

--source v9   reads all_speeches_16_22_v9.parquet from --v9-dir, or
              KNA_HEARINGS_DIR [../kr-hearings-data/data]. It reproduces the
              file shipped since 0.6.0, which link_external.py speeches wrote
              with the same aggregation (summarize_v9_speeches).
--source v10  reads the v10 release layout, meetings.parquet and
              turns/tNN/part-*.parquet (v10/code/pipeline/CONTRACT.md in
              kr-hearings-data), from --v10-dir, or KNA_HEARINGS_V10_DIR
              [../kr-hearings-data/v10/build].

Both sources give the same eight columns with the same types:
meeting_id, term, committee, hearing_type, date, n_speeches, n_legislators,
parties. A v10 table maps them as follows.

    meeting_id     conf_id, the Open API CONF_ID, verbatim. Most v9 IDs drop
                   its leading zero, so the two IDs differ.
    term           term
    committee      committee_raw, with "-" and audit_team appended when the
                   meeting has an audit team, the form v9 used for 국정감사.
                   Subcommittee meetings carry their parent committee.
    hearing_type   hearing_type, the six v9 values plus 특별위원회 and 전원위원회
    date           date
    n_speeches     merged speaker turns in the meeting
    n_legislators  distinct non-empty naas_cd among the turns
    parties        distinct non-empty party among the turns, sorted, comma-joined

Meetings without a turn are left out, as a v9 meeting without a speech had
no row. --compare REF prints how the new table differs from REF. A v10 table
is aligned with a v9 reference through the v9_meeting_id of meetings.parquet.
The script never writes into the kr-hearings-data directories.
"""

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parent
SIBLINGS = REPO.parent
V9_DIR = Path(os.environ.get("KNA_HEARINGS_DIR", SIBLINGS / "kr-hearings-data" / "data"))
V10_DIR = Path(os.environ.get("KNA_HEARINGS_V10_DIR", SIBLINGS / "kr-hearings-data" / "v10" / "build"))
V9_FILE = "all_speeches_16_22_v9.parquet"
OUT_NAME = "hearing_meetings_summary.parquet"

KEYS = ["meeting_id", "term", "committee", "hearing_type", "date"]
COLUMNS = KEYS + ["n_speeches", "n_legislators", "parties"]
V9_COLUMNS = KEYS + ["speaker", "naas_cd", "party"]
V10_MEETING_COLUMNS = ["conf_num", "conf_id", "v9_meeting_id", "term", "hearing_type",
                       "committee_raw", "date"]
V10_TURN_COLUMNS = ["conf_num", "naas_cd", "party"]


# ---------------------------------------------------------------------------
# v9: all_speeches_16_22_v9.parquet
# ---------------------------------------------------------------------------

def summarize_v9_speeches(speeches: pd.DataFrame) -> pd.DataFrame:
    """Meeting summary of v9 speech rows, as shipped since 0.6.0.

    groupby leaves out rows with a missing key, which in v9 are the 266
    speeches of meeting 43038 that have no term or date. An empty naas_cd
    counts as one legislator code, as in the shipped file.
    """
    return speeches.groupby(KEYS).agg(
        n_speeches=("speaker", "count"),
        n_legislators=("naas_cd", "nunique"),
        parties=("party", lambda x: ",".join(sorted(x.dropna().unique()))),
    ).reset_index()


def summarize_v9(path: Path) -> pd.DataFrame:
    speeches = pd.read_parquet(path, columns=V9_COLUMNS)
    print(f"  v9 speeches: {len(speeches):,} rows, {speeches['meeting_id'].nunique():,} meetings")
    no_key = speeches[KEYS].isna().any(axis=1)
    if no_key.any():
        ids = sorted(speeches.loc[no_key, "meeting_id"].unique())
        print(f"  {no_key.sum():,} speeches in {len(ids)} meeting(s) have a missing term, committee, "
              f"hearing_type or date and are left out: {ids[:10]}")
    return summarize_v9_speeches(speeches)


# ---------------------------------------------------------------------------
# v10: meetings.parquet + turns/tNN/part-*.parquet
# ---------------------------------------------------------------------------

def v10_build_info(v10_dir: Path) -> dict:
    """run_id and validation status of a v10 build, when its files say so."""
    info = {}
    manifest = v10_dir / "MANIFEST.json"
    if manifest.exists():
        m = json.loads(manifest.read_text(encoding="utf-8"))
        info.update(run_id=m.get("run_id"), generated_at=m.get("generated_at"))
    report = v10_dir / "validation_report.json"
    if report.exists():
        r = json.loads(report.read_text(encoding="utf-8"))
        info.update(validation_ok=r.get("ok"), validation_summary=r.get("summary"))
    return info


def summarize_v10_turns(turns: pd.DataFrame) -> pd.DataFrame:
    """n_speeches, n_legislators and parties per conf_num."""
    naas = turns["naas_cd"].where(turns["naas_cd"] != "")
    g = turns.assign(naas_cd=naas).groupby("conf_num")
    out = pd.DataFrame({"n_speeches": g.size(), "n_legislators": g["naas_cd"].nunique()})
    p = turns.loc[turns["party"].notna() & (turns["party"] != ""), ["conf_num", "party"]]
    parties = (p.drop_duplicates().sort_values(["conf_num", "party"])
               .groupby("conf_num")["party"].agg(",".join))
    out["parties"] = parties.reindex(out.index).fillna("")
    return out


def summarize_v10(v10_dir: Path) -> pd.DataFrame:
    """Meeting summary of a v10 build.

    Returns the eight COLUMNS plus v9_meeting_id, the key --compare uses to
    align the table with a v9 reference. It is not written to the output.
    """
    meetings = pd.read_parquet(v10_dir / "meetings.parquet")
    missing = [c for c in V10_MEETING_COLUMNS if c not in meetings.columns]
    if missing:
        raise SystemExit(f"ERROR: meetings.parquet lacks contract columns {missing}")
    for key in ("conf_num", "conf_id"):
        if meetings[key].isna().any() or meetings[key].duplicated().any():
            raise SystemExit(f"ERROR: meetings.parquet {key} is missing or duplicated")
    print(f"  v10 meetings: {len(meetings):,}")

    files = sorted((v10_dir / "turns").glob("t*/part-*.parquet"))
    if not files:
        raise SystemExit(f"ERROR: no turns/tNN/part-*.parquet under {v10_dir}")
    turns = pa.concat_tables([pq.read_table(f, columns=V10_TURN_COLUMNS) for f in files]).to_pandas()
    print(f"  v10 turns: {len(turns):,} rows in {len(files)} files")
    stray = set(turns["conf_num"]) - set(meetings["conf_num"])
    if stray:
        raise SystemExit(f"ERROR: {len(stray)} conf_num in turns are not in meetings.parquet, "
                         f"e.g. {sorted(stray)[:5]}")
    stats = summarize_v10_turns(turns)

    if "audit_team" in meetings.columns:
        team = meetings["audit_team"].where(meetings["audit_team"] != "")
    else:
        print("  WARNING: meetings.parquet has no audit_team, so 국정감사 committees get no team suffix")
        team = pd.Series(pd.NA, index=meetings.index, dtype="object")
    committee = meetings["committee_raw"].where(team.isna(), meetings["committee_raw"] + "-" + team)

    out = pd.DataFrame({
        "meeting_id": meetings["conf_id"],
        "term": meetings["term"].astype("Int64"),
        "committee": committee,
        "hearing_type": meetings["hearing_type"],
        "date": meetings["date"],
        "v9_meeting_id": meetings["v9_meeting_id"],
        "conf_num": meetings["conf_num"],
    })
    out = out.merge(stats, left_on="conf_num", right_index=True, how="inner")
    dropped = len(meetings) - len(out)
    if dropped:
        print(f"  {dropped:,} meeting(s) without a turn are left out")
    no_key = out[KEYS].isna().any(axis=1)
    if no_key.any():
        print(f"  {no_key.sum():,} meeting(s) with a missing term, committee, hearing_type or date "
              f"are left out: {out.loc[no_key, 'meeting_id'].tolist()[:10]}")
        out = out[~no_key]
    out = out.sort_values("meeting_id").reset_index(drop=True)
    for c in ("n_speeches", "n_legislators"):
        out[c] = out[c].astype("int64")
    return out[COLUMNS + ["v9_meeting_id"]]


# ---------------------------------------------------------------------------
# Comparison with a reference table
# ---------------------------------------------------------------------------

def compare(new: pd.DataFrame, ref: pd.DataFrame, key: str = "meeting_id") -> dict:
    """Differences between a new summary and a reference, aligned on new[key] = ref.meeting_id."""
    a = new[new[key].notna()].set_index(key)
    repeated = a.index[a.index.duplicated()].unique()
    if len(repeated):
        # Several new meetings name the same reference meeting. Compare the first
        # and count the others as new
        print(f"  WARNING: {len(repeated):,} {key} value(s) occur more than once in the new "
              f"table, only the first row of each is compared: {list(repeated[:5])}")
        a = a[~a.index.duplicated()]
    b = ref.set_index("meeting_id")
    common = a.index.intersection(b.index)
    res = {"rows_new": len(new), "rows_ref": len(ref), "matched": len(common),
           "only_new": int(len(new) - len(common)), "only_ref": int(len(b.index.difference(a.index))),
           "mismatch": {}}
    cols = [c for c in COLUMNS if c != "meeting_id"]
    if key != "meeting_id":
        # Aligned on another key, so meeting_id itself can differ
        b = b.assign(meeting_id=b.index)
        cols = ["meeting_id"] + cols
    for c in cols:
        x, y = a.loc[common, c], b.loc[common, c]
        if c == "term":
            x, y = x.astype("Int64"), y.astype("Int64")
        res["mismatch"][c] = int((x.astype(str) != y.astype(str)).sum())
    return res


def print_comparison(new: pd.DataFrame, ref: pd.DataFrame, res: dict):
    print(f"\n  Comparison with the reference ({res['rows_ref']:,} rows)")
    print(f"    new rows {res['rows_new']:,}, matched {res['matched']:,}, "
          f"only in new {res['only_new']:,}, only in reference {res['only_ref']:,}")
    for c, n in res["mismatch"].items():
        print(f"    {c:15s} differs in {n:>6,} matched meetings")
    per_term = pd.DataFrame({"new": new["term"].value_counts(), "reference": ref["term"].value_counts()})
    per_term = per_term.fillna(0).astype(int).sort_index()
    print("    meetings per term")
    for term, row in per_term.iterrows():
        print(f"      {term}: new {row['new']:>6,}  reference {row['reference']:>6,}")
    if list(new.columns[:len(COLUMNS)]) == COLUMNS and ref.columns.tolist() == COLUMNS:
        same_types = new[COLUMNS].dtypes.astype(str).tolist() == ref.dtypes.astype(str).tolist()
        print(f"    same columns and types: {same_types}")


def main():
    parser = argparse.ArgumentParser(description="Build hearing_meetings_summary.parquet")
    parser.add_argument("--source", choices=["v9", "v10"], required=True)
    parser.add_argument("--out", required=True, metavar="DIR",
                        help=f"output directory, written as DIR/{OUT_NAME}")
    parser.add_argument("--v9-dir", default=str(V9_DIR),
                        help=f"directory holding {V9_FILE} (env KNA_HEARINGS_DIR)")
    parser.add_argument("--v10-dir", default=str(V10_DIR),
                        help="v10 release directory with meetings.parquet and turns/ "
                             "(env KNA_HEARINGS_V10_DIR)")
    parser.add_argument("--compare", default=None,
                        help="reference summary to compare with, e.g. "
                             "data/processed/hearing_meetings_summary.parquet")
    args = parser.parse_args()

    print("=" * 60)
    print(f"Hearing meetings summary from kr-hearings-data {args.source}")
    print("=" * 60)
    if args.source == "v9":
        src = Path(args.v9_dir) / V9_FILE
        if not src.exists():
            raise SystemExit(f"ERROR: {src} not found. Set KNA_HEARINGS_DIR or --v9-dir")
        table, key = summarize_v9(src), "meeting_id"
    else:
        v10_dir = Path(args.v10_dir)
        if not (v10_dir / "meetings.parquet").exists():
            raise SystemExit(f"ERROR: {v10_dir / 'meetings.parquet'} not found. "
                             "Set KNA_HEARINGS_V10_DIR or --v10-dir")
        info = v10_build_info(v10_dir)
        print(f"  v10 build {v10_dir}: {info or 'no MANIFEST.json or validation_report.json'}")
        if info.get("validation_ok") is False:
            print("  WARNING: the v10 build did not pass its own validation")
        table, key = summarize_v10(v10_dir), "v9_meeting_id"

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table[COLUMNS].to_parquet(out / OUT_NAME, index=False)
    print(f"\n  Saved: {out / OUT_NAME} ({len(table):,} meetings)")

    if args.compare:
        ref = pd.read_parquet(args.compare)
        print_comparison(table, ref, compare(table, ref, key))

    print("\nDone.")


if __name__ == "__main__":
    main()
