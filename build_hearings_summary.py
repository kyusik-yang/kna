"""
kna - Hearing meetings summary
==============================
Builds hearing_meetings_summary.parquet, one row per meeting of the
kr-hearings-data speech corpus.

Usage:
    python3 build_hearings_summary.py --source v10 --out data/_build \
        --compare data/processed/hearing_meetings_summary.parquet
    python3 build_hearings_summary.py --source v10 --out data/_build \
        --v10-dir ~/.cache/kr-hearings-data/v10.2
    python3 build_hearings_summary.py --source v10 --out data/_build --v10-package v10.2
    python3 build_hearings_summary.py --source v9 --out data/_build

--source v10  reads kr-hearings-data version 10 (v10, v10.1 or v10.2) in one of
              three forms:
              - a build directory with meetings.parquet and
                turns/tNN/part-*.parquet (--v10-dir, KNA_HEARINGS_V10_DIR, or
                by default ../kr-hearings-data/v10/build/release);
              - a directory of release assets, meetings_{v}.parquet and
                turns_t{16..22}_{v}.parquet, such as the cache of the
                kr-hearings-data package (--v10-dir, with --v10-version when
                it holds more than one version);
              - the kr-hearings-data package itself (--v10-package VERSION),
                which downloads the assets it needs.
--source v9   reads all_speeches_16_22_v9.parquet from --v9-dir, or
              KNA_HEARINGS_DIR [../kr-hearings-data/data]. It reproduces the
              file shipped in releases 0.6.0 to 0.8.0.

A v10 table has the eight v9 columns with the same types, plus conf_num and
is_subcommittee:

    meeting_id       conf_id, the Open API CONF_ID, verbatim. Most v9 IDs drop
                     its leading zero, so the two IDs differ. Null for the
                     meetings that no Open API list returns (187 in v10).
    term             term
    committee        committee_raw, with "-" and audit_team appended when the
                     meeting has an audit team, the form v9 used for 국정감사.
                     Subcommittee meetings carry their parent committee.
    hearing_type     hearing_type, the six v9 values plus 특별위원회 and 전원위원회
    date             date
    n_speeches       merged speaker turns in the meeting
    n_legislators    distinct non-empty naas_cd among the legislator-role turns
                     (role_group == "legislator")
    parties          distinct non-empty party among the legislator-role turns,
                     sorted, comma-joined
    conf_num         the record-viewer ID of the meeting, set for every meeting
    is_subcommittee  as in meetings.parquet

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
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parent
SIBLINGS = REPO.parent
V9_DIR = Path(os.environ.get("KNA_HEARINGS_DIR", SIBLINGS / "kr-hearings-data" / "data"))
V10_DIR = Path(os.environ.get("KNA_HEARINGS_V10_DIR",
                              SIBLINGS / "kr-hearings-data" / "v10" / "build" / "release"))
V9_FILE = "all_speeches_16_22_v9.parquet"
OUT_NAME = "hearing_meetings_summary.parquet"
V10_TERMS = range(16, 23)

KEYS = ["meeting_id", "term", "committee", "hearing_type", "date"]
COLUMNS = KEYS + ["n_speeches", "n_legislators", "parties"]
V10_EXTRA = ["conf_num", "is_subcommittee"]
V10_COLUMNS = COLUMNS + V10_EXTRA
V9_COLUMNS = KEYS + ["speaker", "naas_cd", "party"]
V10_MEETING_COLUMNS = ["conf_num", "conf_id", "v9_meeting_id", "term", "hearing_type",
                       "committee_raw", "date", "is_subcommittee"]
V10_TURN_COLUMNS = ["conf_num", "naas_cd", "party", "role_group"]


# ---------------------------------------------------------------------------
# v9: all_speeches_16_22_v9.parquet
# ---------------------------------------------------------------------------

def summarize_v9_speeches(speeches: pd.DataFrame) -> pd.DataFrame:
    """Meeting summary of v9 speech rows, as shipped in 0.6.0 to 0.8.0.

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
# v10: build directory, release assets or the kr-hearings-data package
# ---------------------------------------------------------------------------

