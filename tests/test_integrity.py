"""Integrity checks on a kna data build (the directory KBL_DATA points to).

Each check skips with the reason when its input file is missing, so the
suite runs on a partial staging build as well as on a full release.
"""

from __future__ import annotations

import re
import warnings

import pandas as pd
import pytest

from conftest import AGES, VOTE_AGES

# ── master_bills contract ───────────────────────────────────────────

LEGACY_COLS = [
    "bill_id", "bill_no", "age", "bill_kind", "bill_nm", "ppsr_kind",
    "proposer_text", "rst_proposer", "rst_mona_cd", "publ_proposer",
    "publ_mona_cd", "ppsl_dt", "committee_dt", "bdg_cmmt_dt", "cmt_present_dt",
    "jrcmit_prsnt_dt", "jrcmit_cmmt_dt", "cmt_proc_dt", "jrcmit_proc_dt",
    "law_submit_dt", "law_cmmt_dt", "law_present_dt", "law_prsnt_dt",
    "law_proc_dt", "rgs_prsnt_dt", "rgs_rsln_dt", "gvrn_trsf_dt", "prom_dt",
    "proc_dt", "jrcmit_proc_rslt", "cmt_proc_result_cd", "law_proc_rslt",
    "law_proc_result_cd", "rgs_conf_nm", "rgs_conf_rslt", "proc_rslt", "status",
    "passed", "enacted", "vote_result_cd", "vote_member_total", "vote_total",
    "vote_yes", "vote_no", "vote_abstain", "prom_no", "prom_law_nm",
    "committee_nm", "committee_id", "jrcmit_nm", "link_url", "member_list",
    "days_to_proc", "days_to_committee",
]
NEW_COLS = [
    "vetoed", "veto_bill_id", "veto_dt", "revote_rslt", "revote_dt",
    "first_plenary_rslt", "promulgated", "law_reflected", "alt_bill_id",
    "alt_vetoed", "expired_at_term_end", "plenary_decided", "vote_bill_id",
]
CONTRACT_COLS = LEGACY_COLS + NEW_COLS
DATE_COLS = [c for c in CONTRACT_COLS if c.endswith("_dt")]
FLAG_COLS = ["passed", "enacted", "vetoed", "promulgated", "law_reflected",
             "alt_vetoed", "expired_at_term_end", "plenary_decided"]
PASSED = ["원안가결", "수정가결", "대안반영폐기"]
ENACTED = ["원안가결", "수정가결"]


@pytest.mark.parametrize("age", AGES)
def test_master_has_contract_columns(kdata, age):
    names = kdata.schema(f"master_bills_{age}.parquet").names
    assert len(CONTRACT_COLS) == 67
    assert names == CONTRACT_COLS, (
        f"master_bills_{age}: missing {[c for c in CONTRACT_COLS if c not in names]}, "
        f"extra {[c for c in names if c not in CONTRACT_COLS]}")


def test_master_schema_identical_across_ages(kdata):
    schemas = {a: kdata.schema(f"master_bills_{a}.parquet") for a in AGES}
    ref = schemas[AGES[-1]]
    for a, s in schemas.items():
        assert s.equals(ref), f"master_bills_{a} schema differs from master_bills_{AGES[-1]}"


@pytest.mark.parametrize("age", AGES)
def test_master_dtypes(kdata, age):
    m = kdata.master(age)
    for c in DATE_COLS:
        if c in m.columns:
            assert pd.api.types.is_datetime64_dtype(m[c]), f"{c} is {m[c].dtype}"
    for c in FLAG_COLS:
        if c in m.columns:
            assert pd.api.types.is_integer_dtype(m[c]), f"{c} is {m[c].dtype}"
            assert set(m[c].unique()) <= {0, 1}, f"{c} has values {sorted(m[c].unique())}"


@pytest.mark.parametrize("age", AGES)
def test_bill_id_unique(kdata, age):
    m = kdata.master(age, ["bill_id"])
    dup = m.loc[m["bill_id"].duplicated(), "bill_id"]
    assert m["bill_id"].notna().all()
    assert dup.empty, f"duplicate bill_id: {dup.head(10).tolist()}"


@pytest.mark.parametrize("age", AGES)
def test_bill_no_unique(kdata, age):
    m = kdata.master(age, ["bill_no"])
    dup = m.loc[m["bill_no"].duplicated(), "bill_no"]
    assert dup.empty, f"{len(dup)} duplicate bill_no (unfolded veto pairs?): {dup.head(10).tolist()}"


