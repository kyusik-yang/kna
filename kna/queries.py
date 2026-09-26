"""Core query functions for kna.

All functions accept a BillDB instance and return DataFrames or dicts.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq

from kna.data import (
    ASSEMBLIES, BillDB, COLS_LEGISLATOR, COLS_SEARCH, COLS_SHOW, COLS_STATS,
)


# ── Status filter mapping ───────────────────────────────────────────

# passed and enacted match the master columns of the same name. reflected
# adds 수정안반영폐기 (content taken into a floor amendment) and, where the
# law_reflected column exists, drops bills absorbed into a vetoed alternative.
STATUS_GROUPS = {
    "passed": ["원안가결", "수정가결", "대안반영폐기"],
    "enacted": ["원안가결", "수정가결"],
    "reflected": ["원안가결", "수정가결", "대안반영폐기", "수정안반영폐기"],
    "pending": ["계류중"],
    "rejected": ["부결", "폐기", "철회"],
    "expired": ["임기만료폐기"],
}
STATUS_FLAGS = {"reflected": "law_reflected"}

PLENARY_RESULTS = ["원안가결", "수정가결", "부결"]


def _status_mask(df: pd.DataFrame, status: str) -> pd.Series:
    mask = df["status"].isin(STATUS_GROUPS[status])
    flag = STATUS_FLAGS.get(status)
    if flag and flag in df.columns:
        mask &= df[flag] == 1
    return mask


def _cols(db: BillDB, age: int, wanted: list[str]) -> list[str]:
    """The wanted columns that exist in this assembly's master file."""
    names = set(db.bill_columns(age))
    return [c for c in wanted if c in names]


def _bills(db: BillDB, age: Optional[int], wanted: list[str]) -> pd.DataFrame:
    """Load bills with only the columns that exist, so no warning is raised."""
    ages = [age] if age else ASSEMBLIES
    return pd.concat([db.bills(assembly=a, columns=_cols(db, a, wanted)) for a in ages],
                     ignore_index=True)


def _nrows(path) -> int:
    return pq.read_metadata(path).num_rows if path.exists() else 0


# ── info ────────────────────────────────────────────────────────────

