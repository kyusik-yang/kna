"""Core query functions for kna.

All functions accept a BillDB instance and return DataFrames or dicts.
Shared by both CLI (cli.py) and MCP server (future).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from kna.data import BillDB, COLS_SEARCH, COLS_SHOW, COLS_LEGISLATOR, COLS_STATS


# ── Status filter mapping ───────────────────────────────────────────

STATUS_GROUPS = {
    "passed": ["원안가결", "수정가결", "대안반영폐기"],
    "enacted": ["원안가결", "수정가결"],
    "pending": ["계류중"],
    "rejected": ["부결", "폐기", "철회"],
}


# ── info ────────────────────────────────────────────────────────────

def db_info(db: BillDB) -> dict:
    """Gather database overview stats."""
    file_info = db.file_info()

    # Roll call count
    rc_path = db.data_dir / "roll_calls_all.parquet"
    rc_count = len(pd.read_parquet(rc_path, columns=["term"])) if rc_path.exists() else 0

    # Ideal point count
    ip_path = db.data_dir / "dw_ideal_points_20_22.csv"
    ip_count = len(pd.read_csv(ip_path, usecols=["member_id"])) if ip_path.exists() else 0

    # Committee meeting count
    cm_count = 0
    for age in range(17, 23):
        p = db.data_dir / f"committee_meetings_{age}.parquet"
        if p.exists():
            cm_count += len(pd.read_parquet(p, columns=[p.stem.split("_")[0] + "_id"]
                                            if False else None))
    # Simpler: just count rows
    cm_count = 0
    for age in range(17, 23):
        p = db.data_dir / f"committee_meetings_{age}.parquet"
        if p.exists():
            cm_count += pd.read_parquet(p).shape[0]

    # Freshness: latest ppsl_dt across all assemblies
    latest = None
    for info in file_info:
        age = info["age"]
        df = db.bills(age=age, columns=["ppsl_dt"])
        mx = df["ppsl_dt"].max()
        if pd.notna(mx) and (latest is None or mx > latest):
            latest = mx
    freshness = pd.Timestamp(latest).strftime("%Y-%m-%d") if pd.notna(latest) else "unknown"

    # Bill text count
    txt_path = db.data_dir / "bill_texts_linked.parquet"
    txt_count = len(pd.read_parquet(txt_path, columns=["BILL_ID"])) if txt_path.exists() else 0

    return {
        "file_info": file_info,
        "rc_count": rc_count,
        "ip_count": ip_count,
        "cm_count": cm_count,
        "txt_count": txt_count,
        "freshness": freshness,
    }


# ── search ──────────────────────────────────────────────────────────

def search_bills(
    db: BillDB,
    keyword: str,
    age: Optional[int] = None,
    committee: Optional[str] = None,
    proposer: Optional[str] = None,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 20,
) -> tuple[pd.DataFrame, int]:
    """Search bills by keyword and filters. Returns (results_df, total_count)."""
    df = db.bills(age=age, columns=COLS_SEARCH)

    # Keyword filter on bill_nm
    mask = df["bill_nm"].str.contains(keyword, case=False, na=False)
    df = df[mask]

    # Additional filters
    if committee:
        df = df[df["committee_nm"].str.contains(committee, case=False, na=False)]
    if proposer:
        df = df[df["rst_proposer"].str.contains(proposer, case=False, na=False)]
    if status and status in STATUS_GROUPS:
        df = df[df["status"].isin(STATUS_GROUPS[status])]
    if kind:
        df = df[df["bill_kind"] == kind]
    if date_from:
        df = df[df["ppsl_dt"] >= pd.Timestamp(date_from)]
    if date_to:
        df = df[df["ppsl_dt"] <= pd.Timestamp(date_to)]

    total = len(df)
    df = df.sort_values("ppsl_dt", ascending=False).head(limit)
    return df, total


# ── show ────────────────────────────────────────────────────────────

def get_bill_detail(db: BillDB, bill_ref: str) -> Optional[pd.Series]:
    """Look up a single bill by bill_no or bill_id, with propose-reason text."""
    df = db.bills(columns=COLS_SHOW)

    if bill_ref.startswith("PRC_") or bill_ref.startswith("ARC_"):
        match = df[df["bill_id"] == bill_ref]
    else:
        match = df[df["bill_no"] == bill_ref]

    if len(match) == 0:
        return None

    row = match.iloc[0]

    # Join propose-reason text if available
    try:
        texts = db.bill_texts()
        bill_id = row.get("bill_id")
        if bill_id:
            text_match = texts[texts["bill_id"] == bill_id]
            if len(text_match) > 0:
                row = row.copy()
                row["propose_reason"] = text_match.iloc[0]["propose_reason"]
    except FileNotFoundError:
        pass

    return row


# ── text search ─────────────────────────────────────────────────────

def search_bill_texts(
    db: BillDB,
    keyword: str,
    age: Optional[int] = None,
    limit: int = 20,
) -> tuple[pd.DataFrame, int]:
    """Search within propose-reason texts (full-text search)."""
    texts = db.bill_texts()
    bills = db.bills(age=age, columns=COLS_SEARCH)

    # Join texts to bills on bill_id
    merged = bills.merge(texts[["bill_id", "propose_reason"]], on="bill_id", how="inner")

    # Search in propose_reason
    mask = merged["propose_reason"].str.contains(keyword, case=False, na=False)
    results = merged[mask]

    total = len(results)
    results = results.sort_values("ppsl_dt", ascending=False).head(limit)
    return results, total


# ── legislator ──────────────────────────────────────────────────────

def get_legislator_profile(
    db: BillDB,
    name: str,
    age: Optional[int] = None,
    mona: Optional[str] = None,
) -> Optional[dict]:
    """Build legislator profile from bills, ideal points, and roll calls."""
    df = db.bills(age=age, columns=COLS_LEGISLATOR)

    if mona:
        bills = df[df["rst_mona_cd"] == mona]
    else:
        bills = df[df["rst_proposer"].str.contains(name, case=False, na=False)]

    if len(bills) == 0:
        return None

    # Determine actual age(s) and pick the first matching MONA_CD
    actual_mona = bills["rst_mona_cd"].dropna().mode()
    actual_mona = actual_mona.iloc[0] if len(actual_mona) > 0 else None

    # Ideal point (20-22nd only)
    ip = None
    rank = None
    total_in_term = None
    party = ""
    try:
        ip_df = db.ideal_points()
        if actual_mona:
            ip_match = ip_df[ip_df["member_id"] == actual_mona]
        else:
            ip_match = ip_df[ip_df["member_name"] == name]

        if age:
            ip_match = ip_match[ip_match["term"] == age]

        if len(ip_match) > 0:
            row = ip_match.iloc[0]
            ip = row["aligned"]
            party = row.get("party", "")
            # Rank within term
            term = row["term"]
            term_df = ip_df[ip_df["term"] == term].copy()
            term_df["rank"] = term_df["aligned"].rank(ascending=True).astype(int)
            my_rank = term_df[term_df["member_id"] == row["member_id"]]
            if len(my_rank) > 0:
                rank = int(my_rank.iloc[0]["rank"])
                total_in_term = len(term_df)
    except FileNotFoundError:
        pass

    # Top enacted bills
    top_enacted = bills[bills["enacted"] == 1].sort_values("ppsl_dt", ascending=False)

    return {
        "name": name,
        "age": age,
        "party": party,
        "ideal_point": ip,
        "rank": rank,
        "total_in_term": total_in_term,
        "bills_df": bills,
        "top_enacted": top_enacted,
    }


# ── stats: funnel ───────────────────────────────────────────────────

FUNNEL_STAGES = [
    ("발의", None),  # total count
    ("소관위 회부", "committee_dt"),
    ("소관위 상정", "cmt_present_dt"),
    ("소관위 처리", "cmt_proc_dt"),
    ("법사위 회부", "law_submit_dt"),
    ("본회의 의결", "rgs_rsln_dt"),
    ("공포", "prom_dt"),
]


def funnel_stats(db: BillDB, age: int) -> list[tuple[str, int]]:
    """Compute legislative funnel for a given assembly (법률안 only).

    For completed assemblies, rgs_rsln_dt is set to the term-end date
    for all expired bills (임기만료폐기). We exclude these to count
    only actual plenary votes.
    """
    df = db.bills(age=age, columns=COLS_STATS)
    bills = df[df["bill_kind"] == "법률안"]

    # Detect term-end date (most common rgs_rsln_dt is the expiry date)
    term_end = None
    if "rgs_rsln_dt" in bills.columns:
        mode = bills["rgs_rsln_dt"].dropna().mode()
        if len(mode) > 0:
            candidate = mode.iloc[0]
            count = (bills["rgs_rsln_dt"] == candidate).sum()
            # If > 50% of non-null values are the same date, it's the term-end
            if count > bills["rgs_rsln_dt"].notna().sum() * 0.3:
                term_end = candidate

    stages = []
    for label, col in FUNNEL_STAGES:
        if col is None:
            stages.append((label, len(bills)))
        elif col in bills.columns:
            if col == "rgs_rsln_dt" and term_end is not None:
                # Exclude term-end date (임기만료폐기)
                real_votes = bills[col].notna() & (bills[col] != term_end)
                stages.append((label, int(real_votes.sum())))
            else:
                stages.append((label, int(bills[col].notna().sum())))
        else:
            stages.append((label, 0))
    return stages


# ── stats: passage rate ─────────────────────────────────────────────

def passage_rate_stats(db: BillDB) -> list[dict]:
    """Compute passage/enactment rates across all assemblies."""
    results = []
    for age in [17, 18, 19, 20, 21, 22]:
        df = db.bills(age=age, columns=["bill_kind", "passed", "enacted"])
        bills = df[df["bill_kind"] == "법률안"]
        total = len(bills)
        passed = int(bills["passed"].sum())
        enacted = int(bills["enacted"].sum())
        results.append({
            "age": age,
            "total": total,
            "passed": passed,
            "pass_rate": passed / total * 100 if total else 0,
            "enacted": enacted,
            "enact_rate": enacted / total * 100 if total else 0,
        })
    return results


# ── export ──────────────────────────────────────────────────────────

def export_bills(
    db: BillDB,
    age: Optional[int] = None,
    committee: Optional[str] = None,
    status: Optional[str] = None,
    kind: Optional[str] = None,
) -> pd.DataFrame:
    """Export filtered bills for downstream analysis."""
    df = db.bills(age=age)

    if committee:
        df = df[df["committee_nm"].str.contains(committee, case=False, na=False)]
    if status and status in STATUS_GROUPS:
        df = df[df["status"].isin(STATUS_GROUPS[status])]
    if kind:
        df = df[df["bill_kind"] == kind]
    return df