@pytest.mark.parametrize("age", AGES)
def test_no_gov_record_counted_as_government_bill(kdata, age):
    # GOV_ ids are presidential reconsideration records. They must be folded
    # into the original bill, never counted as 정부 bills.
    m = kdata.master(age, ["bill_id", "ppsr_kind"])
    bad = m[m["bill_id"].str.startswith("GOV_") & (m["ppsr_kind"] == "정부")]
    assert bad.empty, f"GOV_ rows counted as 정부: {bad['bill_id'].tolist()}"


@pytest.mark.parametrize("age", AGES)
def test_enacted_implies_passed(kdata, age):
    m = kdata.master(age, ["bill_no", "passed", "enacted"])
    bad = m[(m["enacted"] == 1) & (m["passed"] != 1)]
    assert bad.empty, f"enacted but not passed: {bad['bill_no'].head(10).tolist()}"


@pytest.mark.parametrize("age", AGES)
def test_passed_and_enacted_definitions(kdata, age):
    m = kdata.master(age, ["status", "passed", "enacted"])
    assert (m["passed"] == m["status"].isin(PASSED).astype(int)).all()
    assert (m["enacted"] == m["status"].isin(ENACTED).astype(int)).all()


@pytest.mark.parametrize("age", AGES)
def test_vetoed_bills_rejected_on_revote_not_enacted(kdata, age):
    m = kdata.master(age)
    if "vetoed" not in m.columns:
        pytest.fail(f"master_bills_{age} has no vetoed column")
    v = m[(m["vetoed"] == 1) & (m["revote_rslt"] == "부결")]
    bad = v[(v["enacted"] != 0) | (v["passed"] != 0)]
    assert bad.empty, f"vetoed and rejected on the re-vote, still enacted: {bad['bill_no'].tolist()}"


def test_veto_events_match_master(kdata):
    ve = kdata.parquet("veto_events.parquet")
    for age in AGES:
        m = kdata.master(age, ["bill_id", "bill_no", "vetoed", "status", "enacted"])
        ev = ve[ve["age"] == age]
        vetoed = m[m["vetoed"] == 1]
        assert set(ev["bill_id"]) == set(vetoed["bill_id"]), f"{age}th: veto_events vs master vetoed"
        joined = ev.merge(m, on="bill_id", suffixes=("", "_m"))
        mism = joined[joined["final_status"] != joined["status"]]
        assert mism.empty, f"{age}th: final_status != master status for {mism['bill_no'].tolist()}"
        rejected = joined[joined["final_status"] == "부결"]
        assert (rejected["enacted"] == 0).all()


# ── shared table contracts ──────────────────────────────────────────

TABLE_CONTRACTS = {
    "veto_events.parquet": [
        "age", "bill_no", "bill_id", "veto_bill_id", "bill_nm", "ppsr_kind",
        "first_plenary_rslt", "first_plenary_dt", "veto_dt", "revote_rslt", "revote_dt",
        "final_status"],
    "vote_events.parquet": [
        "age", "vote_bill_id", "bill_no", "bill_nm", "proc_dt", "vote_type",
        "master_bill_id", "member_tcnt", "vote_tcnt", "yes", "no", "abstain", "result"],
    "alternative_absorption.parquet": [
        "age", "alt_bill_id", "alt_bill_no", "absorbed_bill_id", "absorbed_bill_no",
        "absorbed_proc_rslt"],
    "cosponsorship_edges.parquet": [
        "bill_id", "member_name", "member_id", "party", "role", "age", "bill_no",
        "party_source", "source"],
    "roll_calls_all.parquet": [
        "term", "meeting_id", "date", "member_name", "vote", "source", "bill_id",
        "bill_context", "party", "district", "member_id", "vote_event", "agg_total",
        "agg_yes", "bill_no", "party_api"],
    "roll_calls_16_19_experimental.parquet": [
        "term", "meeting_id", "date", "member_name", "vote", "source", "bill_id",
        "bill_context", "party", "district", "member_id", "vote_event", "agg_total",
        "agg_yes", "quality_flag"],
}


@pytest.mark.parametrize("fname", sorted(TABLE_CONTRACTS))
def test_table_contract_columns(kdata, fname):
    names = kdata.schema(fname).names
    assert names == TABLE_CONTRACTS[fname], f"{fname}: {names}"