def v10_layout(v10_dir: Path, version: str | None = None) -> tuple[str | None, str | None]:
    """("build", None), ("assets", version) or (None, None) for a directory."""
    if (v10_dir / "meetings.parquet").exists():
        return "build", None
    if version:
        return ("assets", version) if (v10_dir / f"meetings_{version}.parquet").exists() else (None, None)
    found = sorted(p.stem.removeprefix("meetings_") for p in v10_dir.glob("meetings_v*.parquet"))
    if len(found) > 1:
        raise SystemExit(f"ERROR: {v10_dir} holds several versions {found}. Pass --v10-version")
    return ("assets", found[0]) if found else (None, None)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def v10_build_info(v10_dir: Path, version: str | None = None) -> dict:
    """run_id and validation status of a v10 build or release, when its files say so."""
    suffix = f"_{version}" if version else ""
    info = {}
    m = _json(v10_dir / f"MANIFEST{suffix}.json")
    if m:
        # run_id sits under "run" in v10 manifests
        info.update(run_id=(m.get("run") or {}).get("run_id") or m.get("run_id"),
                    generated_at=m.get("generated_at"))
    r = _json(v10_dir / f"validation_report{suffix}.json")
    if r:
        info.update(validation_ok=r.get("ok"), validation_summary=r.get("summary"))
    return info


def _read_columns(path: Path, columns: list[str]) -> pd.DataFrame:
    have = set(pq.read_schema(path).names)
    missing = [c for c in columns if c not in have and c != "audit_team"]
    if missing:
        raise SystemExit(f"ERROR: {path.name} lacks the columns {missing}")
    return pq.read_table(path, columns=[c for c in columns if c in have]).to_pandas()


