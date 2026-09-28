"""
kna - Data Integration
==================================================
Build the bill master of every assembly (17th-22nd) from data/raw.

One builder for all assemblies. Per assembly it writes
  master_bills_{age}.parquet        one row per bill (LEGACY_COLS + NEW_COLS)
  committee_meetings_{age}.parquet  BILLJUDGECONF, lowercase, exact duplicates dropped
  judiciary_meetings_{age}.parquet  BILLLWJUDGECONF, same treatment
  master_bills_{age}_lite.parquet   17-21 only, the legacy lite column subset
  master_bills_22.sqlite            bills + meeting tables (22nd only)
and across assemblies
  veto_events.parquet               one row per presidential reconsideration request
  vote_events.parquet               every plenary tally (20th-22nd, source 'api') and every
                                    recorded vote of the minutes appendices (17th-19th,
                                    source 'minutes_pdf') with its vote type

Universe: BILLRCP (ERACO filter) + member bills (nzmimeepazxkubdpn) + processed
bills (nzpltgfqabtcpsmai). A vetoed bill appears under two BILL_IDs that share
its BILL_NO: the original record and the reconsideration (재의요구) record
(GOV_ prefix, or PPSR 대통령). Each pair is folded into one row that keeps the
original bill and takes its final result from the reconsideration: proc_rslt,
proc_dt and status follow the re-vote (none yet: pending in the 22nd, expired
otherwise), while rgs_*, first_plenary_rslt and the vote_* columns keep the
first floor passage.

Usage:
    python3 integrate.py                                 # all assemblies -> data/processed
    python3 integrate.py --ages 17-22 --out data/_build
    python3 integrate.py --age 22                        # one assembly
    python3 integrate.py --ages 17-22 --out data/_build --compare data/processed
"""

import argparse
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ── Configuration ──────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

ALL_AGES = list(range(17, 23))
CURRENT_AGE = 22        # the sitting assembly: unresolved bills are pending, not expired
SQLITE_AGES = {22}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "integrate.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── Output schema ──────────────────────────────────────────────────────────

LEGACY_COLS = [
    "bill_id", "bill_no", "age", "bill_kind", "bill_nm",
    "ppsr_kind", "proposer_text", "rst_proposer", "rst_mona_cd",
    "publ_proposer", "publ_mona_cd",
    "ppsl_dt", "committee_dt", "bdg_cmmt_dt",
    "cmt_present_dt", "jrcmit_prsnt_dt", "jrcmit_cmmt_dt",
    "cmt_proc_dt", "jrcmit_proc_dt",
    "law_submit_dt", "law_cmmt_dt",
    "law_present_dt", "law_prsnt_dt",
    "law_proc_dt",
    "rgs_prsnt_dt", "rgs_rsln_dt",
    "gvrn_trsf_dt", "prom_dt", "proc_dt",
    "jrcmit_proc_rslt", "cmt_proc_result_cd",
    "law_proc_rslt", "law_proc_result_cd",
    "rgs_conf_nm", "rgs_conf_rslt",
    "proc_rslt", "status", "passed", "enacted",
    "vote_result_cd", "vote_member_total", "vote_total",
    "vote_yes", "vote_no", "vote_abstain",
    "prom_no", "prom_law_nm", "committee_nm", "committee_id",
    "jrcmit_nm", "link_url", "member_list",
    "days_to_proc", "days_to_committee",
]
NEW_COLS = [
    "vetoed", "veto_bill_id", "veto_dt", "revote_rslt", "revote_dt",
    "first_plenary_rslt", "promulgated", "law_reflected",
    "alt_bill_id", "alt_vetoed", "expired_at_term_end", "plenary_decided",
    "vote_bill_id",
]
DATE_COLS = [
    "ppsl_dt", "committee_dt", "bdg_cmmt_dt",
    "cmt_present_dt", "jrcmit_prsnt_dt", "jrcmit_cmmt_dt",
    "cmt_proc_dt", "jrcmit_proc_dt",
    "law_submit_dt", "law_cmmt_dt",
    "law_present_dt", "law_prsnt_dt",
    "law_proc_dt",
    "rgs_prsnt_dt", "rgs_rsln_dt",
    "gvrn_trsf_dt", "prom_dt", "proc_dt",
    "veto_dt", "revote_dt",
]
FLOAT_COLS = ["vote_member_total", "vote_total", "vote_yes", "vote_no", "vote_abstain",
              "days_to_proc", "days_to_committee"]
FLAG_COLS = ["passed", "enacted", "vetoed", "promulgated", "law_reflected",
             "alt_vetoed", "expired_at_term_end", "plenary_decided"]
VOTE_COLS = {       # ncocpgfiaoituanbr -> master
    "proc_result_cd": "vote_result_cd",
    "member_tcnt": "vote_member_total",
    "vote_tcnt": "vote_total",
    "yes_tcnt": "vote_yes",
    "no_tcnt": "vote_no",
    "blank_tcnt": "vote_abstain",
}
# Lite column list, used when data/processed has no old lite file to copy it from
LITE_COLS = [
    "bill_id", "bill_no", "bill_nm", "committee_nm", "ppsl_dt", "proc_rslt",
    "age", "link_url", "proposer_text", "member_list", "law_proc_dt",
    "law_proc_result_cd", "rst_mona_cd", "law_present_dt", "law_submit_dt",
    "cmt_proc_result_cd", "cmt_proc_dt", "cmt_present_dt", "committee_dt",
    "proc_dt", "committee_id", "publ_mona_cd", "rst_proposer", "publ_proposer",
    "bill_kind", "ppsr_kind", "eraco", "jrcmit_nm", "bdg_cmmt_dt",
    "jrcmit_prsnt_dt", "jrcmit_proc_dt", "jrcmit_proc_rslt", "status",
    "passed", "enacted", "days_to_proc",
]
VETO_EVENT_COLS = [
    "age", "bill_no", "bill_id", "veto_bill_id", "bill_nm", "ppsr_kind",
    "first_plenary_rslt", "first_plenary_dt", "veto_dt", "revote_rslt",
    "revote_dt", "final_status",
]
VOTE_EVENT_COLS = [
    "age", "vote_bill_id", "bill_no", "bill_nm", "proc_dt", "vote_type",
    "master_bill_id", "member_tcnt", "vote_tcnt", "yes", "no", "abstain", "result",
    "source", "vote_event_id", "chair_present", "chair_yes", "chair_no", "chair_abstain",
    "chair_counts_differ", "correction_note",
]
MINUTES_EVENTS = "minutes_vote_events_{age}.parquet"   # collect_minutes_votes.py

# ── Result vocabularies ────────────────────────────────────────────────────

PASS_RESULTS = {"원안가결", "수정가결", "가결"}
FLOOR_RESULTS = PASS_RESULTS | {"부결"}
PASSED_RESULTS = ["원안가결", "수정가결", "대안반영폐기"]      # legacy `passed`
ENACTED_RESULTS = ["원안가결", "수정가결"]                    # legacy `enacted`
LAW_REFLECTED_RESULTS = ["원안가결", "수정가결", "대안반영폐기", "수정안반영폐기"]
PLENARY_DECIDED_RESULTS = ["원안가결", "수정가결", "부결"]
EXPIRED = "임기만료폐기"