# ── roll calls ──────────────────────────────────────────────────────

# Bills whose roll call has two tally rows in the API; the member-level
# votes match one of them (reported in reports/rollcall_tally_check.csv).
EXPLAINED_TALLIES = {(20, "2000491")}


def _rc(kdata, columns=None):
    return kdata.parquet("roll_calls_all.parquet", columns)


def test_roll_calls_unique(kdata):
    rc = _rc(kdata, ["term", "bill_id", "member_id"])
    assert rc["member_id"].notna().all(), "roll_calls_all has rows without member_id"
    dup = rc[rc.duplicated(["term", "bill_id", "member_id"], keep=False)]
    assert dup.empty, f"{len(dup)} rows duplicate (term, bill_id, member_id)"


def test_roll_calls_sorted(kdata):
    # Explicit row order: the ideal-point inputs depend on it
    keys = ["term", "date", "bill_id", "member_id"]
    rc = _rc(kdata, keys)
    assert rc.equals(rc.sort_values(keys, kind="mergesort").reset_index(drop=True)), (
        "roll_calls_all is not sorted by term, date, bill_id, member_id")


def test_roll_calls_cover_20_22_only(kdata):
    terms = set(_rc(kdata, ["term"])["term"].unique())
    assert terms <= set(VOTE_AGES), (
        f"roll_calls_all holds terms {sorted(terms)}; the 16th-19th rows belong in "
        "roll_calls_16_19_experimental.parquet")


def _tally_comparison(kdata) -> pd.DataFrame:
    """Y/N/A per (term, bill_id) against every tally row of that vote."""
    rc = _rc(kdata, ["term", "bill_id", "vote"])
    counts = (rc.groupby(["term", "bill_id"])["vote"].value_counts()
              .unstack(fill_value=0).reset_index())
    for c in ["찬성", "반대", "기권"]:
        if c not in counts.columns:
            counts[c] = 0
    ve = kdata.parquet("vote_events.parquet").rename(
        columns={"age": "term", "vote_bill_id": "bill_id"})
    m = counts.merge(ve[["term", "bill_id", "bill_no", "vote_type", "yes", "no", "abstain"]],
                     on=["term", "bill_id"], how="outer", indicator=True)
    m["ok"] = ((m["찬성"] == m["yes"]) & (m["반대"] == m["no"])
               & (m["기권"] == m["abstain"]))
    # A re-vote on a vetoed (returned) bill is a secret ballot, so it has a
    # tally but no member-level rows
    secret = (m["_merge"] == "right_only") & (m["vote_type"] == "reconsideration")
    return m[~secret]


@pytest.mark.parametrize("term", [20, 21])
def test_roll_calls_match_tallies(kdata, term):
    m = _tally_comparison(kdata)
    m = m[m["term"] == term]
    one_side = m[m["_merge"] != "both"]
    assert one_side.empty, (
        f"{term}th: {len(one_side)} votes only in roll calls or only in vote_events: "
        f"{one_side['bill_id'].head(5).tolist()}")
    by_vote = m.groupby(["term", "bill_id", "bill_no"])["ok"].any().reset_index()
    explained = by_vote.apply(lambda r: (r["term"], r["bill_no"]) in EXPLAINED_TALLIES, axis=1)
    bad = by_vote[~by_vote["ok"] & ~explained]
    assert bad.empty, f"{term}th: {len(bad)} votes differ from the tally: {bad['bill_no'].head(10).tolist()}"


def test_roll_calls_22_tally_report(kdata):
    # Reported, not asserted: the 22nd member-level feed omits 16 members
    # seated in 2026, so later votes have fewer rows than MEMBER_TCNT.
    m = _tally_comparison(kdata)
    m = m[m["term"] == 22]
    if m.empty:
        pytest.skip("no 22nd votes in roll_calls_all")
    by_vote = m.groupby("bill_id")["ok"].any()
    warnings.warn(
        f"22nd roll calls: {int(by_vote.sum())} of {len(by_vote)} votes match the tally "
        f"exactly; {int((~by_vote).sum())} differ (see reports/rollcall_tally_check.csv)",
        UserWarning)


