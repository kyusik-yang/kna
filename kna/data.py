"""Data loader for the kna master database."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd


def _resolve_data_dir() -> Path:
    """Resolve the data directory in priority order."""
    # 1. Environment variable
    env = os.getenv("KBL_DATA")
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    # 2. ./data/processed/ relative to repo root (adjacent to kbl/ package)
    repo_root = Path(__file__).resolve().parent.parent
    local = repo_root / "data" / "processed"
    if local.is_dir():
        return local

    # 3. ~/.cache/kbl/
    cache = Path.home() / ".cache" / "kna"
    if cache.is_dir():
        return cache

    raise FileNotFoundError(
        "Cannot find data directory. Set KBL_DATA environment variable, "
        "or run from the kna repo root."
    )


ASSEMBLIES = [17, 18, 19, 20, 21, 22]

# Columns needed by each command (for column pruning)
COLS_SEARCH = [
    "bill_id", "bill_no", "age", "bill_nm", "bill_kind",
    "ppsl_dt", "committee_nm", "rst_proposer", "ppsr_kind", "status",
]
COLS_SHOW = [
    "bill_id", "bill_no", "age", "bill_nm", "bill_kind",
    "ppsr_kind", "proposer_text", "rst_proposer", "committee_nm", "status",
    "ppsl_dt", "committee_dt", "cmt_present_dt", "cmt_proc_dt",
    "cmt_proc_result_cd", "law_submit_dt", "law_cmmt_dt",
    "law_proc_dt", "rgs_rsln_dt", "prom_dt", "prom_no",
    "vote_yes", "vote_no", "vote_abstain", "vote_member_total",
    "link_url", "passed", "enacted",
]
COLS_LEGISLATOR = [
    "bill_id", "bill_no", "age", "bill_nm", "ppsr_kind",
    "rst_proposer", "rst_mona_cd", "status", "passed", "enacted",
    "ppsl_dt", "proc_dt", "days_to_proc", "prom_dt",
]
COLS_STATS = [
    "bill_id", "age", "bill_kind", "ppsr_kind", "status",
    "passed", "enacted", "committee_nm",
    "ppsl_dt", "committee_dt", "cmt_present_dt", "cmt_proc_dt",
    "law_submit_dt", "rgs_rsln_dt", "prom_dt", "days_to_proc",
]


class BillDB:
    """Lazy-loading interface to the kna master database."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or _resolve_data_dir()
        self._cache: dict[str, pd.DataFrame] = {}

    def bills(
        self,
        assembly: Optional[int] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load master bills, optionally for a single assembly."""
        ages = [assembly] if assembly else ASSEMBLIES
        frames = [self._load_bills(a, columns) for a in ages]
        return pd.concat(frames, ignore_index=True)

    def _load_bills(self, age: int, columns: Optional[list[str]]) -> pd.DataFrame:
        col_key = tuple(sorted(columns)) if columns else ()
        key = f"bills_{age}_{hash(col_key)}"
        if key not in self._cache:
            # Prefer full master, fall back to lite
            for suffix in ["", "_lite"]:
                p = self.data_dir / f"master_bills_{age}{suffix}.parquet"
                if p.exists():
                    # Only request columns that actually exist in the file
                    if columns:
                        available = set(pd.read_parquet(p, columns=[]).columns)
                        pruned = [c for c in columns if c in available]
                        self._cache[key] = pd.read_parquet(p, columns=pruned or None)
                    else:
                        self._cache[key] = pd.read_parquet(p)
                    break
            else:
                raise FileNotFoundError(f"No master file for {age}th assembly")
        return self._cache[key]

    def roll_calls(
        self,
        assembly: Optional[int] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load roll call votes (2.4M rows). Filter by assembly for speed."""
        key = f"rc_{assembly}_{hash(tuple(sorted(columns or [])))}"
        if key not in self._cache:
            p = self.data_dir / "roll_calls_all.parquet"
            if not p.exists():
                raise FileNotFoundError("roll_calls_all.parquet not found")
            df = pd.read_parquet(p, columns=columns)
            if assembly is not None:
                df = df[df["term"] == assembly]
            self._cache[key] = df
        return self._cache[key]

    def ideal_points(self) -> pd.DataFrame:
        """Load DW-NOMINATE ideal points (936 legislator-terms, 20-22nd)."""
        if "ip" not in self._cache:
            p = self.data_dir / "dw_ideal_points_20_22.csv"
            if not p.exists():
                raise FileNotFoundError("dw_ideal_points_20_22.csv not found")
            df = pd.read_csv(p)
            # Flip sign: negative = liberal, positive = conservative
            df["aligned"] = -df["aligned"]
            self._cache["ip"] = df
        return self._cache["ip"]

    def committee_meetings(
        self,
        assembly: int,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Load committee meeting records for a given assembly."""
        p = self.data_dir / f"committee_meetings_{assembly}.parquet"
        if not p.exists():
            raise FileNotFoundError(f"committee_meetings_{assembly}.parquet not found")
        return pd.read_parquet(p, columns=columns)

    def bill_texts(self) -> pd.DataFrame:
        """Load bill propose-reason texts (60K bills, 20-22nd Assembly)."""
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
        """Load member metadata (party, district, committee, gender, etc.)."""
        ages = [assembly] if assembly else ASSEMBLIES
        frames = []
        for a in ages:
            p = self.data_dir / f"members_{a}.parquet"
            if p.exists():
                frames.append(pd.read_parquet(p, columns=columns))
        if not frames:
            raise FileNotFoundError("No members_*.parquet files found")
        return pd.concat(frames, ignore_index=True)

    def assets(
        self,
        assembly: Optional[int] = None,
    ) -> pd.DataFrame:
        """Load legislator asset disclosure panel (772 members, 2015-2024).

        Returns member-year rows with 37 wealth variables (net_worth,
        total_realestate, total_stocks, etc.) in thousands of KRW.
        Source: OpenWatch (CC BY-SA 4.0), covers 19th-22nd assemblies.
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
        """Get basic info about each assembly's data file."""
        info = []
        for age in ASSEMBLIES:
            for suffix in ["", "_lite"]:
                p = self.data_dir / f"master_bills_{age}{suffix}.parquet"
                if p.exists():
                    df = pd.read_parquet(p, columns=["bill_id", "enacted"])
                    info.append({
                        "age": age,
                        "total": len(df),
                        "enacted": int(df["enacted"].sum()),
                        "ncol": len(pd.read_parquet(p, columns=None).columns),
                        "level": "Full" if suffix == "" else "Lite",
                    })
                    break
        return info
