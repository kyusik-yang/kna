"""Tests for the 17th-19th roll calls parsed from the plenary minutes PDFs.

collect_minutes_votes.py and minutes_votes.py write
data/raw/minutes_votes_{age}.parquet (one row per printed name) and
data/raw/minutes_vote_events_{age}.parquet (one row per recorded vote).
integrate.py adds the votes to vote_events.parquet and the master's vote_*
columns, and consolidate_votes.py adds the names to roll_calls_all with
source 'minutes_pdf'.

The unit tests need no data. The raw-data tests read KNA_RAW_DIR (default
data/raw), the build tests the directory under test (KBL_DATA), and the
comparison with kr-hearings-data v10 reads KNA_V10_DIR (default
~/Desktop/kyusik-github/kr-hearings-data/v10/build/release). Each skips when
its input is missing. Rates are reported as warnings.
"""

from __future__ import annotations

import os
import unicodedata
import warnings
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

import minutes_votes as mv

AGES = [17, 18, 19]
V10_DIR = Path(os.getenv("KNA_V10_DIR", Path.home() / "Desktop/kyusik-github/kr-hearings-data"
                         "/v10/build/release")).expanduser()
UNRESOLVED = {"unresolved_same_name", "printed_on_two_lists", "unmatched"}
PASSED = {"원안가결", "수정가결", "가결"}

# Votes whose appendix lists fewer or more names than its printed group count.
# 17_27974_047 prints 찬성 의원(207인) over 206 names (the chair also says 206).
# 18_34052_012 prints 찬성 의원(176인), the count its correction note gives,
# over the 175 names of the machine record.
NAMES_NOT_PRINTED_COUNT = {"17_27974_047", "18_34052_012"}


# ── unit tests ──────────────────────────────────────────────────────

def test_line_tokens_both_layouts():
    assert mv.line_tokens("강기윤  강기정  김  현  김현미") == ["강기윤", "강기정", "김", "현", "김현미"]
    # 17th layout: every syllable spaced, names three spaces apart
    assert mv.line_tokens("  문 희 상   민 병 두   문    희") == ["문희상", "민병두", "문", "희"]


def test_single_syllables_join_only_into_members():
    known = {"김현", "문희", "진영"}
    names, junk = mv.tokens_to_names(["김", "현", "제", "안", "진", "영"], known)
    assert names == ["김현", "진영"] and junk == ["제", "안"]


def _body(text: str) -> list[str]:
    return text.split("\n")


@pytest.mark.parametrize("line,counts", [
    ("재석 237인 중 찬성 236인, 반대 없고, 기권 1인으로서 관세법은 가결되었음을 선포합니다.",
     (237, 236, 0, 1)),
    ("재석 209인 중 찬성 198인, 기권 9인, 반대 2인으로서 경제교육지원법은 가결되었음을",
     (209, 198, 2, 9)),
    ("재석 174인 중 찬성 역시 174인, 산업발전법 일부개정법률안은 가결되었음을 선포합니다.",
     (174, 174, 0, 0)),
    ("투표 결과를 말씀드리겠습니다. 194인 중 189인 찬성, 반대 1인, 기권 4인으로서 영화진흥법은 가결",
     (194, 189, 1, 4)),
    ("재석 170인 중 만장일치로 가결되었음을 선포합니다.", (170, 170, 0, 0)),
])
def test_chair_announcement_variants(line, counts):
    anns, _, _ = mv.parse_body(_body(line + "\n(찬반 의원 성명은 끝에 실음)"), 2, "2008-01-01")
    a = anns[0]
    assert (a["present"], a["yes"], a["no"], a["abstain"]) == counts
    assert a["marker"]


def test_misspoken_counts_are_not_read():
    # '반대 191인, 반대 5인' (18th, 34089): the chair's yes count is missing
    anns, _, _ = mv.parse_body(_body("재석 201인 중 반대 191인, 반대 5인, 기권 5인으로서 은행법은 가결"),
                               1, "2010-01-01")
    assert anns == []


def test_date_advances_past_midnight():
    lines = ["재석 200인 중 찬성 200인으로서 가법은 가결되었음을", "(2월23일 24시 경과)",
             "(2월24일 24시 경과)", "재석 201인 중 찬성 201인으로서 나법은 가결되었음을"]
    anns, _, _ = mv.parse_body(lines, len(lines), "2016-02-23")
    assert [a["date"] for a in anns] == ["2016-02-23", "2016-02-25"]