def test_same_name_legislators_keep_both(kdata):
    # Regression for the member_name dedup that dropped 12,418 votes of
    # same-name pairs. Known pairs must both be present, and wherever both
    # members voted, some vote carries a row for each.
    known = {20: {"김성태", "최경환"}, 21: {"김병욱", "이수진"}}
    rc = _rc(kdata, ["term", "bill_id", "member_id", "member_name"])
    checked = 0
    for term in VOTE_AGES:
        if not kdata.has(f"members_{term}.parquet"):
            continue
        mem = kdata.members(term)
        groups = mem.groupby("member_name")["mona_cd"].unique()
        groups = groups[groups.map(len) > 1]
        rt = rc[rc["term"] == term]
        for name, ids in groups.items():
            present = sorted(set(ids) & set(rt["member_id"]))
            if name in known.get(term, set()):
                assert len(present) == len(ids), f"{term}th {name}: only {present} of {list(ids)} in roll calls"
            if len(present) < 2:
                continue
            per_bill = rt[rt["member_id"].isin(present)].groupby("bill_id")["member_id"].nunique()
            assert (per_bill >= 2).any(), f"{term}th {name}: never both on one vote"
            checked += 1
    if checked == 0:
        pytest.skip("no same-name pair with both members in roll_calls_all")


def test_roll_call_party_is_party_at_election(kdata):
    rc = _rc(kdata, ["term", "member_id", "party"]).drop_duplicates()
    for term in VOTE_AGES:
        if not kdata.has(f"members_{term}.parquet"):
            continue
        mem = kdata.members(term)[["mona_cd", "party"]].rename(columns={"mona_cd": "member_id"})
        j = rc[rc["term"] == term].merge(mem, on="member_id", suffixes=("", "_elected"))
        bad = j[j["party"] != j["party_elected"]]
        assert bad.empty, f"{term}th: {bad['member_id'].nunique()} members' party differs from members_{term}.party"


# ── members ─────────────────────────────────────────────────────────

# Official per-assembly seniority counts: Open Assembly 역대 국회의원 재선 현황
# (endpoint ngdeoqgoablceakpp), fetched 2026-09-24 in the data audit
# (audit/SIMILAR/seniority_benchmark.csv, column "official"). The table stops
# at the 21st, and the 17th differs by one member (205 vs 206 초선), so the
# 18th-21st are asserted.
OFFICIAL_SENIORITY = {
    18: {"초선": 159, "재선": 91, "3선": 47, "4선": 21, "5선": 7, "6선": 5, "7선": 1},
    19: {"초선": 171, "재선": 73, "3선": 53, "4선": 19, "5선": 11, "6선": 3, "7선": 2},
    20: {"초선": 150, "재선": 70, "3선": 48, "4선": 35, "5선": 10, "6선": 5, "7선": 1, "8선": 1},
    21: {"초선": 168, "재선": 75, "3선": 43, "4선": 20, "5선": 15, "6선": 1},
}


@pytest.mark.parametrize("age", AGES)
def test_members_mona_unique(kdata, age):
    mem = kdata.members(age)
    assert mem["mona_cd"].notna().all()
    dup = mem.loc[mem["mona_cd"].duplicated(), "mona_cd"]
    assert dup.empty, f"members_{age}: duplicate mona_cd {dup.tolist()}"


@pytest.mark.parametrize("age", sorted(OFFICIAL_SENIORITY))
def test_seniority_matches_official(kdata, age):
    mem = kdata.members(age)
    assert "seniority" in mem.columns, f"members_{age} has no seniority column"
    got = mem["seniority"].value_counts().to_dict()
    assert got == OFFICIAL_SENIORITY[age]


# ── cosponsorship edges ─────────────────────────────────────────────

