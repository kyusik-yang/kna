"""Contract tests for the Python API (kna.data.BillDB and kna.queries)."""

from __future__ import annotations

import pandas as pd
import pytest

from conftest import AGES
from kna import queries as q
from kna.data import BillDB

MEETING_COLS = {
    "committee_meetings": ["eraco", "bill_id", "bill_no", "bill_nm", "ppsr", "ppsl_dt",
                           "jrcmit_conf_nm", "jrcmit_conf_dt", "jrcmit_conf_rslt",
                           "bill_id_tagged"],
    "judiciary_meetings": ["eraco", "bill_id", "bill_no", "bill_nm", "ppsr", "ppsl_dt",
                           "lwcmit_conf_nm", "lwcmit_conf_dt", "lwcmit_conf_rslt",
                           "bill_id_tagged"],
}


@pytest.fixture(scope="module")
def db(data_dir) -> BillDB:
    return BillDB(data_dir)


def _need(db, name):
    if not (db.data_dir / name).exists():
        pytest.skip(f"{name} not in {db.data_dir}")


# ── loaders ─────────────────────────────────────────────────────────

def test_bills_prunes_columns(db):
    cols = ["bill_id", "bill_nm", "status", "ppsl_dt"]
    df = db.bills(assembly=22, columns=cols)
    assert list(df.columns) == cols


def test_bills_warns_on_unknown_columns(db):
    with pytest.warns(UserWarning, match="nonexistent"):
        df = db.bills(assembly=17, columns=["bill_id", "nonexistent"])
    assert list(df.columns) == ["bill_id"]


def test_roll_calls_columns_without_term(db):
    _need(db, "roll_calls_all.parquet")
    df = db.roll_calls(assembly=22, columns=["member_id", "vote"])
    assert list(df.columns) == ["member_id", "vote"]
    full = db.roll_calls(assembly=22, columns=["term"])
    assert len(df) == len(full) > 0 and (full["term"] == 22).all()


@pytest.mark.parametrize("age", AGES)
@pytest.mark.parametrize("stem", sorted(MEETING_COLS))
def test_meeting_loaders_lowercase(db, stem, age):
    _need(db, f"{stem}_{age}.parquet")
    df = getattr(db, stem)(age)
    assert list(df.columns) == MEETING_COLS[stem]
    sub = getattr(db, stem)(age, columns=["bill_id", "bill_id_tagged"])
    assert list(sub.columns) == ["bill_id", "bill_id_tagged"]


@pytest.mark.parametrize("loader,fname,cols", [
    ("committee_assignments", "committee_assignments.parquet",
     ["mona_cd", "assembly", "committee", "start_date", "end_date"]),
    ("subcommittee_reviews", "subcommittee_reviews.parquet", ["age", "bill_id", "sub_committee_name"]),
    ("alternative_absorption", "alternative_absorption.parquet",
     ["age", "alt_bill_id", "alt_bill_no", "absorbed_bill_id", "absorbed_bill_no",
      "absorbed_proc_rslt"]),
    ("cosponsorship_edges", "cosponsorship_edges.parquet",
     ["bill_id", "member_name", "member_id", "party", "role", "age", "bill_no",
      "party_source", "source"]),
    ("veto_events", "veto_events.parquet",
     ["age", "bill_no", "bill_id", "veto_bill_id", "bill_nm", "ppsr_kind",
      "first_plenary_rslt", "first_plenary_dt", "veto_dt", "revote_rslt", "revote_dt",
      "final_status"]),
    ("vote_events", "vote_events.parquet",
     ["age", "vote_bill_id", "bill_no", "bill_nm", "proc_dt", "vote_type", "master_bill_id",
      "member_tcnt", "vote_tcnt", "yes", "no", "abstain", "result"]),
    ("roll_calls_16_19_experimental", "roll_calls_16_19_experimental.parquet",
     ["term", "member_name", "vote", "quality_flag"]),
])
def test_new_loaders(db, loader, fname, cols):
    _need(db, fname)
    df = getattr(db, loader)()
    assert len(df) > 0
    missing = [c for c in cols if c not in df.columns]
    assert not missing, f"{loader}: missing {missing}"


def test_assembly_filters(db):
    _need(db, "cosponsorship_edges.parquet")
    e = db.cosponsorship_edges(21, columns=["bill_id", "member_id"])
    assert list(e.columns) == ["bill_id", "member_id"] and len(e) > 0
    _need(db, "committee_assignments.parquet")
    assert (db.committee_assignments(21)["assembly"] == 21).all()


def test_members_pass_new_columns_through(db):
    mem = db.members(assembly=22)
    for c in ["mona_cd", "member_name", "party", "district", "seniority", "term_number"]:
        assert c in mem.columns, f"members_22 has no {c}"


@pytest.mark.parametrize("series", ["bridged", "wnominate", "dwnominate"])
def test_ideal_points_api(db, series):
    _need(db, f"ideal_points_{series}.csv")
    ip = db.ideal_points(series)
    for c in ["member_id", "member_name", "party", "term", "ideal_point"]:
        assert c in ip.columns
    assert set(ip["term"].unique()) <= {20, 21, 22}


# ── queries ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("age", AGES)
def test_funnel_monotone(db, age):
    stages = q.funnel_stats(db, age)
    counts = [c for _, c in stages]
    assert counts == sorted(counts, reverse=True), stages
    law = db.bills(assembly=age, columns=["bill_kind", "plenary_decided", "promulgated"])
    law = law[law["bill_kind"] == "법률안"]
    by_label = dict(stages)
    assert by_label["본회의 의결"] == int((law["plenary_decided"] == 1).sum())
    assert by_label["공포"] == int((law["promulgated"] == 1).sum())


