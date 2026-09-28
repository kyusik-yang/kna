"""Data loader for the kna master database."""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq


def _resolve_data_dir() -> Path:
    """Resolve the data directory in priority order."""
    # 1. Environment variable
    env = os.getenv("KBL_DATA")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
        warnings.warn(
            f"KBL_DATA={env!r} is not a directory; trying the default locations",
            stacklevel=2,
        )

    # 2. ./data/processed/ relative to repo root (adjacent to the kna/ package)
    repo_root = Path(__file__).resolve().parent.parent
    local = repo_root / "data" / "processed"
    if local.is_dir():
        return local

    # 3. data/processed/ under the working directory (an installed package run
    #    from the root of a repo checkout)
    cwd = Path.cwd() / "data" / "processed"
    if cwd.is_dir():
        return cwd

    # 4. ~/.cache/kna/
    cache = Path.home() / ".cache" / "kna"
    if cache.is_dir():
        return cache

    raise FileNotFoundError(
        "Cannot find data directory. Set KBL_DATA environment variable, "
        "or run from the kna repo root."
    )


ASSEMBLIES = [17, 18, 19, 20, 21, 22]

# Columns needed by each command (for column pruning). Columns missing from
# an older data vintage are skipped by the queries, not requested.
COLS_SEARCH = [
    "bill_id", "bill_no", "age", "bill_nm", "bill_kind",
    "ppsl_dt", "committee_nm", "rst_proposer", "ppsr_kind", "status",
    "law_reflected",
]
COLS_SHOW = [
    "bill_id", "bill_no", "age", "bill_nm", "bill_kind",
    "ppsr_kind", "proposer_text", "rst_proposer", "committee_nm", "status",
    "ppsl_dt", "committee_dt", "cmt_present_dt", "cmt_proc_dt",
    "cmt_proc_result_cd", "law_submit_dt", "law_cmmt_dt",
    "law_proc_dt", "rgs_rsln_dt", "rgs_conf_rslt", "prom_dt", "prom_no",
    "proc_dt", "vote_yes", "vote_no", "vote_abstain", "vote_member_total",
    "link_url", "passed", "enacted", "promulgated", "plenary_decided",
    "vetoed", "veto_bill_id", "veto_dt", "revote_rslt", "revote_dt",
    "first_plenary_rslt", "alt_bill_id",
]
COLS_LEGISLATOR = [
    "bill_id", "bill_no", "age", "bill_nm", "bill_kind", "ppsr_kind",
    "rst_proposer", "rst_mona_cd", "status", "passed", "enacted",
    "promulgated", "ppsl_dt", "proc_dt", "days_to_proc", "prom_dt",
]
COLS_STATS = [
    "bill_id", "age", "bill_kind", "ppsr_kind", "status",
    "passed", "enacted", "committee_nm",
    "ppsl_dt", "committee_dt", "cmt_present_dt", "cmt_proc_dt",
    "law_submit_dt", "law_cmmt_dt", "rgs_rsln_dt", "rgs_conf_rslt",
    "prom_dt", "days_to_proc", "plenary_decided", "promulgated",
]


def _meeting_col(name: str) -> str:
    """Harmonized name of a committee/judiciary meeting column.

    Files written before the 2026-09 rebuild store the 17th-21st columns in
    uppercase, with the requested bill id in _BILL_ID.
    """
    low = name.lower()
    return "bill_id_tagged" if low == "_bill_id" else low