def text_total(text) -> int | None:
    """Number of proposers stated in a PROPOSER text.

    '등 N인' gives the proposers, otherwise the named 의원 are counted;
    '외 M인' adds the supporters (찬성). '강창희의원 등 6인 외 94인' -> 100.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    head = str(text).split("외")[0]
    m = re.search(r"등\s*(\d+)\s*인", head)
    n = int(m.group(1)) if m else len(re.findall(r"의원", head))
    extra = re.search(r"외\s*(\d+)\s*인", str(text))
    return n + (int(extra.group(1)) if extra else 0)


def test_text_total_parser():
    assert text_total("임태희의원등 100인") == 100
    assert text_total("강창희의원 등 6인 외 94인") == 100
    assert text_total("박홍근의원ㆍ이헌승의원ㆍ심상정의원 등 18인") == 18
    assert text_total("A의원ㆍB의원ㆍC의원 외 185인") == 188


def test_cosponsorship_not_capped_at_100(kdata):
    # The upstream file stopped at 100 rows per bill. A bill may have exactly
    # 100 edges only when its PROPOSER text says 100.
    e = kdata.parquet("cosponsorship_edges.parquet", ["bill_id", "age"])
    n = e.groupby(["age", "bill_id"]).size().rename("n").reset_index()
    at100 = n[n["n"] == 100]
    if at100.empty:
        return
    texts = pd.concat([kdata.master(a, ["bill_id", "bill_no", "proposer_text"]).assign(age=a)
                       for a in sorted(at100["age"].unique())])
    j = at100.merge(texts, on=["age", "bill_id"], how="left")
    j["stated"] = j["proposer_text"].map(text_total)
    bad = j[j["stated"] != 100]
    assert bad.empty, (
        f"{len(bad)} bills have exactly 100 edges but their text states otherwise: "
        f"{bad[['age', 'bill_no', 'proposer_text']].head(10).values.tolist()}")


# ── committee meetings ──────────────────────────────────────────────

def _max_rows_per_bill(df: pd.DataFrame) -> int:
    cols = {c.lower(): c for c in df.columns}
    tag = cols.get("bill_id_tagged") or cols.get("_bill_id")
    key = df[tag].fillna(df[cols["bill_id"]]) if tag else df[cols["bill_id"]]
    return int(key.value_counts().max()) if len(key) else 0


@pytest.mark.parametrize("age", [17, 18, 19, 20])
def test_committee_meetings_not_capped_at_5(kdata, age):
    # BILLJUDGECONF used to return at most 5 rows per bill for the 17th-20th.
    built = _max_rows_per_bill(kdata.parquet(f"committee_meetings_{age}.parquet"))
    if built > 5:
        return
    raw = kdata.raw / f"BILLJUDGECONF_{age}.parquet"
    if not raw.exists():
        pytest.skip(f"committee_meetings_{age} is capped at {built} rows per bill and "
                    f"{raw} is not available to tell whether the re-fetch is complete")
    raw_max = _max_rows_per_bill(pd.read_parquet(raw))
    if raw_max <= 5:
        pytest.skip(f"BILLJUDGECONF_{age} re-fetch not complete: the raw file is still "
                    f"capped at {raw_max} rows per bill")
    pytest.fail(f"raw BILLJUDGECONF_{age} is complete ({raw_max} rows for one bill) but "
                f"committee_meetings_{age} is capped at {built}: rerun integrate.py")


@pytest.mark.parametrize("age", AGES)
@pytest.mark.parametrize("stem", ["committee_meetings", "judiciary_meetings"])
def test_meeting_tables_lowercase_without_duplicates(kdata, stem, age):
    df = kdata.parquet(f"{stem}_{age}.parquet")
    assert list(df.columns) == [c.lower() for c in df.columns], f"{stem}_{age}: uppercase columns"
    assert "bill_id_tagged" in df.columns
    assert not df.duplicated().any(), f"{stem}_{age}: {int(df.duplicated().sum())} exact duplicate rows"


# ── ideal points ────────────────────────────────────────────────────

@pytest.mark.parametrize("series", ["bridged", "wnominate", "dwnominate"])
def test_ideal_points_join_members(kdata, series):
    ip = kdata.csv(f"ideal_points_{series}.csv")
    dup = ip[ip.duplicated(["member_id", "term"])]
    assert dup.empty, f"duplicate (member_id, term): {dup[['member_id', 'term']].values.tolist()}"
    mem = pd.concat([kdata.members(t) for t in sorted(ip["term"].unique())])
    mem = mem[["mona_cd", "age", "member_name"]].rename(columns={"mona_cd": "member_id", "age": "term"})
    j = ip.merge(mem, on=["member_id", "term"], how="left", suffixes=("", "_members"),
                 indicator=True)
    orphans = j[j["_merge"] != "both"]
    assert orphans.empty, f"not in members: {orphans[['member_id', 'term']].values.tolist()}"
    renamed = j[j["member_name"] != j["member_name_members"]]
    assert renamed.empty, f"name differs from members: {renamed[['member_id', 'term']].values.tolist()}"