APPENDIX = """【전자투표 찬반 의원 성명】
◯가법 일부개정법률안에 대한 수정안
<1차 투표>
  투표 의원(3인)
  찬성 의원(2인)
강기윤  김  현
  기권 의원(1인)
문희상
<2차 투표>
  투표 의원(3인)
  찬성 의원(3인)
강기윤  김  현  문희상
(강기윤 의원 표결기 조작 지체. 실제 찬성
의원 3인임
◯나법 일부개정법률안
  투표 의원(2인)
  찬성 의원(2인)
강기윤  김  현
◯출석 의원(3인)
강기윤  김  현  문희상"""


def test_appendix_revote_and_unterminated_note():
    known = {"강기윤", "김현", "문희상"}
    ev = mv.parse_rollcall_section(APPENDIX.split("\n"), 0, known)
    assert [(e.title, e.revote_seq) for e in ev] == [
        ("가법 일부개정법률안에 대한 수정안", 1), ("가법 일부개정법률안에 대한 수정안", 2),
        ("나법 일부개정법률안", 1)]
    assert ev[0].notes == ["<1차 투표>"] and ev[1].notes[0] == "<2차 투표>"
    assert "실제 찬성" in ev[1].notes[1]           # the note lost its ')' but ends at the ◯
    assert ev[0].groups["찬성"].names == ["강기윤", "김현"]
    assert ev[0].groups["기권"].names == ["문희상"]
    assert ev[2].groups["찬성"].names == ["강기윤", "김현"]   # ◯출석 의원 is not a vote


def test_note_counts():
    note = "(박진 의원 표결기 조작 지체. 실제 투표 의원 208인, 기권 의원 3인임)"
    assert mv.note_counts_match(note, {"투표": 208, "찬성": 205, "반대": 0, "기권": 3}) is True
    assert mv.note_counts_match(note, {"투표": 209, "찬성": 206, "반대": 0, "기권": 3}) is False
    assert mv.note_counts_match("<2차 투표>", {"투표": 1}) is None


def test_dueum_folds_initial_sounds():
    assert mv.dueum("국민년금법") == mv.dueum("국민연금법")
    assert mv.dueum("류근찬") == mv.dueum("유근찬")


def _roster():
    return pd.DataFrame({
        "mona_cd": ["A", "B", "C"],
        "member_name": ["김선동", "김선동", "강기윤"],
        "member_name_hanja": ["金善東", "金先東", "姜起潤"],
        "party": ["x", "y", "z"], "district": ["d", "e", "f"]}).assign(
        hanja_n=lambda d: d["member_name_hanja"])


def test_same_name_rules(monkeypatch):
    monkeypatch.setitem(mv.SAME_NAME, 99, {"김선동": {"A": (None, None), "B": ("2011-04-29", None)}})
    rows = [
        # before B's oath: A alone
        ("e1", "2011-04-05", "찬성", "김선동"),
        # B printed in Hanja, the Hangul row is A
        ("e2", "2011-05-01", "찬성", "金先東"), ("e2", "2011-05-01", "반대", "김선동"),
        # Hangul twice, same vote: one row each
        ("e3", "2011-05-01", "찬성", "김선동"), ("e3", "2011-05-01", "찬성", "김선동"),
        # Hangul twice, different votes: unresolved
        ("e4", "2011-05-01", "찬성", "김선동"), ("e4", "2011-05-01", "기권", "김선동"),
        # Hangul once, no Hanja: unresolved
        ("e5", "2011-05-01", "찬성", "김선동"),
        ("e5", "2011-05-01", "찬성", "강기윤"),
    ]
    nm = pd.DataFrame(rows, columns=["vote_event_id", "date", "vote", "name_raw"])
    out = mv.resolve_names(nm, _roster(), 99)
    got = list(zip(out["vote_event_id"], out["member_id"], out["member_match"]))
    assert got == [
        ("e1", "A", "same_name_seated_alone"),
        ("e2", "B", "hanja"), ("e2", "A", "same_name_event_hanja"),
        ("e3", "A", "same_name_pair_same_vote"), ("e3", "B", "same_name_pair_same_vote"),
        ("e4", None, "unresolved_same_name"), ("e4", None, "unresolved_same_name"),
        ("e5", None, "unresolved_same_name"), ("e5", "C", "name")]