def test_status_groups_cover_statuses(db):
    groups = set().union(*q.STATUS_GROUPS.values())
    assert {"임기만료폐기", "수정안반영폐기"} <= groups
    seen = set()
    for a in AGES:
        seen |= set(db.bills(assembly=a, columns=["status"])["status"].dropna().unique())
    # A few one-off upstream statuses (가결, 심사대상제외) stay unmapped
    uncovered = seen - groups - {"가결", "심사대상제외"}
    assert not uncovered, f"statuses in no --status group: {uncovered}"


def test_passage_rate_uses_law_basis(db):
    for r in q.passage_rate_stats(db):
        b = db.bills(assembly=r["age"], columns=["bill_kind", "enacted", "promulgated"])
        law = b[b["bill_kind"] == "법률안"]
        assert r["total"] == len(law)
        assert r["enacted"] == int(law["enacted"].sum())
        assert r["promulgated"] == int(law["promulgated"].sum())


def _pair(db, age, name):
    mem = db.members(assembly=age)
    ids = sorted(mem.loc[mem["member_name"] == name, "mona_cd"])
    if len(ids) < 2:
        pytest.skip(f"{name} is not a same-name pair in the {age}th members")
    return ids


@pytest.mark.parametrize("age,name", [(21, "김병욱"), (21, "이수진"), (20, "김성태")])
def test_same_name_requires_mona(db, age, name):
    ids = _pair(db, age, name)
    with pytest.raises(q.AmbiguousLegislator) as err:
        q.get_legislator_profile(db, name, age=age)
    assert sorted(err.value.candidates["mona_cd"].unique()) == ids
    for mona in ids:
        p = q.get_legislator_profile(db, name, age=age, mona=mona)
        codes = p["bills_df"]["rst_mona_cd"].fillna("").str.split(",")
        assert codes.map(lambda xs: mona in [x.strip() for x in xs]).all()
        m = db.bills(assembly=age, columns=["rst_mona_cd"])["rst_mona_cd"].fillna("")
        expected = m.str.split(",").map(lambda xs: mona in [x.strip() for x in xs]).sum()
        assert len(p["bills_df"]) == expected
        assert p["term"] == age


def test_name_is_not_substring_matched(db):
    # 김현 and 김현정 both sit in the 22nd; the profile of 김현 is only 김현's
    mem = db.members(assembly=22)
    kim = mem[mem["member_name"] == "김현"]
    other = mem[mem["member_name"] == "김현정"]
    if len(kim) != 1 or other.empty:
        pytest.skip("김현/김현정 not both in members_22")
    p = q.get_legislator_profile(db, "김현", age=22)
    assert p["mona"] == kim["mona_cd"].iloc[0]
    assert p["district"] == kim["district"].iloc[0]
    # Every bill carries 김현's own code (김현정's bills only if co-led with 김현)
    codes = p["bills_df"]["rst_mona_cd"].fillna("").str.split(",")
    assert codes.map(lambda xs: p["mona"] in [x.strip() for x in xs]).all()
    assert q.get_legislator_profile(db, "김", age=22) is None


def test_joint_lead_bills_are_included(db):
    b = db.bills(assembly=22, columns=["bill_id", "rst_mona_cd"])
    joint = b[b["rst_mona_cd"].fillna("").str.contains(",")]
    if joint.empty:
        pytest.skip("no joint-lead bills in the 22nd")
    bill = joint.iloc[0]
    second = bill["rst_mona_cd"].split(",")[1].strip()
    p = q.get_legislator_profile(db, "", age=22, mona=second)
    assert p is not None and bill["bill_id"] in set(p["bills_df"]["bill_id"])


def test_show_finds_vetoed_bill_by_reconsideration_id(db):
    # GOV_ reconsideration records are folded into the original bill, so a
    # GOV_ id must still resolve to that bill, with its first floor date
    _need(db, "veto_events.parquet")
    ve = db.veto_events()
    folded = ve[ve["veto_bill_id"].notna() & (ve["veto_bill_id"] != ve["bill_id"])]
    if folded.empty:
        pytest.skip("no folded veto pairs in veto_events")
    for _, ev in folded.iterrows():
        row = q.get_bill_detail(db, ev["veto_bill_id"])
        assert row is not None, f"{ev['veto_bill_id']} not found"
        assert row["bill_id"] == ev["bill_id"]
        if pd.notna(ev["first_plenary_dt"]):
            floor = row.get("rgs_rsln_dt")
            if floor is None or pd.isna(floor):
                floor = row.get("first_plenary_dt")
            assert pd.notna(floor), f"{ev['bill_no']}: no first floor date for show"


def test_ideal_point_is_labelled_with_its_term(db):
    _need(db, "ideal_points_bridged.csv")
    ip = db.ideal_points()
    multi = ip.groupby("member_id")["term"].nunique()
    mona = multi[multi > 1].index[0]
    rows = ip[ip["member_id"] == mona].sort_values("term")
    first = int(rows["term"].iloc[0])
    p = q.get_legislator_profile(db, "", age=first, mona=mona)
    assert p["term"] == first
    assert p["ideal_point"] == pytest.approx(float(rows["ideal_point"].iloc[0]))
    # Without an assembly every term is listed, each with its own value
    p_all = q.get_legislator_profile(db, "", mona=mona)
    t = p_all["terms"].dropna(subset=["ideal_point"])
    got = dict(zip(t["age"], t["ideal_point"]))
    want = dict(zip(rows["term"], rows["ideal_point"]))
    assert got == pytest.approx(want)