# Reconsideration records with neither a GOV_ prefix nor PPSR 대통령.
# 17th bill 171640: BILLRCP lists only this post-veto record (PPSL_DT
# 2008-02-14 = veto date); the original is 030427 (수정가결 2008-01-28).
KNOWN_RECONSIDERATION = {"PRC_G0K8A0Q2M1H4L1O1Q2V5H4P2C5K1E9"}

LIKMS_LINK = "https://likms.assembly.go.kr/bill/billDetail.do?billId={}"

# Tally names carry the proposer of the voted text: '(홍길동의원 등 10인)',
# '(홍길동의원 외 169인)', '(법제사법위원장)', '(정부)'.
PROPOSER_SUFFIX = re.compile(r"\([^()]*(?:의원|위원장|위원회|정부|의장|\d\s*인)[^()]*\)\s*$")
TRAILING_PAREN = re.compile(r"\([^()]*\)\s*$")

# ── Source field mapping ───────────────────────────────────────────────────

NZM_RENAME = {
    "bill_name": "bill_nm",
    "committee": "committee_nm",
    "propose_dt": "ppsl_dt",
    "proc_result": "proc_rslt",
    "proposer": "proposer_text",
    "detail_link": "link_url",
}
NZP_RENAME = {
    "bill_name": "bill_nm",
    "proposer_kind": "ppsr_kind",
    "propose_dt": "ppsl_dt",
    "proc_result_cd": "proc_rslt",
    "curr_committee": "committee_nm",
    "curr_committee_id": "committee_id",
    "proposer": "nzp_proposer",
}
# Field -> sources in priority order. The three lists agree wherever they
# overlap; the processed-bill list adds committee stages for non-member bills.
FIELD_SOURCES = {
    "bill_no": ("rcp", "nzm", "nzp"),
    "bill_nm": ("rcp", "nzm", "nzp"),
    "bill_kind": ("rcp",),
    "ppsr_kind": ("rcp",),
    "ppsl_dt": ("nzm", "rcp", "nzp"),
    "proc_rslt": ("nzm", "rcp", "nzp"),
    "link_url": ("nzm", "rcp", "nzp"),
    "proposer_text": ("nzm",),
    "rst_proposer": ("nzm",),
    "rst_mona_cd": ("nzm",),
    "publ_proposer": ("nzm",),
    "publ_mona_cd": ("nzm",),
    "member_list": ("nzm",),
    "committee_nm": ("nzm", "nzp"),
    "committee_id": ("nzm", "nzp"),
    "committee_dt": ("nzm", "nzp"),
    "cmt_present_dt": ("nzm", "nzp"),
    "cmt_proc_dt": ("nzm", "nzp"),
    "cmt_proc_result_cd": ("nzm", "nzp"),
    "law_submit_dt": ("nzm", "nzp"),
    "law_present_dt": ("nzm", "nzp"),
    "law_proc_dt": ("nzm", "nzp"),
    "law_proc_result_cd": ("nzm", "nzp"),
    "proc_dt": ("nzm", "nzp"),
}
JUDGE_COLS = ["bill_id", "jrcmit_nm", "bdg_cmmt_dt",
              "jrcmit_prsnt_dt", "jrcmit_proc_dt", "jrcmit_proc_rslt"]
DETAIL_COLS = [          # BILLINFODETAIL columns kept as master columns
    "jrcmit_cmmt_dt",    # 소관위 회부일
    "law_cmmt_dt",       # 법사위 회부일
    "law_prsnt_dt",      # 법사위 상정일
    "law_proc_rslt",     # 법사위 처리결과
    "rgs_prsnt_dt",      # 본회의 상정일
    "rgs_rsln_dt",       # 본회의 의결일
    "rgs_conf_nm",       # 본회의 회차
    "rgs_conf_rslt",     # 본회의 결과
    "gvrn_trsf_dt",      # 정부이송일
    "prom_dt",           # 공포일
    "prom_no",           # 공포번호
    "prom_law_nm",       # 공포법률명
]
DETAIL_FILL = {          # BILLINFODETAIL column -> master column it fills when missing
    "jrcmit_nm": "committee_nm",
    "jrcmit_cmmt_dt": "committee_dt",
    "jrcmit_prsnt_dt": "cmt_present_dt",
    "jrcmit_proc_dt": "cmt_proc_dt",
    "law_proc_dt": "law_proc_dt",
}


# ── Helpers ────────────────────────────────────────────────────────────────

def safe_date(series: pd.Series) -> pd.Series:
    """Convert to datetime, coercing errors to NaT. Handles '0' and empty strings.

    format='ISO8601' parses each value on its own. Without it pandas infers the
    format from the first value, so a stray 'YYYYMMDD' (two 19th-assembly
    RGS_RSLN_DT values) is dropped, or blanks the whole column if it comes first.
    Values are stripped first: ISO8601 rejects '2022-07-25 ' (a trailing space
    in three 21st-assembly COMMITTEE_DT / JRCMIT_CMMT_DT values).
    """
    s = series.map(lambda x: x.strip() if isinstance(x, str) else x)
    s = s.replace({"0": pd.NaT, "": pd.NaT})
    return pd.to_datetime(s, errors="coerce", format="ISO8601")


def load_raw(filename: str) -> pd.DataFrame:
    path = RAW_DIR / filename
    if not path.exists():
        log.warning(f"  File not found: {filename}")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df.columns = df.columns.str.lower()
    return df