def test_hanja_outside_seat_dates_stops(monkeypatch):
    monkeypatch.setitem(mv.SAME_NAME, 99, {"김선동": {"A": (None, None), "B": ("2011-04-29", None)}})
    nm = pd.DataFrame([("e1", "2011-04-05", "찬성", "金先東")],
                      columns=["vote_event_id", "date", "vote", "name_raw"])
    with pytest.raises(SystemExit):
        mv.resolve_names(nm, _roster(), 99)


def test_name_printed_twice_is_kept_once():
    n = pd.DataFrame({"vote_event_id": ["e1"] * 3, "member_id": ["A", "B", "A"],
                      "member_match": ["name"] * 3, "vote": ["찬성"] * 3,
                      "name_raw": ["원혜영", "우제항", "원혜영"]})
    out, twice = mv.drop_printed_twice(n, 17)
    assert list(out["member_id"]) == ["A", "B"] and twice["e1"] == "원혜영"


# ── raw data ────────────────────────────────────────────────────────

def _raw(kdata, name: str) -> pd.DataFrame:
    p = kdata.raw / name
    if not p.exists():
        pytest.skip(f"{name} not in {kdata.raw}")
    return pd.read_parquet(p)


def _events(kdata, age):
    return _raw(kdata, f"minutes_vote_events_{age}.parquet")


def _votes(kdata, age):
    return _raw(kdata, f"minutes_votes_{age}.parquet")


@pytest.mark.parametrize("age", AGES)
def test_names_equal_printed_counts(kdata, age):
    e = _events(kdata, age)
    off = set(e.loc[~e["names_equal_printed"], "vote_event_id"])
    assert off == {x for x in NAMES_NOT_PRINTED_COUNT if x.startswith(f"{age}_")}
    # the counts are those of the member-vote rows
    v = _votes(kdata, age)
    c = v.groupby(["vote_event_id", "vote"]).size().unstack(fill_value=0)
    e = e.set_index("vote_event_id")
    for lab, col in [("찬성", "names_yes"), ("반대", "names_no"), ("기권", "names_abstain")]:
        got = c[lab].reindex(e.index, fill_value=0) if lab in c.columns else 0
        assert (got == e[col]).all(), f"{age}th {col} differs from the rows"


@pytest.mark.parametrize("age", AGES)
def test_votes_keys(kdata, age):
    e, v = _events(kdata, age), _votes(kdata, age)
    assert e["vote_event_id"].is_unique
    assert set(v["vote_event_id"]) <= set(e["vote_event_id"])
    assert (e["names_total"] > 0).all(), "a recorded vote without names"
    known = v[v["member_id"].notna()]
    assert not known.duplicated(["vote_event_id", "member_id"]).any(), "a member twice in one vote"
    assert set(v.loc[v["member_id"].isna(), "member_match"]) <= UNRESOLVED
    assert v.loc[v["member_id"].notna(), "member_match"].isin(UNRESOLVED).sum() == 0


@pytest.mark.parametrize("age", AGES)
def test_member_links(kdata, age):
    v = _votes(kdata, age)
    share = v["member_id"].notna().mean()
    un = v[v["member_id"].isna()]
    warnings.warn(f"{age}th minutes names: {len(v):,} rows, member_id for {share:.5%}, "
                  f"unresolved {dict(Counter(un['name_raw']))}", UserWarning)
    assert share >= 0.995
    # only the same-name pairs of SAME_NAME stay unresolved
    assert set(un["name_raw"]) <= set(mv.SAME_NAME.get(age, {}))
    if kdata.has(f"members_{age}.parquet"):
        mem = kdata.members(age)
        assert set(v["member_id"].dropna()) <= set(mem["mona_cd"])


@pytest.mark.parametrize("age", AGES)
def test_bill_links(kdata, age):
    e = _events(kdata, age)
    linked = e["bill_id"].notna()
    warnings.warn(f"{age}th minutes votes: {len(e):,}, bill_id for {linked.mean():.2%} "
                  f"({e['bill_link'].value_counts().to_dict()})", UserWarning)
    assert linked.mean() >= 0.99
    assert set(e.loc[~linked, "vote_type"]) <= {"other"}
    assert set(e.loc[linked, "vote_type"]) <= {"original", "amendment", "reversal", "revote"}
    if kdata.has(f"master_bills_{age}.parquet"):
        m = kdata.master(age, ["bill_id"])
        assert set(e.loc[linked, "bill_id"]) <= set(m["bill_id"])