def db_info(db: BillDB) -> dict:
    """Gather database overview stats."""
    file_info = db.file_info()
    d = db.data_dir

    # Roll calls: 20th-22nd API votes; the 16th-19th rows are a separate file
    rc_count = _nrows(d / "roll_calls_all.parquet")
    rc_exp_count = _nrows(d / "roll_calls_16_19_experimental.parquet")

    # Ideal point count
    # Default series is the bridged alignment (see CODEBOOK.md "Ideal Points");
    # dw_ideal_points_20_22.csv is deprecated and must not be read.
    ip_path = d / "ideal_points_bridged.csv"
    ip_count, ip_vintage = 0, ""
    if ip_path.exists():
        ip = pd.read_csv(ip_path)
        ip_count = len(ip)
        if "vintage" in ip.columns and ip["vintage"].notna().any():
            ip_vintage = str(ip["vintage"].dropna().iloc[0])

    cm_count = sum(_nrows(d / f"committee_meetings_{a}.parquet") for a in ASSEMBLIES)
    mem_count = sum(_nrows(d / f"members_{a}.parquet") for a in ASSEMBLIES)

    # Freshness: latest ppsl_dt across all assemblies
    latest = None
    for info in file_info:
        df = db.bills(assembly=info["age"], columns=["ppsl_dt"])
        mx = df["ppsl_dt"].max()
        if pd.notna(mx) and (latest is None or mx > latest):
            latest = mx
    freshness = pd.Timestamp(latest).strftime("%Y-%m-%d") if pd.notna(latest) else "unknown"

    txt_count = _nrows(d / "bill_texts_linked.parquet")
    asset_count = _nrows(d / "assets_wealth_panel.parquet")

    # Structural tables added in 2026-09 (absent from older data vintages)
    tables = [
        ("Cosponsor edges", "cosponsorship_edges.parquet", "17-22nd, 대표/공동발의 + 찬성"),
        ("Subcommittee", "subcommittee_reviews.parquet", "17-22nd, 소위 referrals/reviews"),
        ("Alt. absorption", "alternative_absorption.parquet", "17-22nd, 대안 -> absorbed bills"),
        ("Committee spells", "committee_assignments.parquet", "dated committee assignments"),
        ("Vote tallies", "vote_events.parquet", "20-22nd, plenary tallies"),
        ("Veto events", "veto_events.parquet", "17-22nd, 재의요구"),
    ]
    extra = [(label, _nrows(d / f), note) for label, f, note in tables if (d / f).exists()]

    return {
        "file_info": file_info,
        "rc_count": rc_count,
        "rc_exp_count": rc_exp_count,
        "ip_count": ip_count,
        "ip_vintage": ip_vintage,
        "cm_count": cm_count,
        "txt_count": txt_count,
        "mem_count": mem_count,
        "asset_count": asset_count,
        "freshness": freshness,
        "extra": extra,
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
    df = _bills(db, age, COLS_SEARCH)

    # Keyword filter on bill_nm
    mask = df["bill_nm"].str.contains(keyword, case=False, na=False)
    df = df[mask]

    # Additional filters
    if committee:
        df = df[df["committee_nm"].str.contains(committee, case=False, na=False)]
    if proposer:
        # Exact name among the comma-joined lead proposers, so 김현 does not
        # match 김현정 and a joint lead still matches
        df = df[_has_code(df["rst_proposer"], proposer.strip())]
    if status and status in STATUS_GROUPS:
        df = df[_status_mask(df, status)]
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
    df = _bills(db, None, COLS_SHOW)

    bill_ref = bill_ref.strip()
    if bill_ref.startswith(("PRC_", "ARC_", "GOV_")):
        match = df[df["bill_id"] == bill_ref]
        if len(match) == 0 and "veto_bill_id" in df.columns:
            # A reconsideration (재의요구) record is folded into its original bill
            match = df[df["veto_bill_id"] == bill_ref]
    else:
        match = df[df["bill_no"] == bill_ref]
        if len(match) == 0:
            # 17th-assembly bill_ids are plain numbers
            match = df[df["bill_id"] == bill_ref]

    if len(match) == 0:
        return None

    row = match.iloc[0]

    # A vetoed bill without a BILLINFODETAIL row has no rgs_rsln_dt; its first
    # floor passage date is kept in veto_events
    vetoed = row.get("vetoed")
    if pd.notna(vetoed) and int(vetoed) == 1 and pd.isna(row.get("rgs_rsln_dt")):
        try:
            ve = db.veto_events(int(row["age"]))
            hit = ve.loc[ve["bill_id"] == row["bill_id"], "first_plenary_dt"].dropna()
            if len(hit) > 0:
                row = row.copy()
                row["first_plenary_dt"] = hit.iloc[0]
        except FileNotFoundError:
            pass

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
    bills = _bills(db, age, COLS_SEARCH)

    # Join texts to bills on bill_id
    merged = bills.merge(texts[["bill_id", "propose_reason"]], on="bill_id", how="inner")

    # Search in propose_reason
    mask = merged["propose_reason"].str.contains(keyword, case=False, na=False)
    results = merged[mask]

    total = len(results)
    results = results.sort_values("ppsl_dt", ascending=False).head(limit)
    return results, total


# ── legislator ──────────────────────────────────────────────────────

class AmbiguousLegislator(LookupError):
    """More than one legislator matches a name. Pass mona= to pick one."""

    def __init__(self, name: str, age: Optional[int], candidates: pd.DataFrame):
        self.name = name
        self.age = age
        self.candidates = candidates
        n = candidates["mona_cd"].nunique()
        scope = f"assembly {age}" if age else "assemblies 17-22"
        super().__init__(
            f"{n} legislators named {name!r} in {scope}; pass mona= "
            f"({', '.join(candidates['mona_cd'].unique())})"
        )


def resolve_legislator(
    db: BillDB,
    name: str,
    age: Optional[int] = None,
    mona: Optional[str] = None,
) -> pd.DataFrame:
    """Member rows (one per assembly) of the legislator meant by name or mona.

    The name is matched exactly against members_{assembly}, never as a
    substring. With mona, the MONA_CD decides and the name is not checked.
    Raises AmbiguousLegislator when more than one MONA_CD matches. Returns an
    empty frame when nothing matches.
    """
    mem = db.members(assembly=age)
    if mona:
        rows = mem[mem["mona_cd"] == mona.strip()]
    else:
        rows = mem[mem["member_name"].str.strip() == name.strip()]
    rows = rows.sort_values(["age", "mona_cd"]).reset_index(drop=True)
    if rows["mona_cd"].nunique() > 1:
        cols = [c for c in ["mona_cd", "member_name", "age", "party", "district",
                            "election_type"] if c in rows.columns]
        raise AmbiguousLegislator(name, age, rows[cols])
    return rows


def suggest_legislators(
    db: BillDB, name: str, age: Optional[int] = None, limit: int = 8
) -> list[str]:
    """Member names that contain the query or are contained in it (hints only)."""
    try:
        names = db.members(assembly=age, columns=["member_name"])["member_name"].dropna()
    except FileNotFoundError:
        return []
    q = name.strip()
    if not q:
        return []
    hits = sorted({n for n in names.unique() if n != q and (q in n or n in q)})
    return hits[:limit]


def _has_code(codes: pd.Series, mona: str) -> pd.Series:
    """True where mona is one of the comma-separated tokens (joint leads).

    Used for rst_mona_cd codes and for rst_proposer names alike.
    """
    pat = rf"(?:^|,)\s*{re.escape(mona)}\s*(?:,|$)"
    return codes.fillna("").str.contains(pat, regex=True)


def legislator_bills(db: BillDB, mona: str, ages: list[int]) -> pd.DataFrame:
    """Bills led by mona (sole or joint lead proposer) in the given assemblies."""
    frames = []
    for a in ages:
        df = db.bills(assembly=a, columns=_cols(db, a, COLS_LEGISLATOR))
        if "rst_mona_cd" in df.columns:
            frames.append(df[_has_code(df["rst_mona_cd"], mona)])
    if not frames:
        return pd.DataFrame(columns=COLS_LEGISLATOR)
    return pd.concat(frames, ignore_index=True)


def _term_ideal_points(db: BillDB, mona: str) -> pd.DataFrame:
    """Bridged ideal point and within-term rank of mona, one row per term.

    Rank 1 is the most liberal legislator of the term.
    """
    ip_df = db.ideal_points()
    ranked = ip_df.assign(
        rank=ip_df.groupby("term")["ideal_point"].rank(ascending=True, method="min"),
        total_in_term=ip_df.groupby("term")["ideal_point"].transform("size"),
    )
    cols = ["term", "ideal_point", "rank", "total_in_term"]
    if "vintage" in ranked.columns:
        cols.append("vintage")
    out = ranked.loc[ranked["member_id"] == mona, cols].copy()
    out["rank"] = out["rank"].astype(int)
    return out.rename(columns={"term": "age"})


def _clean(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def get_legislator_profile(
    db: BillDB,
    name: str,
    age: Optional[int] = None,
    mona: Optional[str] = None,
) -> Optional[dict]:
    """Build a legislator profile from members, bills and ideal points.

    The legislator is resolved exactly (resolve_legislator), bills are the
    ones whose rst_mona_cd list contains the MONA_CD, and ideal points are
    reported per term. Without age the profile covers every term served;
    the header metadata then describes the latest term. Returns None when
    no member matches; raises AmbiguousLegislator for shared names.
    """
    rows = resolve_legislator(db, name, age=age, mona=mona)
    if len(rows) == 0:
        return None

    mona_cd = rows["mona_cd"].iloc[0]
    ages = sorted(int(a) for a in rows["age"].unique())

    # Per-term metadata and ideal points
    terms = rows.copy()
    if "seniority" not in terms.columns:
        # Older member files only have the lifetime count at the snapshot
        terms["seniority"] = None
    try:
        ip = _term_ideal_points(db, mona_cd)
        terms = terms.merge(ip, on="age", how="left")
    except FileNotFoundError:
        terms["ideal_point"] = None
    cur = terms.iloc[-1]  # the requested term, or the latest one

    bills = legislator_bills(db, mona_cd, ages)
    top_enacted = bills[bills["enacted"] == 1].sort_values("ppsl_dt", ascending=False) \
        if "enacted" in bills.columns else bills.iloc[0:0]

    ip_val = cur.get("ideal_point")
    has_ip = ip_val is not None and pd.notna(ip_val)
    return {
        "name": _clean(cur.get("member_name")) or name,
        "mona": mona_cd,
        "age": age,
        "term": int(cur["age"]),
        "party": _clean(cur.get("party")),
        "party_current": _clean(cur.get("party_current")),
        "party_end": _clean(cur.get("party_end")),
        "district": _clean(cur.get("district")),
        "committee": _clean(cur.get("committee")),
        "sex": _clean(cur.get("sex")),
        "election_type": _clean(cur.get("election_type")),
        "seniority": _clean(cur.get("seniority")),
        "reelection": _clean(cur.get("reelection")),
        "ideal_point": float(ip_val) if has_ip else None,
        "rank": int(cur["rank"]) if has_ip else None,
        "total_in_term": int(cur["total_in_term"]) if has_ip else None,
        "ip_vintage": _clean(cur.get("vintage")) if has_ip else "",
        "terms": terms,
        "bills_df": bills,
        "top_enacted": top_enacted,
    }


# ── stats: funnel ───────────────────────────────────────────────────

# A stage is reached when any of its markers is set. Markers are date columns,
# or 0/1 flags (plenary_decided, promulgated).
FUNNEL_STAGES = [
    ("발의", None),  # total count
    ("소관위 회부", ["committee_dt"]),
    ("소관위 상정", ["cmt_present_dt"]),
    ("소관위 처리", ["cmt_proc_dt"]),
    ("법사위 회부", ["law_submit_dt", "law_cmmt_dt"]),
    ("본회의 의결", ["plenary_decided"]),
    ("공포", ["promulgated"]),
]


def _stage_markers(bills: pd.DataFrame, cols: list[str]) -> pd.Series:
    hit = pd.Series(False, index=bills.index)
    for col in cols:
        if col == "plenary_decided" and col not in bills.columns:
            # Older masters: a floor decision is 원안가결, 수정가결 or 부결
            src = "rgs_conf_rslt" if "rgs_conf_rslt" in bills.columns else "status"
            hit |= bills[src].isin(PLENARY_RESULTS)
        elif col == "promulgated" and col not in bills.columns:
            hit |= bills["prom_dt"].notna() if "prom_dt" in bills.columns else False
        elif col in ("plenary_decided", "promulgated"):
            hit |= bills[col] == 1
        elif col in bills.columns:
            hit |= bills[col].notna()
    return hit


def funnel_stats(db: BillDB, age: int) -> list[tuple[str, int]]:
    """Compute legislative funnel for a given assembly (법률안 only).

    Each stage counts the bills that reached it or any later stage, so the
    funnel never widens. Some bills skip stages: committee alternatives
    (위원장 대안) are never referred to a committee, and bills of the
    법제사법위원회 itself skip the 법사위 review. The plenary stage is a floor
    decision (plenary_decided: 원안가결, 수정가결 or 부결), not rgs_rsln_dt,
    which is the final disposition date of every processed bill.
    """
    df = _bills(db, age, COLS_STATS)
    bills = df[df["bill_kind"] == "법률안"]

    marks = [(label, _stage_markers(bills, cols) if cols else None)
             for label, cols in FUNNEL_STAGES]
    stages = []
    later = pd.Series(False, index=bills.index)
    for label, hit in reversed(marks):
        if hit is None:
            stages.append((label, len(bills)))
            continue
        later = later | hit
        stages.append((label, int(later.sum())))
    return stages[::-1]


# ── stats: passage rate ─────────────────────────────────────────────

def passage_rate_stats(db: BillDB) -> list[dict]:
    """Compute passage, enactment and promulgation rates (법률안 only)."""
    results = []
    for age in ASSEMBLIES:
        df = db.bills(assembly=age, columns=_cols(
            db, age, ["bill_kind", "passed", "enacted", "promulgated", "prom_dt"]))
        bills = df[df["bill_kind"] == "법률안"]
        total = len(bills)
        passed = int(bills["passed"].sum())
        enacted = int(bills["enacted"].sum())
        if "promulgated" in bills.columns:
            prom = int(bills["promulgated"].sum())
        elif "prom_dt" in bills.columns:
            prom = int(bills["prom_dt"].notna().sum())
        else:
            prom = 0
        results.append({
            "age": age,
            "total": total,
            "passed": passed,
            "pass_rate": passed / total * 100 if total else 0,
            "enacted": enacted,
            "enact_rate": enacted / total * 100 if total else 0,
            "promulgated": prom,
            "prom_rate": prom / total * 100 if total else 0,
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
    df = db.bills(assembly=age)

    if committee:
        df = df[df["committee_nm"].str.contains(committee, case=False, na=False)]
    if status and status in STATUS_GROUPS:
        df = df[_status_mask(df, status)]
    if kind:
        df = df[df["bill_kind"] == kind]
    return df