def load_v10(v10_dir: Path | None = None, version: str | None = None,
             package: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(meetings, turns, info) of kr-hearings-data v10, read-only."""
    mcols = V10_MEETING_COLUMNS + ["audit_team"]
    if package:
        import kr_hearings_data as khd
        meetings = khd.load_meetings(version=package)
        missing = [c for c in V10_MEETING_COLUMNS if c not in meetings.columns]
        if missing:
            raise SystemExit(f"ERROR: kr-hearings-data {package} meetings lack the columns {missing}")
        meetings = meetings[[c for c in mcols if c in meetings.columns]]
        turns = pd.concat([khd.load_turns(version=package, term=t, columns=V10_TURN_COLUMNS)
                           for t in V10_TERMS], ignore_index=True)
        return meetings, turns, {"layout": "package", "version": package}

    layout, version = v10_layout(v10_dir, version)
    if layout is None:
        raise SystemExit(f"ERROR: no meetings.parquet or meetings_v*.parquet in {v10_dir}. "
                         "Set KNA_HEARINGS_V10_DIR, --v10-dir or --v10-package")
    if layout == "build":
        meetings = _read_columns(v10_dir / "meetings.parquet", mcols)
        files = sorted((v10_dir / "turns").glob("t*/part-*.parquet"))
    else:
        meetings = _read_columns(v10_dir / f"meetings_{version}.parquet", mcols)
        files = [v10_dir / f"turns_t{t}_{version}.parquet" for t in V10_TERMS]
        absent = [f.name for f in files if not f.exists()]
        if absent:
            raise SystemExit(f"ERROR: {v10_dir} lacks {absent}")
    if not files:
        raise SystemExit(f"ERROR: no turn files under {v10_dir}")
    # Per file, so that an empty term file with null-typed columns does not clash
    turns = pd.concat([pq.read_table(f, columns=V10_TURN_COLUMNS).to_pandas() for f in files],
                      ignore_index=True)
    info = {"layout": layout, "version": version, "dir": str(v10_dir), "turn_files": len(files),
            **v10_build_info(v10_dir, version)}
    return meetings, turns, info


def summarize_v10_turns(turns: pd.DataFrame) -> pd.DataFrame:
    """n_speeches, n_legislators and parties per conf_num.

    n_speeches counts every turn. n_legislators and parties use the
    legislator-role turns only, so a minister who holds a seat does not count
    as a legislator in a meeting where they speak as minister.
    """
    out = pd.DataFrame({"n_speeches": turns.groupby("conf_num").size()})
    leg = turns[turns["role_group"] == "legislator"]
    code = leg["naas_cd"].where(leg["naas_cd"] != "")
    out["n_legislators"] = code.groupby(leg["conf_num"]).nunique().reindex(out.index).fillna(0)
    p = leg.loc[leg["party"].notna() & (leg["party"] != ""), ["conf_num", "party"]]
    parties = (p.drop_duplicates().sort_values(["conf_num", "party"])
               .groupby("conf_num")["party"].agg(",".join))
    out["parties"] = parties.reindex(out.index).fillna("")
    return out


def summarize_v10(meetings: pd.DataFrame, turns: pd.DataFrame) -> pd.DataFrame:
    """Meeting summary of v10 meetings and turns.

    Returns V10_COLUMNS plus v9_meeting_id, the key --compare uses to align
    the table with a v9 reference. v9_meeting_id is not written out.
    """
    missing = [c for c in V10_MEETING_COLUMNS if c not in meetings.columns]
    if missing:
        raise SystemExit(f"ERROR: the v10 meetings lack the columns {missing}")
    if meetings["conf_num"].isna().any() or meetings["conf_num"].duplicated().any():
        raise SystemExit("ERROR: the v10 meetings have a missing or repeated conf_num")
    conf_id = meetings["conf_id"].dropna()
    if conf_id.duplicated().any():
        raise SystemExit("ERROR: the v10 meetings have a repeated conf_id")
    n_null = int(meetings["conf_id"].isna().sum())
    print(f"  v10 meetings: {len(meetings):,} ({n_null:,} without a conf_id keep a null meeting_id)")
    print(f"  v10 turns: {len(turns):,}")
    stray = set(turns["conf_num"]) - set(meetings["conf_num"])
    if stray:
        raise SystemExit(f"ERROR: {len(stray)} conf_num in turns are not in the meetings, "
                         f"e.g. {sorted(stray)[:5]}")
    stats = summarize_v10_turns(turns)

    if "audit_team" in meetings.columns:
        team = meetings["audit_team"].where(meetings["audit_team"] != "")
    else:
        print("  WARNING: the v10 meetings have no audit_team, so 국정감사 committees get no team suffix")
        team = pd.Series(pd.NA, index=meetings.index, dtype="object")
    committee = meetings["committee_raw"].where(team.isna(), meetings["committee_raw"] + "-" + team)

    out = pd.DataFrame({
        "meeting_id": meetings["conf_id"],
        "term": meetings["term"].astype("Int64"),
        "committee": committee,
        "hearing_type": meetings["hearing_type"],
        "date": meetings["date"],
        "conf_num": meetings["conf_num"].astype("int64"),
        "is_subcommittee": meetings["is_subcommittee"].astype(bool),
        "v9_meeting_id": meetings["v9_meeting_id"],
    })
    out = out.merge(stats, left_on="conf_num", right_index=True, how="inner")
    dropped = len(meetings) - len(out)
    if dropped:
        print(f"  {dropped:,} meeting(s) without a turn are left out")
    no_key = out[KEYS[1:]].isna().any(axis=1)
    if no_key.any():
        print(f"  {no_key.sum():,} meeting(s) with a missing term, committee, hearing_type or date "
              f"are left out: conf_num {out.loc[no_key, 'conf_num'].tolist()[:10]}")
        out = out[~no_key]
    out = out.sort_values(["meeting_id", "conf_num"], na_position="last").reset_index(drop=True)
    for c in ("n_speeches", "n_legislators"):
        out[c] = out[c].astype("int64")
    return out[V10_COLUMNS + ["v9_meeting_id"]]


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
    shared = [c for c in COLUMNS if c in ref.columns]
    if list(new.columns[:len(COLUMNS)]) == COLUMNS and shared == COLUMNS:
        same_types = (new[COLUMNS].dtypes.astype(str).tolist()
                      == ref[COLUMNS].dtypes.astype(str).tolist())
        print(f"    same types in the eight shared columns: {same_types}")


def main():
    parser = argparse.ArgumentParser(description="Build hearing_meetings_summary.parquet")
    parser.add_argument("--source", choices=["v9", "v10"], required=True)
    parser.add_argument("--out", required=True, metavar="DIR",
                        help=f"output directory, written as DIR/{OUT_NAME}")
    parser.add_argument("--v9-dir", default=str(V9_DIR),
                        help=f"directory holding {V9_FILE} (env KNA_HEARINGS_DIR)")
    parser.add_argument("--v10-dir", default=str(V10_DIR),
                        help="v10 build directory (meetings.parquet, turns/) or a directory of "
                             "release assets (meetings_{v}.parquet, turns_t{NN}_{v}.parquet) "
                             "(env KNA_HEARINGS_V10_DIR)")
    parser.add_argument("--v10-version", default=None,
                        help="release version to read from an asset directory, e.g. v10.2")
    parser.add_argument("--v10-package", default=None, metavar="VERSION",
                        help="read through the kr-hearings-data package instead, e.g. v10.2")
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
        table, key, columns = summarize_v9(src), "meeting_id", COLUMNS
    else:
        meetings, turns, info = load_v10(Path(args.v10_dir).expanduser(), args.v10_version,
                                         args.v10_package)
        print(f"  v10 source: {info}")
        if info.get("validation_ok") is False:
            print("  WARNING: the v10 build did not pass its own validation")
        table, key, columns = summarize_v10(meetings, turns), "v9_meeting_id", V10_COLUMNS

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table[columns].to_parquet(out / OUT_NAME, index=False)
    print(f"\n  Saved: {out / OUT_NAME} ({len(table):,} meetings)")

    if args.compare:
        ref = pd.read_parquet(args.compare)
        print_comparison(table, ref, compare(table, ref, key))

    print("\nDone.")


if __name__ == "__main__":
    main()