@pytest.mark.parametrize("age", AGES)
def test_chair_counts(kdata, age):
    e = _events(kdata, age)
    has = e["chair_present"].notna()
    differ = e["chair_counts_differ"].fillna(False).astype(bool)
    explained = differ & e["correction_note_matches_names"].fillna(False).astype(bool)
    warnings.warn(
        f"{age}th chair counts: found for {int(has.sum()):,} of {len(e):,} votes, equal to the "
        f"names in {int((has & ~differ).sum()):,} ({(has & ~differ).sum() / has.sum():.2%}), "
        f"differ in {int(differ.sum()):,}, of which {int(explained.sum()):,} match the "
        f"appendix correction note", UserWarning)
    assert has.mean() >= 0.99
    assert ((has & ~differ) | explained).sum() / has.sum() >= 0.99
    # a correction note is always flagged
    assert e.loc[e["correction_note"], "appendix_note"].str.contains("실[제체]").all()


@pytest.mark.parametrize("age", AGES)
def test_results_agree_with_master(kdata, age):
    e = _events(kdata, age)
    m = kdata.master(age, ["bill_id", "rgs_conf_rslt"])
    x = e[(e["vote_type"] == "original") & e["chair_result"].notna()].merge(
        m, on="bill_id", suffixes=("_ev", ""))
    ok = (((x["chair_result"] == "가결") & x["rgs_conf_rslt"].isin(PASSED))
          | ((x["chair_result"] == "부결") & (x["rgs_conf_rslt"] == "부결")))
    assert ok.all(), x.loc[~ok, ["vote_event_id", "chair_result", "rgs_conf_rslt"]].to_string()


@pytest.mark.parametrize("age", AGES)
def test_same_as_kr_hearings_v10(kdata, age):
    """Names per vote equal the v10 parse wherever both have the meeting's votes.

    v10 reads the same minutes (viewer XML, or HWP for the 18th). Reported, and
    asserted only as a floor, because v10 is still being revised.
    """
    for f in ["rollcall.parquet"]:
        if not (V10_DIR / f).exists():
            pytest.skip(f"{V10_DIR / f} not found")
    r = pd.read_parquet(V10_DIR / "rollcall.parquet",
                        columns=["conf_num", "vote_seq", "vote_group", "name", "term"])
    r = r[r["term"] == age]
    e, v = _events(kdata, age), _votes(kdata, age)
    n_p = e.groupby("confer_num").size()
    n_v = r.drop_duplicates(["conf_num", "vote_seq"]).groupby("conf_num").size()
    same = [c for c in n_p.index if n_v.get(c) == n_p[c]]
    rg = {k: d for k, d in r[r["conf_num"].isin(same)].groupby("conf_num")}
    vg = {k: d for k, d in v[v["confer_num"].isin(same)].groupby("confer_num")}
    identical, differ = 0, []
    for c in same:
        seqs = sorted(rg[c]["vote_seq"].unique())
        for (seq, ev), vs in zip(e[e["confer_num"] == c].sort_values("event_seq")[
                ["event_seq", "vote_event_id"]].itertuples(index=False), seqs):
            a = vg[c][vg[c]["event_seq"] == seq]
            b = rg[c][rg[c]["vote_seq"] == vs]
            eq = all(Counter(a.loc[a["vote"] == g, "name_raw"])
                     == Counter(unicodedata.normalize("NFKC", n) for n in b.loc[b["vote_group"] == g, "name"])
                     for g in ["찬성", "반대", "기권"])
            identical += eq
            if not eq:
                differ.append(ev)
    total = identical + len(differ)
    warnings.warn(f"{age}th vs kr-hearings-data v10: {len(same)} of {len(n_p)} meetings with the "
                  f"same number of votes, {identical:,} of {total:,} votes with identical names, "
                  f"differ {differ[:12]}", UserWarning)
    assert total == 0 or identical / total >= 0.99


# ── build ───────────────────────────────────────────────────────────

def _rc_minutes(kdata):
    if "vote_event_id" not in kdata.schema("roll_calls_all.parquet").names:
        pytest.skip("roll_calls_all was built without the minutes votes")
    rc = kdata.parquet("roll_calls_all.parquet",
                       ["term", "vote_event_id", "member_id", "member_match", "vote", "source",
                        "bill_id", "party", "party_api"])
    m = rc[rc["source"] == "minutes_pdf"]
    if m.empty:
        pytest.skip("roll_calls_all was built without the minutes votes")
    return rc, m