class BillDB:
    """Lazy-loading interface to the kna master database."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else _resolve_data_dir()
        self._cache: dict[str, pd.DataFrame] = {}

    # ── helpers ─────────────────────────────────────────────────────

    def _path(self, fname: str) -> Path:
        p = self.data_dir / fname
        if not p.exists():
            raise FileNotFoundError(f"{fname} not found in {self.data_dir}")
        return p

    @staticmethod
    def _warn_unknown(label: str, missing: list[str]) -> None:
        if missing:
            warnings.warn(f"{label}: unknown column(s) ignored: {missing}", stacklevel=3)

    def _bill_path(self, age: int) -> Path:
        # Prefer full master, fall back to lite
        for suffix in ["", "_lite"]:
            p = self.data_dir / f"master_bills_{age}{suffix}.parquet"
            if p.exists():
                return p
        raise FileNotFoundError(f"No master file for {age}th assembly")

    def _load_table(
        self,
        fname: str,
        assembly: Optional[int] = None,
        age_col: str = "age",
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Read one parquet table, optionally filtered to one assembly."""
        key = f"{fname}_{assembly}_{tuple(columns) if columns else None}"
        if key not in self._cache:
            p = self._path(fname)
            read = None
            if columns is not None:
                names = pq.read_schema(p).names
                self._warn_unknown(fname, [c for c in columns if c not in names])
                read = [c for c in columns if c in names]
                if assembly is not None and age_col not in read:
                    read = read + [age_col]
            filters = [(age_col, "==", assembly)] if assembly is not None else None
            df = pd.read_parquet(p, columns=read, filters=filters)
            if columns is not None and age_col not in columns and age_col in df.columns:
                df = df.drop(columns=age_col)
            self._cache[key] = df.reset_index(drop=True)
        return self._cache[key]

    # ── bills ───────────────────────────────────────────────────────

    def bill_columns(self, assembly: int) -> list[str]:
        """Column names of one assembly's master file, read from its schema."""
        return pq.read_schema(self._bill_path(assembly)).names

    def bills(
        self,
        assembly: Optional[int] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load master bills, optionally for a single assembly.

        Args:
            assembly: 17-22, or None for all assemblies.
            columns: columns to read, returned in this order. Names missing
                from a master file are dropped with a warning.
        """
        ages = [assembly] if assembly else ASSEMBLIES
        if columns is not None:
            missing = {}
            for a in ages:
                names = set(self.bill_columns(a))
                for c in columns:
                    if c not in names:
                        missing.setdefault(c, []).append(a)
            if missing:
                detail = ", ".join(f"{c} (assembly {', '.join(map(str, a))})"
                                   for c, a in missing.items())
                warnings.warn(f"master_bills: unknown column(s) ignored: {detail}",
                              stacklevel=2)
        frames = [self._load_bills(a, columns) for a in ages]
        return pd.concat(frames, ignore_index=True)

    def _load_bills(self, age: int, columns: Optional[list[str]]) -> pd.DataFrame:
        p = self._bill_path(age)
        pruned = None
        if columns is not None:
            names = set(pq.read_schema(p).names)
            pruned = [c for c in columns if c in names]
        key = f"bills_{age}_{tuple(pruned) if pruned is not None else None}"
        if key not in self._cache:
            self._cache[key] = pd.read_parquet(p, columns=pruned)
        return self._cache[key]

    # ── votes and ideal points ──────────────────────────────────────

    def roll_calls(
        self,
        assembly: Optional[int] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load member-level roll call votes, 17th-22nd, one row per member per vote.

        ``vote_event_id`` identifies the vote in every assembly. The
        20th-22nd have source 'api' (nojepdqqaweusdfbi), plus 'likms' and
        'likms_absent' rows for the 22nd members the API omits, one row per
        (term, bill_id, member_id). The 17th-19th have source 'minutes_pdf',
        the name lists of the plenary minutes. There an amendment vote
        shares the bill_id of the bill it amends, the minutes list no
        absentees (no 불참 rows), and member_id is null where two members
        share the printed name and the minutes do not say which one voted.
        ``party`` is the party at election (members_{term}). ``party_api`` is
        the API's POLY_NM snapshot, null in the 17th-19th. The 16th rows are
        in roll_calls_16_19_experimental(). Filter by assembly for speed.
        ``term`` does not need to be among ``columns``.
        """
        return self._load_table("roll_calls_all.parquet", assembly, "term", columns)

    def roll_calls_16_19_experimental(self) -> pd.DataFrame:
        """Load the 16th Assembly vote rows parsed from speech text (EXPERIMENTAL).

        These rows are not a roll-call matrix. Do not use them as roll-call
        data without checking ``quality_flag``. The parser merged the votes
        of a plenary meeting into a few events and the consolidation kept one
        row per member per event, so a row is a member's position at some
        vote of the meeting. member_id came from a name match that can merge
        same-name legislators. Since 0.8.0 the file holds only the 16th, 923
        rows. The 17th-19th are in roll_calls(), rebuilt from the plenary
        minutes. No ideal-point series uses these rows. See CODEBOOK.md
        section 9 and CORRECTIONS.md.
        """
        return self._load_table("roll_calls_16_19_experimental.parquet")

    def vote_events(self, assembly: Optional[int] = None) -> pd.DataFrame:
        """Load every recorded plenary vote, one row per vote.

        The 20th-22nd hold the official tallies (source 'api'), the 17th-19th
        the recorded votes of the plenary minutes (source 'minutes_pdf'), with
        the chair's announced counts in chair_* columns and the flags
        chair_counts_differ and correction_note. vote_type is original,
        amendment, reversal, revote, reconsideration or other.
        vote_event_id joins to roll_calls() and master_bill_id links the vote
        to master_bills.
        """
        return self._load_table("vote_events.parquet", assembly)

    def veto_events(self, assembly: Optional[int] = None) -> pd.DataFrame:
        """Load presidential reconsideration requests (one row per vetoed bill)."""
        return self._load_table("veto_events.parquet", assembly)

    def ideal_points(self, series: str = "bridged") -> pd.DataFrame:
        """Load legislator ideal points (20th-22nd, one row per legislator-term).

        Three series are available and they are not interchangeable. See the
        "Ideal points" section of CODEBOOK.md before choosing. The 17th-19th
        roll calls are not scaled. In the 22nd, wnom2d_dim2 of
        ideal_points_wnominate.csv is unstable (CODEBOOK.md section 10.5).

        Args:
            series: which estimates to load.
                ``"bridged"`` (default) chained bridging alignment. Comparable
                    both within and across assemblies. Column ``ideal_point``.
                ``"wnominate"`` per-assembly W-NOMINATE. Comparable WITHIN an
                    assembly only; each term is separately renormalized, so
                    differences across terms mix real movement with rescaling.
                ``"dwnominate"`` pooled DW-NOMINATE. Comparable across
                    assemblies, but with only three terms the estimator admits
                    just a constant, so each legislator has one position for
                    all terms and within-legislator movement is zero.

        Returns:
            DataFrame with member_id, member_name, party, party_bloc, term,
            ideal_point, plus vintage in files built since 2026-09 (party is
            the party at election). Join to members on (member_id, term).
            Sign convention: positive = conservative, negative = liberal.
        """
        files = {
            "bridged": ("ideal_points_bridged.csv", "bridged_1d"),
            "wnominate": ("ideal_points_wnominate.csv", "wnom_1d"),
            "dwnominate": ("ideal_points_dwnominate.csv", "dwnom_1d"),
        }
        if series not in files:
            raise ValueError(
                f"unknown series {series!r}; choose from {sorted(files)}"
            )

        key = f"ip_{series}"
        if key not in self._cache:
            fname, col = files[series]
            p = self.data_dir / fname
            if not p.exists():
                raise FileNotFoundError(f"{fname} not found")
            df = pd.read_csv(p, dtype={"member_id": str})
            df = df.rename(columns={col: "ideal_point"})
            self._cache[key] = df
        return self._cache[key]

    # ── committee records ───────────────────────────────────────────

    def committee_meetings(
        self,
        assembly: int,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load committee meeting records (BILLJUDGECONF) for one assembly.

        Column names are lowercase for every assembly; the requested bill id
        (_BILL_ID in older files) is returned as ``bill_id_tagged``.
        """
        return self._load_meetings("committee_meetings", assembly, columns)

    def judiciary_meetings(
        self,
        assembly: int,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load 법제사법위원회 review records (BILLLWJUDGECONF) for one assembly.

        Same column conventions as committee_meetings().
        """
        return self._load_meetings("judiciary_meetings", assembly, columns)

    def _load_meetings(
        self, stem: str, assembly: int, columns: Optional[list[str]]
    ) -> pd.DataFrame:
        p = self.data_dir / f"{stem}_{assembly}.parquet"
        if not p.exists():
            raise FileNotFoundError(f"{stem}_{assembly}.parquet not found")
        actual = {_meeting_col(c): c for c in pq.read_schema(p).names}
        read = None
        if columns is not None:
            self._warn_unknown(p.name, [c for c in columns if c not in actual])
            read = [actual[c] for c in columns if c in actual]
        df = pd.read_parquet(p, columns=read)
        df.columns = [_meeting_col(c) for c in df.columns]
        return df

    def subcommittee_reviews(self, assembly: Optional[int] = None) -> pd.DataFrame:
        """Load subcommittee referrals and reviews (TVBPMCONFINFO), 17th-22nd."""
        return self._load_table("subcommittee_reviews.parquet", assembly)

    def alternative_absorption(self, assembly: Optional[int] = None) -> pd.DataFrame:
        """Load committee alternatives and the bills they absorbed (TVBPMBILL11).

        One row per (alt_bill_id, absorbed_bill_id).
        """
        return self._load_table("alternative_absorption.parquet", assembly)

    def committee_assignments(self, assembly: Optional[int] = None) -> pd.DataFrame:
        """Load dated committee assignment spells (mona_cd, committee, start/end)."""
        return self._load_table("committee_assignments.parquet", assembly, "assembly")

    def cosponsorship_edges(
        self,
        assembly: Optional[int] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load bill-member proposer edges (대표발의, 공동발의, 찬성), 17th-22nd."""
        return self._load_table("cosponsorship_edges.parquet", assembly, "age", columns)

    # ── other tables ────────────────────────────────────────────────

    def bill_texts(self) -> pd.DataFrame:
        """Load propose-reason texts (제안이유 및 주요내용), one row per bill.

        Law bills of the 17th-22nd, about 110K rows. Columns, lowercased:
        bill_id, propose_reason, scrape_status, age, bill_no and source.
        source is 'likms_scrape' for the texts scraped from LIKMS (20th-22nd
        member law bills) and 'BPMBILLSUMMARY' for the official API text
        (law bills of every proposer kind). The API texts keep a leading
        heading that the scraped texts lack. propose_reason is null only in
        scraped rows whose scrape failed and that the API does not fill.
        Files built before 0.8.0 hold only the scraped rows of the 20th-22nd
        and lack age, bill_no and source. Join to bills() on bill_id to
        filter by assembly.
        """
        if "texts" not in self._cache:
            p = self.data_dir / "bill_texts_linked.parquet"
            if not p.exists():
                raise FileNotFoundError("bill_texts_linked.parquet not found")
            df = pd.read_parquet(p)
            df.columns = df.columns.str.lower()
            self._cache["texts"] = df
        return self._cache["texts"]

    def members(
        self,
        assembly: Optional[int] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load member metadata, one row per member-term (17th-22nd).

        Every column of members_{age} is passed through: party (at election),
        party_end (end of term or departure) or party_current (22nd serving
        members), depending on the build, district, election_type,
        seniority and term_number (at that assembly), reelection (lifetime
        count at the snapshot), committee, is_current, snapshot_date, ...
        Older data vintages lack some of these columns.
        """
        ages = [assembly] if assembly else ASSEMBLIES
        frames = []
        missing: set[str] = set()
        for a in ages:
            p = self.data_dir / f"members_{a}.parquet"
            if p.exists():
                read = None
                if columns is not None:
                    names = set(pq.read_schema(p).names)
                    missing.update(c for c in columns if c not in names)
                    read = [c for c in columns if c in names]
                frames.append(pd.read_parquet(p, columns=read))
        if not frames:
            raise FileNotFoundError("No members_*.parquet files found")
        self._warn_unknown("members", sorted(missing))
        return pd.concat(frames, ignore_index=True)

    def assets(
        self,
        assembly: Optional[int] = None,
    ) -> pd.DataFrame:
        """Load legislator asset disclosure panel (776 members, 2015-2025).

        Returns member-year rows with the wealth variables of CODEBOOK.md
        section 16 (net_worth, total_realestate, total_stocks, etc.) in
        thousands of KRW, covering the 19th-22nd assemblies. Sources:
        OpenWatch (CC BY-SA 4.0) for wealth_year 2015-2024 and the official
        국회공보 of March 2026 for wealth_year 2025.
        """
        key = f"assets_{assembly}"
        if key not in self._cache:
            p = self.data_dir / "assets_wealth_panel.parquet"
            if not p.exists():
                raise FileNotFoundError("assets_wealth_panel.parquet not found")
            df = pd.read_parquet(p)
            if assembly is not None:
                df = df[df["assembly"] == assembly]
            self._cache[key] = df
        return self._cache[key]

    def legislator_map(self) -> pd.DataFrame:
        """Load legislator ID mapping table."""
        if "lm" not in self._cache:
            p = self.data_dir / "legislator_id_mapping.parquet"
            if not p.exists():
                return pd.DataFrame()
            self._cache["lm"] = pd.read_parquet(p)
        return self._cache["lm"]

    def file_info(self) -> list[dict]:
        """Get basic info about each assembly's data file.

        enacted counts every bill kind; laws, enacted_laws and promulgated
        count 법률안 only.
        """
        info = []
        for age in ASSEMBLIES:
            for suffix in ["", "_lite"]:
                p = self.data_dir / f"master_bills_{age}{suffix}.parquet"
                if p.exists():
                    names = pq.read_schema(p).names
                    want = [c for c in ["bill_kind", "enacted", "promulgated", "prom_dt"]
                            if c in names]
                    df = pd.read_parquet(p, columns=want)
                    law = df["bill_kind"] == "법률안"
                    if "promulgated" in df.columns:
                        prom = int(df["promulgated"].sum())
                    elif "prom_dt" in df.columns:
                        prom = int((law & df["prom_dt"].notna()).sum())
                    else:
                        prom = None
                    info.append({
                        "age": age,
                        "total": len(df),
                        "enacted": int(df["enacted"].sum()),
                        "laws": int(law.sum()),
                        "enacted_laws": int(df.loc[law, "enacted"].sum()),
                        "promulgated": prom,
                        "ncol": len(names),
                        "level": "Full" if suffix == "" else "Lite",
                    })
                    break
        return info