def parse_ages(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def unique_by_id(df: pd.DataFrame, name: str, key: str = "bill_id") -> pd.DataFrame:
    """Drop exact duplicate rows, then require one row per key."""
    if df.empty:
        return df
    dup = df.duplicated().sum()
    if dup:
        log.warning(f"  {name}: {dup} exact duplicate rows dropped")
        df = df.drop_duplicates()
    extra = df[key].duplicated().sum()
    if extra:
        raise RuntimeError(f"{name}: {extra} {key} values with conflicting rows")
    return df


def left_join(master: pd.DataFrame, right: pd.DataFrame, on: str, what: str) -> pd.DataFrame:
    """Left join that must not change the number of master rows."""
    before = len(master)
    out = master.merge(right, on=on, how="left", validate="many_to_one")
    assert len(out) == before, f"{what} join changed rows {before} -> {len(out)}"
    return out


def canon_name(name) -> str:
    s = re.sub(r"\s+", "", str(name or ""))
    return s.replace("ㆍ", "·").replace("‧", "·").replace("∙", "·")


def strip_parens(name: str) -> str:
    prev = None
    while prev != name:
        prev, name = name, TRAILING_PAREN.sub("", name)
    return name


def name_matches(tally_name, bill_nm) -> bool:
    """Does a tally's BILL_NAME refer to this bill (ignoring the proposer suffix)?"""
    a, b = canon_name(tally_name), canon_name(bill_nm)
    if not a or not b:
        return False
    if a == b or canon_name(PROPOSER_SUFFIX.sub("", str(tally_name))) == b:
        return True
    return strip_parens(a) == strip_parens(b)


def dedup_detail(detail: pd.DataFrame, rec: pd.DataFrame) -> pd.DataFrame:
    """One BILLINFODETAIL row per requested bill (_bill_id), as an indexed frame.

    The API sometimes returns several rows for one bill, one of them nearly
    empty or with a conflicting floor result. Keep the row with the most
    non-empty fields; on a tie prefer the row whose floor result and date
    equal the bill's result and processing date in the list endpoints, then
    the latest floor date.
    """
    if detail.empty:
        return pd.DataFrame(columns=["ppsr", "ppsr_kind", "ppsl_dt", "bill_nm", "bill_no"]
                            + DETAIL_COLS + list(DETAIL_FILL)).rename_axis("_bill_id")
    d = detail.drop(columns=["bill_id"], errors="ignore").drop_duplicates()
    body = d.drop(columns=["_bill_id"])
    filled = (body.notna() & (body.astype(str).apply(lambda c: c.str.strip()) != "")).sum(axis=1)
    rsln = safe_date(d["rgs_rsln_dt"])
    agrees = (d["rgs_conf_rslt"].eq(d["_bill_id"].map(rec["proc_rslt"])).astype(int)
              + rsln.eq(safe_date(d["_bill_id"].map(rec["proc_dt"]))).astype(int))
    d = d.assign(_filled=filled, _agrees=agrees, _rsln=rsln)
    multi = d["_bill_id"].duplicated(keep=False)
    if multi.any():
        log.info(f"  BILLINFODETAIL: {d.loc[multi, '_bill_id'].nunique():,} bills with "
                 f"several distinct rows, kept the most complete")
    d = d.sort_values(["_bill_id", "_filled", "_agrees", "_rsln", "rgs_conf_nm"],
                      ascending=[True, False, False, False, False], na_position="last")
    d = d.drop_duplicates("_bill_id").drop(columns=["_filled", "_agrees", "_rsln"])
    return d.set_index("_bill_id")


# ── Step 1: universe of records ────────────────────────────────────────────

def load_records(age: int) -> tuple[pd.DataFrame, dict]:
    """One row per BILL_ID from BILLRCP, member bills and processed bills."""
    era = f"제{age}대"
    rcp = load_raw(f"BILLRCP_{age}.parquet")
    if not rcp.empty:
        rcp = rcp[rcp["eraco"] == era]
    nzm = load_raw(f"nzmimeepazxkubdpn_{age}.parquet").rename(columns=NZM_RENAME)
    nzp = load_raw(f"nzpltgfqabtcpsmai_{age}.parquet").rename(columns=NZP_RENAME)
    srcs = {"rcp": unique_by_id(rcp, f"BILLRCP_{age}"),
            "nzm": unique_by_id(nzm, f"nzmimeepazxkubdpn_{age}"),
            "nzp": unique_by_id(nzp, f"nzpltgfqabtcpsmai_{age}")}
    for name, df in srcs.items():
        log.info(f"  {name}: {len(df):,} records")
    if srcs["rcp"].empty:
        log.warning(f"  BILLRCP_{age} is empty: non-member bills will be missing")

    ids = pd.Index(pd.concat([df["bill_id"] for df in srcs.values() if not df.empty])
                   .drop_duplicates(), name="bill_id")
    indexed = {k: (v.set_index("bill_id") if not v.empty else pd.DataFrame())
               for k, v in srcs.items()}
    rec = pd.DataFrame(index=ids)
    for col, order in FIELD_SOURCES.items():
        s = pd.Series(None, index=ids, dtype=object)
        for name in order:
            src = indexed[name]
            if col in src.columns:
                s = s.where(s.notna(), src[col].reindex(ids))
        rec[col] = s
    in_rcp = ids.isin(indexed["rcp"].index)
    in_nzm = ids.isin(indexed["nzm"].index)
    in_nzp = ids.isin(indexed["nzp"].index)
    # Member and processed-bill lists hold law bills only
    rec["bill_kind"] = rec["bill_kind"].where(rec["bill_kind"].notna() | ~(in_nzm | in_nzp), "법률안")
    nzp_kind = (indexed["nzp"]["ppsr_kind"].reindex(ids)
                if "ppsr_kind" in indexed["nzp"].columns else None)
    kind = rec["ppsr_kind"].where(rec["ppsr_kind"].notna() | ~in_nzm, "의원")
    if nzp_kind is not None:
        kind = kind.where(kind.notna(), nzp_kind)
    rec["ppsr_kind"] = kind
    log.info(f"  Universe: {len(rec):,} BILL_IDs ({(~in_rcp).sum():,} not in BILLRCP)")
    return rec, srcs


# ── Step 2: veto pairs ─────────────────────────────────────────────────────

def find_vetoes(rec: pd.DataFrame, det: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """Pair every reconsideration record with its original bill.

    Returns (records with any recovered originals added, veto pairs, unexplained
    bill_no duplicates). A pair row has bill_id (the original), veto_bill_id
    (the reconsideration record) and self_pair when no original was found.
    """
    ppsr = pd.Series(rec.index.map(det["ppsr"]) if "ppsr" in det.columns else None,
                     index=rec.index)
    n_ids = rec.groupby("bill_no")["bill_no"].transform("size")
    is_recon = (rec.index.str.startswith("GOV_")
                | rec.index.isin(KNOWN_RECONSIDERATION)
                | ((ppsr == "대통령") & (n_ids > 1)))
    rec = rec.assign(is_recon=is_recon)

    pairs, unexplained = [], []
    for no, grp in rec[n_ids > 1].groupby("bill_no"):
        recon = grp[grp["is_recon"]]
        orig = grp[~grp["is_recon"]]
        if recon.empty or len(orig) != 1:
            unexplained.append(no)
            continue
        if len(recon) > 1:
            log.warning(f"  bill_no {no}: {len(recon)} reconsideration records, "
                        f"the latest is the veto record")
        recon = recon.sort_values("ppsl_dt")
        for rid in recon.index:
            pairs.append({"bill_id": orig.index[0], "veto_bill_id": rid,
                          "self_pair": False, "latest": rid == recon.index[-1]})

    # A reconsideration record whose original is in none of the three lists
    # (a vetoed alternative whose re-vote is still pending): the original
    # shares the GOV_ record's suffix, so look for it in BILLINFODETAIL.
    lone = rec.index[rec["is_recon"] & (n_ids == 1)]
    added = []
    for rid in lone:
        oid = "PRC_" + rid[4:] if rid.startswith("GOV_") else None
        if oid is not None and oid in det.index:
            d = det.loc[oid]
            added.append({
                "bill_id": oid, "bill_no": d.get("bill_no") or rec.at[rid, "bill_no"],
                "bill_nm": d.get("bill_nm"), "bill_kind": rec.at[rid, "bill_kind"],
                "ppsr_kind": d.get("ppsr_kind"), "ppsl_dt": d.get("ppsl_dt"),
                "proc_rslt": d.get("rgs_conf_rslt"), "link_url": LIKMS_LINK.format(oid),
                "is_recon": False,
            })
            pairs.append({"bill_id": oid, "veto_bill_id": rid, "self_pair": False, "latest": True})
            log.info(f"  {rid}: original {oid} recovered from BILLINFODETAIL")
        else:
            pairs.append({"bill_id": rid, "veto_bill_id": rid, "self_pair": True, "latest": True})
            log.warning(f"  {rid} (bill_no {rec.at[rid, 'bill_no']}): original record not "
                        f"collected (expected {oid}); kept the reconsideration record as the "
                        f"bill row with proposer fields cleared. Collect BILLINFODETAIL for "
                        f"{oid} and rebuild.")
    if added:
        rec = pd.concat([rec, pd.DataFrame(added).set_index("bill_id")])
    return rec, pd.DataFrame(pairs, columns=["bill_id", "veto_bill_id", "self_pair", "latest"]), unexplained


def veto_frame(pairs: pd.DataFrame, rec: pd.DataFrame, det: pd.DataFrame,
               term_end: pd.Timestamp, age: int) -> pd.DataFrame:
    """Veto attributes of each original bill (one row per vetoed bill)."""
    v = pairs[pairs["latest"]].copy()
    if v.empty:
        return pd.DataFrame(columns=["bill_id", "veto_bill_id", "self_pair", "veto_dt",
                                     "revote_rslt", "revote_dt", "final_rslt", "final_dt",
                                     "orig_list_rslt", "orig_list_proc_dt"])
    rslt = v["veto_bill_id"].map(rec["proc_rslt"])
    v["veto_dt"] = safe_date(v["veto_bill_id"].map(rec["ppsl_dt"]))
    recon_rsln = safe_date(v["veto_bill_id"].map(det["rgs_rsln_dt"]))
    v["revote_rslt"] = rslt.where(rslt.isin(FLOOR_RESULTS))
    v["revote_dt"] = recon_rsln.where(v["revote_rslt"].notna())
    unresolved = None if age == CURRENT_AGE else EXPIRED
    final = v["revote_rslt"].copy()
    final = final.where(final.notna(), rslt)                    # 임기만료폐기 or other end states
    v["final_rslt"] = final.where(final.notna(), unresolved)
    expired_dt = recon_rsln.where(recon_rsln.notna(), term_end)
    v["final_dt"] = v["revote_dt"].where(v["revote_rslt"].notna(),
                                         expired_dt.where(v["final_rslt"] == EXPIRED))
    v["orig_list_rslt"] = v["bill_id"].map(rec["proc_rslt"]).where(~v["self_pair"])
    v["orig_list_proc_dt"] = safe_date(v["bill_id"].map(rec["proc_dt"])).where(~v["self_pair"])
    return v


# ── Step 5: plenary tallies ────────────────────────────────────────────────

def match_tallies(master: pd.DataFrame, veto: pd.DataFrame, folded: dict, age: int
                  ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assign every tally to a bill and pick each bill's own passage tally.

    Returns (master vote columns indexed by bill_id, vote events).
    """
    if not (RAW_DIR / f"ncocpgfiaoituanbr_{age}.parquet").exists():
        log.info(f"  No ncocpgfiaoituanbr_{age}.parquet (the API has tallies from the 20th on)")
        return pd.DataFrame(), pd.DataFrame(columns=VOTE_EVENT_COLS)
    t = load_raw(f"ncocpgfiaoituanbr_{age}.parquet")
    dup = t.duplicated().sum()
    if dup:
        log.warning(f"  ncocpgfiaoituanbr_{age}: {dup} exact duplicate tallies dropped")
        t = t.drop_duplicates()
    t = t.reset_index(drop=True)
    t["proc_dt"] = safe_date(t["proc_dt"])

    by_id = master.set_index("bill_id")
    by_no = master.set_index("bill_no")
    vinfo = veto.set_index("bill_id") if not veto.empty else pd.DataFrame()
    master_id, how = [], []
    for r in t.itertuples():
        if r.bill_id in by_id.index:
            master_id.append(r.bill_id); how.append("id")
        elif r.bill_id in folded:
            master_id.append(folded[r.bill_id]); how.append("recon_id")
        elif r.bill_no in by_no.index:
            cand = by_no.loc[r.bill_no]
            kind_ok = (pd.isna(r.bill_kind_cd) or pd.isna(cand["bill_kind"])
                       or r.bill_kind_cd == cand["bill_kind"])
            if kind_ok and name_matches(r.bill_name, cand["bill_nm"]):
                master_id.append(cand["bill_id"]); how.append("bill_no")
            else:
                master_id.append(None); how.append("rejected")
        else:
            master_id.append(None); how.append("unmatched")
    t["master_bill_id"] = master_id
    t["_how"] = how

    veto_dt = t["master_bill_id"].map(vinfo["veto_dt"]) if not vinfo.empty else pd.Series(pd.NaT, index=t.index)
    after_veto = veto_dt.notna() & (t["proc_dt"] >= veto_dt)
    suffixed = t["bill_name"].fillna("").map(lambda n: "수정안" in n or bool(PROPOSER_SUFFIX.search(n)))
    t["vote_type"] = "other"
    t.loc[t["_how"] == "bill_no", "vote_type"] = suffixed.map({True: "amendment", False: "other"})
    t.loc[t["_how"] == "id", "vote_type"] = "original"
    t.loc[(t["_how"] == "recon_id") | (t["master_bill_id"].notna() & after_veto),
          "vote_type"] = "reconsideration"
    counts = t["_how"].value_counts().to_dict()
    log.info(f"  Tallies: {len(t):,} (by id {counts.get('id', 0):,}, by bill_no+name "
             f"{counts.get('bill_no', 0):,}, reconsideration id {counts.get('recon_id', 0):,}, "
             f"rejected {counts.get('rejected', 0):,}, no bill {counts.get('unmatched', 0):,})")
    rejected = t[t["_how"].isin(["rejected", "unmatched"])]
    for r in rejected.head(10).itertuples():
        log.info(f"    unassigned tally {r.bill_id} {r.bill_no} {r.bill_kind_cd} {r.bill_name}")

    # The master's tally: the bill's own tally first, else a floor amendment
    # under its number; within that, the result that matches the bill's first
    # floor decision, then the latest and the largest vote.
    first = by_id["first_plenary_rslt"]
    rgs = by_id["rgs_conf_rslt"].where(by_id["rgs_conf_rslt"].isin(FLOOR_RESULTS))
    target = first.where(first.notna(), rgs)
    target = target.where(target.notna(), by_id["proc_rslt"])
    c = t[t["vote_type"].isin(["original", "amendment"])].copy()
    tg = c["master_bill_id"].map(target)
    c["_orig"] = (c["vote_type"] == "original").astype(int)
    c["_match"] = ((tg.isin(PASS_RESULTS) & c["proc_result_cd"].isin(PASS_RESULTS))
                   | (tg == c["proc_result_cd"])).astype(int)
    c = c.sort_values(["master_bill_id", "_orig", "_match", "proc_dt", "vote_tcnt"],
                      ascending=[True, False, False, False, False])
    chosen = c.drop_duplicates("master_bill_id").set_index("master_bill_id")
    votes = chosen[list(VOTE_COLS)].rename(columns=VOTE_COLS)
    votes["vote_bill_id"] = chosen["bill_id"]

    events = pd.DataFrame({
        "age": age,
        "vote_bill_id": t["bill_id"],
        "bill_no": t["bill_no"],
        "bill_nm": t["bill_name"],
        "proc_dt": t["proc_dt"],
        "vote_type": t["vote_type"],
        "master_bill_id": t["master_bill_id"],
        "member_tcnt": t["member_tcnt"],
        "vote_tcnt": t["vote_tcnt"],
        "yes": t["yes_tcnt"],
        "no": t["no_tcnt"],
        "abstain": t["blank_tcnt"],
        "result": t["proc_result_cd"],
    })
    log.info(f"  Vote types: {events['vote_type'].value_counts().to_dict()}")
    return votes, events


def minutes_vote_events(master: pd.DataFrame, age: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """17th-19th: recorded votes from the plenary minutes appendices.

    data/raw/minutes_vote_events_{age}.parquet (collect_minutes_votes.py) has
    one row per recorded vote, linked to master bills where the title allows.
    Its counts are the names printed in the appendix, and the chair's
    announced counts are kept beside them. The minutes print no membership count, so
    member_tcnt is null, and result is the chair's 가결 or 부결.

    The master's vote_* columns take one vote per bill: the latest vote on
    the bill itself (vote_on 'bill' or 'reversal', including a repeated
    vote), else the latest vote on a floor amendment to it. Latest is by date
    and then by order in the minutes. vote_bill_id holds that vote's
    vote_event_id, and vote_member_total stays null.
    """
    ev = pd.read_parquet(RAW_DIR / MINUTES_EVENTS.format(age=age))
    stray = ev["bill_id"].notna() & ~ev["bill_id"].isin(master["bill_id"])
    if stray.any():
        log.warning(f"  {int(stray.sum())} minutes votes link to bills missing from the master: "
                    f"{ev.loc[stray, 'bill_id'].unique()[:5].tolist()}")
    linked = ev["bill_id"].where(~stray)
    events = pd.DataFrame({
        "age": age,
        "vote_bill_id": linked,
        "bill_no": ev["bill_no"].where(~stray),
        "bill_nm": ev["title"],
        "proc_dt": pd.to_datetime(ev["date"]),
        "vote_type": ev["vote_type"],
        "master_bill_id": linked,
        "member_tcnt": pd.array([pd.NA] * len(ev), dtype="Int64"),
        "vote_tcnt": ev["names_total"],
        "yes": ev["names_yes"],
        "no": ev["names_no"],
        "abstain": ev["names_abstain"],
        "result": ev["chair_result"],
        "source": "minutes_pdf",
        "vote_event_id": ev["vote_event_id"],
        "chair_present": ev["chair_present"].astype("Int64"),
        "chair_yes": ev["chair_yes"].astype("Int64"),
        "chair_no": ev["chair_no"].astype("Int64"),
        "chair_abstain": ev["chair_abstain"].astype("Int64"),
        "chair_counts_differ": ev["chair_counts_differ"],
        "correction_note": ev["correction_note"],
    })
    c = ev[linked.notna()].copy()
    c["_own"] = c["vote_on"].isin(["bill", "reversal"])
    c = c.sort_values(["bill_id", "_own", "date", "confer_num", "event_seq"], kind="mergesort")
    chosen = c.drop_duplicates("bill_id", keep="last").set_index("bill_id")
    votes = pd.DataFrame({
        "vote_result_cd": chosen["chair_result"],
        "vote_member_total": float("nan"),
        "vote_total": chosen["names_total"].astype("float64"),
        "vote_yes": chosen["names_yes"].astype("float64"),
        "vote_no": chosen["names_no"].astype("float64"),
        "vote_abstain": chosen["names_abstain"].astype("float64"),
        "vote_bill_id": chosen["vote_event_id"],
    }, index=chosen.index)
    log.info(f"  Minutes votes: {len(ev):,} ({ev['vote_type'].value_counts().to_dict()}), "
             f"{len(chosen):,} bills take their vote_* columns from them "
             f"({int((~chosen['_own']).sum()):,} from an amendment vote)")
    return votes, events


# ── Step 6: alternative absorption ─────────────────────────────────────────

def attach_alternatives(master: pd.DataFrame, folded: dict, age: int) -> pd.Series:
    """alt_bill_id: the committee alternative a bill was absorbed into."""
    path = RAW_DIR / f"alt_absorption_{age}.parquet"
    if not path.exists():
        log.info(f"  alt_absorption_{age}.parquet not found: alt_bill_id left empty")
        return pd.Series(None, index=master.index, dtype=object)
    a = pd.read_parquet(path, columns=["ALT_BILL_ID", "BILL_ID"])
    a.columns = ["alt_bill_id", "bill_id"]
    a["alt_bill_id"] = a["alt_bill_id"].replace(folded)
    a = a[a["alt_bill_id"] != a["bill_id"]].drop_duplicates()
    a = a[a["bill_id"].isin(master["bill_id"])]
    res = master.set_index("bill_id")["proc_rslt"]
    a["_pass"] = a["alt_bill_id"].map(res).isin(ENACTED_RESULTS).astype(int)
    multi = a["bill_id"].duplicated(keep=False)
    a = a.sort_values(["bill_id", "_pass", "alt_bill_id"], ascending=[True, False, True])
    a = a.drop_duplicates("bill_id").set_index("bill_id")
    log.info(f"  alt_absorption: {len(a):,} absorbed bills linked to "
             f"{a['alt_bill_id'].nunique():,} alternatives "
             f"({multi.sum():,} links from bills in several alternatives)")
    return master["bill_id"].map(a["alt_bill_id"])


# ── Build one assembly ─────────────────────────────────────────────────────

def build_master(age: int) -> dict:
    """Build the master bills table + satellite tables of one assembly."""
    log.info(f"{'='*60}")
    log.info(f"Building master database (AGE={age})")
    log.info(f"{'='*60}")
    era = f"제{age}대"

    # ── Step 1: universe ────────────────────────────────────────────────
    log.info("\n[Step 1] Universe: BILLRCP + member bills + processed bills")
    rec, srcs = load_records(age)
    detail = load_raw(f"BILLINFODETAIL_{age}.parquet")
    det = dedup_detail(detail, rec)
    log.info(f"  BILLINFODETAIL: {len(detail):,} rows -> {len(det):,} bills")

    judge = load_raw(f"BILLJUDGE_{age}.parquet")
    if not judge.empty:
        judge = unique_by_id(judge[judge["eraco"] == era], f"BILLJUDGE_{age}")

    # ── Step 2: veto pairs ──────────────────────────────────────────────
    log.info("\n[Step 2] Veto pairs (재의요구)")
    rec, pairs, unexplained = find_vetoes(rec, det)
    folded = dict(zip(pairs.loc[~pairs["self_pair"], "veto_bill_id"],
                      pairs.loc[~pairs["self_pair"], "bill_id"]))
    log.info(f"  {int(rec['is_recon'].sum())} reconsideration records, "
             f"{len(folded)} folded into their original, "
             f"{int(pairs['self_pair'].sum())} without a collected original")
    for p in pairs.itertuples():
        log.info(f"    {rec.at[p.bill_id, 'bill_no']}  {p.bill_id} <- {p.veto_bill_id}")

    # Term end: the processing date shared by expired bills
    exp_dt = safe_date(rec.loc[rec["proc_rslt"] == EXPIRED, "proc_dt"])
    term_end = exp_dt.mode().iloc[0] if not exp_dt.dropna().empty else pd.NaT
    veto = veto_frame(pairs, rec, det, term_end, age)

    self_ids = set(pairs.loc[pairs["self_pair"], "bill_id"])
    master = rec.drop(index=list(folded)).copy()
    # The reconsideration record's proposer and date describe the veto, not the bill
    master.loc[master.index.isin(self_ids), ["ppsr_kind", "ppsl_dt"]] = None
    master = master.reset_index()

    # ── Step 8 (early): identity checks before any join ─────────────────
    assert master["bill_id"].is_unique, "bill_id not unique"
    dup_no = master["bill_no"][master["bill_no"].duplicated(keep=False)]
    if not dup_no.empty or unexplained:
        log.error(f"  Unexplained bill_no duplicates: {sorted(set(dup_no) | set(unexplained))}")
        raise RuntimeError(f"bill_no not unique in {age}대")
    rcp_ids = set(srcs["rcp"]["bill_id"]) if not srcs["rcp"].empty else set()
    lost = rcp_ids - set(master["bill_id"]) - set(folded)
    assert not lost, f"BILLRCP records neither in master nor folded: {sorted(lost)[:5]}"
    log.info(f"  Master: {len(master):,} bills, bill_id and bill_no unique; every BILLRCP "
             f"record is a bill row or a folded reconsideration record")

    # ── Step 3: joins ───────────────────────────────────────────────────
    log.info("\n[Step 3] Joins: BILLJUDGE, BILLINFODETAIL")
    if not judge.empty:
        only = judge[~judge["bill_id"].isin(master["bill_id"]) & ~judge["bill_id"].isin(folded)]
        kinds = only["bill_nm"].str.extract(r"(인사청문요청안|국정조사요구|[가-힣]+안)$")[0]
        log.info(f"  BILLJUDGE-only agenda items left out: {len(only):,} "
                 f"{kinds.value_counts().to_dict()}")
        master = left_join(master, judge[[c for c in JUDGE_COLS if c in judge.columns]],
                           "bill_id", "BILLJUDGE")
        log.info(f"  BILLJUDGE: {master['jrcmit_proc_rslt'].notna().sum():,} with committee result")
    else:
        for c in JUDGE_COLS[1:]:
            master[c] = None

    dsub = det.reindex(columns=DETAIL_COLS).copy()
    for src in DETAIL_FILL:
        dsub[f"det_{src}"] = det[src] if src in det.columns else None
    dsub = dsub.rename_axis("bill_id").reset_index()
    master = left_join(master, dsub, "bill_id", "BILLINFODETAIL")
    log.info(f"  BILLINFODETAIL: {master['bill_id'].isin(det.index).sum():,} of "
             f"{len(master):,} bills have a detail row")

    for col in DATE_COLS:
        if col in master.columns:
            master[col] = safe_date(master[col])
    for src in DETAIL_FILL:
        if src.endswith("_dt"):
            master[f"det_{src}"] = safe_date(master[f"det_{src}"])

    # ── Step 4: fill gaps from BILLINFODETAIL ───────────────────────────
    log.info("\n[Step 4] Fill committee stages and processing dates")
    for src, dst in DETAIL_FILL.items():
        fill = master[f"det_{src}"]
        if dst == "committee_nm":
            fill = fill.where(~fill.isin(["본회의", ""]))
        gap = master[dst].isna() & fill.notna()
        master.loc[gap, dst] = fill[gap]
        log.info(f"  {dst} <- detail {src}: {gap.sum():,} filled")
    master = master.drop(columns=[f"det_{s}" for s in DETAIL_FILL])
    gap = master["proc_dt"].isna() & master["proc_rslt"].notna() & master["rgs_rsln_dt"].notna()
    master.loc[gap, "proc_dt"] = master.loc[gap, "rgs_rsln_dt"]
    log.info(f"  proc_dt <- detail rgs_rsln_dt for processed bills: {gap.sum():,} filled")

    # Vetoed bills: first floor result stays in rgs_*, the final result follows the re-vote
    v = veto.set_index("bill_id")
    is_v = master["bill_id"].isin(v.index)
    vid = master.loc[is_v, "bill_id"]
    rgs = master.loc[is_v, "rgs_conf_rslt"]
    # A self-pair row's detail is the reconsideration record's own (the re-vote)
    from_detail = rgs.isin(FLOOR_RESULTS) & ~vid.isin(self_ids)
    master["vetoed"] = is_v.astype(int)
    master["veto_bill_id"] = master["bill_id"].map(v["veto_bill_id"])
    master["veto_dt"] = master["bill_id"].map(v["veto_dt"])
    master["revote_rslt"] = master["bill_id"].map(v["revote_rslt"])
    master["revote_dt"] = master["bill_id"].map(v["revote_dt"])
    master["first_plenary_rslt"] = None
    master["first_plenary_dt"] = pd.NaT
    if is_v.any():
        master.loc[is_v, "first_plenary_rslt"] = rgs.where(from_detail, vid.map(v["orig_list_rslt"]))
        master.loc[is_v, "first_plenary_dt"] = master.loc[is_v, "rgs_rsln_dt"].where(
            from_detail, vid.map(v["orig_list_proc_dt"]))
        master.loc[is_v, "proc_rslt"] = vid.map(v["final_rslt"])
        master.loc[is_v, "proc_dt"] = vid.map(v["final_dt"])

    # ── Step 5: votes ───────────────────────────────────────────────────
    log.info("\n[Step 5] Plenary tallies")
    votes, vote_events = match_tallies(master, veto, folded, age)
    if vote_events.empty and (RAW_DIR / MINUTES_EVENTS.format(age=age)).exists():
        votes, vote_events = minutes_vote_events(master, age)
    else:
        vote_events = vote_events.assign(source="api", vote_event_id=vote_events["vote_bill_id"])
        for col in ["chair_present", "chair_yes", "chair_no", "chair_abstain"]:
            vote_events[col] = pd.array([pd.NA] * len(vote_events), dtype="Int64")
        for col in ["chair_counts_differ", "correction_note"]:
            vote_events[col] = pd.array([pd.NA] * len(vote_events), dtype="boolean")
    for col in list(VOTE_COLS.values()) + ["vote_bill_id"]:
        master[col] = master["bill_id"].map(votes[col]) if col in votes.columns else None
    for col in ["vote_member_total", "vote_total", "vote_yes", "vote_no", "vote_abstain"]:
        master[col] = master[col].astype("float64")
    log.info(f"  Bills with a tally: {master['vote_total'].notna().sum():,}")

    # ── Step 6: derived variables ───────────────────────────────────────
    log.info("\n[Step 6] Derived variables")
    master["age"] = age
    master["status"] = master["proc_rslt"].fillna("계류중" if age == CURRENT_AGE else EXPIRED)
    master["days_to_proc"] = (master["proc_dt"] - master["ppsl_dt"]).dt.days
    master["days_to_committee"] = (master["bdg_cmmt_dt"] - master["ppsl_dt"]).dt.days
    master["passed"] = master["proc_rslt"].isin(PASSED_RESULTS).astype(int)
    master["enacted"] = master["proc_rslt"].isin(ENACTED_RESULTS).astype(int)
    master["promulgated"] = ((master["bill_kind"] == "법률안")
                             & master["prom_dt"].notna()).astype(int)
    master["alt_bill_id"] = attach_alternatives(master, folded, age)
    alt = master.set_index("bill_id")
    alt_dead = alt.index[(alt["vetoed"] == 1) & ~alt["proc_rslt"].isin(PASS_RESULTS)]
    master["alt_vetoed"] = master["alt_bill_id"].isin(alt_dead).astype(int)
    master["law_reflected"] = (master["proc_rslt"].isin(LAW_REFLECTED_RESULTS)
                               & (master["alt_vetoed"] == 0)).astype(int)
    master["expired_at_term_end"] = (master["proc_rslt"] == EXPIRED).astype(int)
    # Floor decision: BILLINFODETAIL's result, else the first floor result or
    # the list result when the bill has no detail row
    floor = master["rgs_conf_rslt"].where(master["rgs_conf_rslt"].notna(),
                                          master["first_plenary_rslt"])
    floor = floor.where(floor.notna(), master["proc_rslt"])
    master["plenary_decided"] = floor.isin(PLENARY_DECIDED_RESULTS).astype(int)

    log.info(f"  Total bills: {len(master):,}")
    log.info(f"  Passed (원안/수정가결/대안반영폐기): {master['passed'].sum():,}")
    log.info(f"  Enacted (원안/수정가결): {master['enacted'].sum():,}")
    log.info(f"  Promulgated laws: {master['promulgated'].sum():,}")
    log.info(f"  Vetoed: {master['vetoed'].sum():,}; alternatives vetoed: "
             f"{master['alt_vetoed'].sum():,} absorbed bills")
    log.info(f"  계류중: {(master['status'] == '계류중').sum():,}")

    # ── Column order and types ──────────────────────────────────────────
    for col in DATE_COLS + ["first_plenary_dt"]:
        master[col] = pd.to_datetime(master[col]).astype("datetime64[ns]")
    for col in FLAG_COLS + ["age"]:
        master[col] = master[col].astype("int64")
    for col in FLOAT_COLS:
        master[col] = master[col].astype("float64")
    typed = set(DATE_COLS + FLAG_COLS + FLOAT_COLS + ["age", "first_plenary_dt"])
    for col in [c for c in LEGACY_COLS + NEW_COLS if c not in typed]:
        master[col] = master[col].astype(object).where(master[col].notna(), None)

    # ── Veto events ─────────────────────────────────────────────────────
    ve = master.loc[master["vetoed"] == 1].copy()
    ve["final_status"] = ve["proc_rslt"].fillna("계류중")
    veto_events = ve[VETO_EVENT_COLS].reset_index(drop=True)

    assert master["bill_id"].is_unique and master["bill_no"].is_unique
    master = master[LEGACY_COLS + NEW_COLS].reset_index(drop=True)

    # ── Step 7: satellite tables ────────────────────────────────────────
    log.info("\n[Step 7] Satellite tables (committee meetings)")
    committee_meetings = load_meetings(f"BILLJUDGECONF_{age}.parquet", master, folded)
    judiciary_meetings = load_meetings(f"BILLLWJUDGECONF_{age}.parquet", master, folded)

    return {"master": master, "committee_meetings": committee_meetings,
            "judiciary_meetings": judiciary_meetings, "veto_events": veto_events,
            "vote_events": vote_events}


def load_meetings(filename: str, master: pd.DataFrame, folded: dict) -> pd.DataFrame:
    """Lowercase columns, tag column bill_id_tagged, exact duplicates dropped."""
    df = load_raw(filename)
    if df.empty:
        return df
    df = df.rename(columns={"_bill_id": "bill_id_tagged"})
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    orphan = ~df["bill_id_tagged"].isin(master["bill_id"])
    log.info(f"  {filename}: {before:,} rows -> {len(df):,} after dropping exact duplicates; "
             f"{orphan.sum():,} rows of {df.loc[orphan, 'bill_id_tagged'].nunique():,} "
             f"bills not in master ({df.loc[orphan, 'bill_id_tagged'].isin(folded).sum():,} "
             f"on reconsideration records)")
    return df


# ── Save ───────────────────────────────────────────────────────────────────

def arrow_schema(df: pd.DataFrame) -> pa.Schema:
    """Explicit types, so an all-empty text column is string, not null, in every age."""
    fields = []
    for col, dtype in df.dtypes.items():
        if pd.api.types.is_datetime64_any_dtype(dtype):
            t = pa.timestamp("ns")
        elif pd.api.types.is_integer_dtype(dtype):
            t = pa.int64()
        elif pd.api.types.is_float_dtype(dtype):
            t = pa.float64()
        elif pd.api.types.is_bool_dtype(dtype):
            t = pa.bool_()
        else:
            t = pa.string()
        fields.append(pa.field(col, t))
    return pa.schema(fields)


def write_parquet(df: pd.DataFrame, path: Path):
    """Write to a temp file and rename, so a crash never leaves a half file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, schema=arrow_schema(df))
    os.replace(tmp, path)


def lite_columns(old_dir: Path, age: int) -> list[str]:
    old = old_dir / f"master_bills_{age}_lite.parquet"
    if old.exists():
        return pq.read_schema(old).names
    return LITE_COLS


def save_outputs(out: dict, age: int, out_dir: Path):
    """Save master table as Parquet (+ SQLite for 22), satellite tables as Parquet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    master = out["master"]
    cm, jm = out["committee_meetings"], out["judiciary_meetings"]

    pq_path = out_dir / f"master_bills_{age}.parquet"
    write_parquet(master, pq_path)
    log.info(f"\n  Saved: {pq_path.name} ({len(master):,} rows, {len(master.columns)} cols)")

    if age != CURRENT_AGE:
        cols = lite_columns(PROCESSED_DIR, age)
        lite = master.assign(eraco=f"제{age}대")[cols]
        write_parquet(lite, out_dir / f"master_bills_{age}_lite.parquet")
        log.info(f"  Saved: master_bills_{age}_lite.parquet ({len(lite.columns)} cols)")

    if age in SQLITE_AGES:
        db_path = out_dir / f"master_bills_{age}.sqlite"
        tmp = db_path.with_suffix(".sqlite.tmp")
        tmp.unlink(missing_ok=True)
        with sqlite3.connect(tmp) as conn:
            master.to_sql("bills", conn, if_exists="replace", index=False)
            if not cm.empty:
                cm.to_sql("committee_meetings", conn, if_exists="replace", index=False)
            if not jm.empty:
                jm.to_sql("judiciary_meetings", conn, if_exists="replace", index=False)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_bill_id ON bills(bill_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_bill_no ON bills(bill_no)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_ppsr_kind ON bills(ppsr_kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_committee ON bills(committee_nm)")
            if not cm.empty:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cm_bill_id ON committee_meetings(bill_id)")
            if not jm.empty:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jm_bill_id ON judiciary_meetings(bill_id)")
        conn.close()
        tmp.replace(db_path)
        log.info(f"  Saved: {db_path.name}")

    for name, df in [("committee_meetings", cm), ("judiciary_meetings", jm)]:
        if not df.empty:
            path = out_dir / f"{name}_{age}.parquet"
            write_parquet(df, path)
            log.info(f"  Saved: {path.name} ({len(df):,} rows)")


def save_combined(frames: list[pd.DataFrame], ages: list[int], path: Path,
                  cols: list[str], sort: list[str]):
    """Write an all-assembly table, replacing only the rows of the ages built now."""
    new = pd.concat([f for f in frames if not f.empty], ignore_index=True) \
        if any(not f.empty for f in frames) else pd.DataFrame(columns=cols)
    if path.exists():
        old = pd.read_parquet(path)
        new = pd.concat([old[~old["age"].isin(ages)], new], ignore_index=True)
    new = new[cols].sort_values(sort, kind="stable").reset_index(drop=True)
    new["age"] = new["age"].astype("int64")
    write_parquet(new, path)
    log.info(f"  Saved: {path.name} ({len(new):,} rows, ages "
             f"{sorted(new['age'].unique().tolist())})")


def print_summary(master: pd.DataFrame):
    """Print summary statistics of the master table."""
    log.info(f"\n{'='*60}")
    log.info("Master Database Summary")
    log.info(f"{'='*60}")
    log.info(f"  Total bills: {len(master):,}")
    log.info(f"  Columns: {len(master.columns)}")

    if "bill_kind" in master.columns:
        log.info(f"\n  Bill types:")
        for kind, cnt in master["bill_kind"].value_counts().items():
            log.info(f"    {kind}: {cnt:,}")

    if "ppsr_kind" in master.columns:
        log.info(f"\n  Proposer types:")
        for kind, cnt in master["ppsr_kind"].value_counts().items():
            log.info(f"    {kind}: {cnt:,}")

    if "status" in master.columns:
        log.info(f"\n  Processing status:")
        for status, cnt in master["status"].value_counts().head(10).items():
            log.info(f"    {status}: {cnt:,}")

    if "passed" in master.columns:
        total = len(master)
        passed = master["passed"].sum()
        log.info(f"\n  Passage rate: {passed:,}/{total:,} ({passed/total*100:.1f}%)")

    if "days_to_proc" in master.columns:
        valid = master["days_to_proc"].dropna()
        if len(valid) > 0:
            log.info(f"\n  Processing duration (days):")
            log.info(f"    Mean: {valid.mean():.0f}")
            log.info(f"    Median: {valid.median():.0f}")
            log.info(f"    Min: {valid.min():.0f}, Max: {valid.max():.0f}")

    if "committee_nm" in master.columns:
        log.info(f"\n  Top committees:")
        for comm, cnt in master["committee_nm"].value_counts().head(5).items():
            log.info(f"    {comm}: {cnt:,}")


# ── Old vs new comparison ──────────────────────────────────────────────────

def master_metrics(df: pd.DataFrame) -> dict:
    """Headline counts of one master table (works on the old and new schema)."""
    nonmember = df["ppsr_kind"] != "의원"
    m = {
        "rows": len(df),
        "columns": len(df.columns),
        "bill_no_duplicate_rows": int(len(df) - df["bill_no"].nunique()),
        "gov_prefix_rows": int(df["bill_id"].str.startswith("GOV_").sum()),
        "ppsr_kind_null": int(df["ppsr_kind"].isna().sum()),
        "pending_nonmember": int(((df["status"] == "계류중") & nonmember).sum()),
        "enacted": int(df["enacted"].sum()),
        "passed": int(df["passed"].sum()),
        "enacted_law": int(((df["enacted"] == 1) & (df["bill_kind"] == "법률안")).sum()),
        "enacted_law_without_prom_dt": int(((df["enacted"] == 1) & (df["bill_kind"] == "법률안")
                                            & df["prom_dt"].isna()).sum()),
        "promulgated": int(((df["bill_kind"] == "법률안") & df["prom_dt"].notna()).sum()),
        "law_reflected": int(df["law_reflected"].sum()) if "law_reflected" in df.columns
        else int(df["proc_rslt"].isin(LAW_REFLECTED_RESULTS).sum()),
        "vetoed": int(df["vetoed"].sum()) if "vetoed" in df.columns else None,
        "committee_nm_filled_nonmember": int((df["committee_nm"].notna() & nonmember).sum()),
        "nonmember_rows": int(nonmember.sum()),
        "days_to_proc_filled": int(df["days_to_proc"].notna().sum()),
        "days_to_committee_filled": int(df["days_to_committee"].notna().sum())
        if "days_to_committee" in df.columns else None,
        "vote_total_filled": int(df["vote_total"].notna().sum()) if "vote_total" in df.columns else 0,
    }
    for kind, n in df["ppsr_kind"].value_counts().items():
        m[f"ppsr_kind={kind}"] = int(n)
        m[f"proc_dt_filled|{kind}"] = int((df["proc_dt"].notna() & (df["ppsr_kind"] == kind)).sum())
    for s, n in df["status"].value_counts().items():
        m[f"status={s}"] = int(n)
    return m


def compare(old_dir: Path, new_dir: Path, ages: list[int]) -> pd.DataFrame:
    rows = []
    for age in ages:
        new_p = new_dir / f"master_bills_{age}.parquet"
        old_p = old_dir / f"master_bills_{age}.parquet"
        new = master_metrics(pd.read_parquet(new_p))
        old = master_metrics(pd.read_parquet(old_p)) if old_p.exists() else {}
        for name in ["committee_meetings", "judiciary_meetings"]:
            for d, side in [(new_dir, new), (old_dir, old)]:
                p = d / f"{name}_{age}.parquet"
                if p.exists():
                    m = pd.read_parquet(p)
                    side[f"{name}_rows"] = len(m)
                    side[f"{name}_exact_duplicates"] = int(m.duplicated().sum())
        for k in list(dict.fromkeys(list(old) + list(new))):
            o, n = old.get(k), new.get(k)
            d = (n or 0) - (o or 0) if (o is not None or n is not None) else None
            rows.append({"age": age, "metric": k, "old": o, "new": n, "diff": d})
    return pd.DataFrame(rows)


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build master bill lifecycle database")
    parser.add_argument("--age", type=int, help="One assembly (e.g. 22)")
    parser.add_argument("--ages", help="Several assemblies, e.g. 17-22 or 20,22 (default: 17-22)")
    parser.add_argument("--out", default=str(PROCESSED_DIR),
                        help="Output directory (default: data/processed)")
    parser.add_argument("--compare", help="Directory of the old outputs to compare against; "
                                          "writes {out}/reports/master_compare.csv")
    args = parser.parse_args()

    ages = [args.age] if args.age else parse_ages(args.ages) if args.ages else ALL_AGES
    out_dir = Path(args.out)
    start = time.time()
    vetoes, votes = [], []
    for age in ages:
        out = build_master(age)
        save_outputs(out, age, out_dir)
        print_summary(out["master"])
        vetoes.append(out["veto_events"])
        votes.append(out["vote_events"])

    log.info(f"\n{'='*60}")
    save_combined(vetoes, ages, out_dir / "veto_events.parquet", VETO_EVENT_COLS,
                  ["age", "veto_dt", "bill_no"])
    save_combined(votes, ages, out_dir / "vote_events.parquet", VOTE_EVENT_COLS,
                  ["age", "proc_dt", "bill_no", "vote_bill_id", "vote_event_id"])

    if args.compare:
        report = compare(Path(args.compare), out_dir, ages)
        rdir = out_dir / "reports"
        rdir.mkdir(parents=True, exist_ok=True)
        report.to_csv(rdir / "master_compare.csv", index=False, encoding="utf-8-sig")
        log.info(f"  Saved: reports/master_compare.csv ({len(report):,} rows)")

    elapsed = time.time() - start
    log.info(f"\nIntegration completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