def test_roll_calls_minutes_rows(kdata):
    rc, m = _rc_minutes(kdata)
    assert set(m["term"]) <= set(AGES)
    assert set(rc.loc[rc["term"].isin(AGES), "source"]) == {"minutes_pdf"}
    assert m["party_api"].isna().all()
    assert set(m["vote"]) <= {"찬성", "반대", "기권"}
    known = rc[rc["member_id"].notna()]
    assert not known.duplicated(["term", "vote_event_id", "member_id"]).any()
    assert set(m.loc[m["member_id"].isna(), "member_match"]) <= UNRESOLVED
    for age in AGES:
        p = kdata.raw / f"minutes_votes_{age}.parquet"
        if p.exists():
            raw = pd.read_parquet(p, columns=["vote_event_id"])
            assert (m["term"] == age).sum() == len(raw), f"{age}th rows differ from {p.name}"


def test_roll_calls_minutes_party_at_election(kdata):
    _, m = _rc_minutes(kdata)
    for age in AGES:
        if not kdata.has(f"members_{age}.parquet"):
            continue
        mem = kdata.members(age)[["mona_cd", "party"]].rename(columns={"mona_cd": "member_id"})
        j = m[m["term"] == age].drop_duplicates("member_id").merge(
            mem, on="member_id", suffixes=("", "_elected"))
        assert (j["party"] == j["party_elected"]).all()


def _ve(kdata):
    if "source" not in kdata.schema("vote_events.parquet").names:
        pytest.skip("vote_events was built without the minutes votes")
    return kdata.parquet("vote_events.parquet")


def test_vote_events_minutes(kdata):
    ve = _ve(kdata)
    assert set(ve.loc[ve["age"].isin(AGES), "source"]) <= {"minutes_pdf"}
    assert set(ve.loc[~ve["age"].isin(AGES), "source"]) <= {"api"}
    mv_ = ve[ve["source"] == "minutes_pdf"]
    if mv_.empty:
        pytest.skip("vote_events was built without the minutes votes")
    assert mv_["vote_event_id"].is_unique
    assert mv_["member_tcnt"].isna().all()
    assert (mv_["vote_tcnt"] == mv_["yes"] + mv_["no"] + mv_["abstain"]).all()
    api = ve[ve["source"] == "api"]
    assert (api["vote_event_id"] == api["vote_bill_id"]).all()
    _rc_minutes(kdata)
    rc = kdata.parquet("roll_calls_all.parquet", ["vote_event_id", "vote", "source"])
    c = rc[rc["source"] == "minutes_pdf"].groupby("vote_event_id")["vote"].value_counts().unstack(
        fill_value=0).reindex(mv_["vote_event_id"], fill_value=0)
    assert (c["찬성"].values == mv_["yes"].values).all()
    assert (c["반대"].values == mv_["no"].values).all()
    assert (c["기권"].values == mv_["abstain"].values).all()


@pytest.mark.parametrize("age", AGES)
def test_master_vote_columns_from_minutes(kdata, age):
    m = kdata.master(age, ["bill_id", "vote_bill_id", "vote_result_cd", "vote_total", "vote_yes",
                           "vote_no", "vote_abstain", "vote_member_total"])
    ve = _ve(kdata)
    ve = ve[(ve["age"] == age) & (ve["source"] == "minutes_pdf")]
    if ve.empty:
        pytest.skip(f"no {age}th minutes votes in vote_events")
    filled = m[m["vote_bill_id"].notna()]
    assert len(filled) == ve["master_bill_id"].nunique()
    assert m["vote_member_total"].isna().all()
    j = filled.merge(ve, left_on="vote_bill_id", right_on="vote_event_id", validate="one_to_one")
    assert (j["bill_id"] == j["master_bill_id"]).all()
    assert (j["vote_yes"] == j["yes"]).all() and (j["vote_no"] == j["no"]).all()
    assert (j["vote_abstain"] == j["abstain"]).all() and (j["vote_total"] == j["vote_tcnt"]).all()
    assert (j["vote_result_cd"].fillna("") == j["result"].fillna("")).all()


def test_experimental_file_holds_the_16th_only(kdata):
    x = kdata.parquet("roll_calls_16_19_experimental.parquet", ["term"])
    assert set(x["term"]) == {16}
