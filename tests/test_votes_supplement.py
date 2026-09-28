"""Tests for the LIKMS supplement of the 22nd roll calls.

collect_votes_likms.py reads the LIKMS vote page of every 22nd vote whose
API rows fall short of MEMBER_TCNT and writes the missing members' rows to
data/raw/roll_calls_22_supplement.parquet. consolidate_votes.py merges them
into roll_calls_all with source 'likms' or 'likms_absent'.

The unit tests need no data. The data tests read the raw directory
(KNA_RAW_DIR, default data/raw) and the data directory under test (KBL_DATA),
and skip when a file is missing.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from collect_votes_likms import (SOURCE_ABSENT, SOURCE_LISTED, SupplementError,
                                 leftover_names, match_names, parse_vote_page,
                                 seat_starts)
from consolidate_votes import merge_supplement

SOURCES = {"api", SOURCE_LISTED, SOURCE_ABSENT}
PAIR = {"8BF5855P", "H7X3372O"}  # the two 박지원 of the 22nd
# 22nd votes whose member-level counts differ from the tally on the LIKMS page
# itself: the page's header gives the tally, its lists the member-level votes.
KNOWN_22_TALLY_DIFF = {"2215128"}


# ── unit tests ──────────────────────────────────────────────────────

def _entry(name, slug=None):
    if slug:
        href = f'https://www.assembly.go.kr/members/22nd/{slug}" target="_blank" title="새창열림" class="0'
        img = f'<img src="x.jpg" data-src="x.jpg" alt="국회의원:{name}">'
    else:
        href = 'javascript:void(0);" target="_self" class="1 cur-d'
        img = f'<img src="" data-src="/bill/static/img/bi/no-img_mem_m.png" alt="국회의원:{name}">'
    return f'<li><a href="{href}">\n <div>\n {img}\n </div>\n <p>{name}</p>\n </a></li>'


PAGE = (
    '<form id="voteForm"><input type="hidden" name="billId" value="PRC_X"></form>'
    '<h5 class="msal01"><a href="javascript:;" title="확장됨">찬성</a></h5><ul>'
    + _entry("강경숙", "KANGKYUNGSOOK") + _entry("박지원")
    + '</ul><h5 class="msal02"><a href="javascript:;">반대</a></h5><ul>'
    + _entry("한동훈")
    + '</ul><h5 class="msal03"><a href="javascript:;">기권</a></h5><ul></ul>'
    '<script>const voteInfo = {"voteUnqId":7,"billId":"PRC_X","billNo":"2200001",'
    '"procDt":"2026-09-17","enrCnt":4,"voteCnt":3,"apprCnt":2,"opstCnt":1,'
    '"abstCnt":0,"nattCnt":1};</script>'
)


def test_parse_vote_page():
    info, lists = parse_vote_page(PAGE)
    assert info["billId"] == "PRC_X" and info["apprCnt"] == 2 and info["nattCnt"] == 1
    assert lists["찬성"] == [["강경숙", "KANGKYUNGSOOK"], ["박지원", None]]
    assert lists["반대"] == [["한동훈", None]]
    assert lists["기권"] == []


def test_parse_vote_page_rejects_other_pages():
    with pytest.raises(SupplementError):
        parse_vote_page("<html>오류</html>")


ROSTER = pd.DataFrame({
    "mona_cd": ["8BF5855P", "H7X3372O", "T2T8225E", "5DC8083A", "MRS4949T"],
    "member_name": ["박지원", "박지원", "강경숙", "한동훈", "이소희"],
})


def _api(rows):
    return pd.DataFrame(rows, columns=["member_id", "member_name", "vote"])


def test_leftover_names_are_the_page_minus_the_api():
    _, lists = parse_vote_page(PAGE)
    api = _api([("T2T8225E", "강경숙", "찬성"), ("8BF5855P", "박지원", "불참")])
    left = leftover_names(api, lists)
    assert left == {"찬성": Counter({"박지원": 1}), "반대": Counter({"한동훈": 1}),
                    "기권": Counter()}


def test_leftover_names_fail_when_an_api_vote_is_not_on_the_page():
    _, lists = parse_vote_page(PAGE)
    api = _api([("T2T8225E", "강경숙", "반대")])
    with pytest.raises(SupplementError, match="not on the page"):
        leftover_names(api, lists)


def test_same_name_pair_resolves_to_the_member_without_an_api_row():
    left = {"찬성": Counter({"박지원": 1}), "반대": Counter({"한동훈": 1}), "기권": Counter()}
    got = match_names(left, ROSTER, api_ids={"8BF5855P", "T2T8225E"})
    assert sorted(got) == [("5DC8083A", "반대"), ("H7X3372O", "찬성")]


@pytest.mark.parametrize("api_ids", [set(), {"8BF5855P", "H7X3372O"}])
def test_same_name_pair_fails_when_ambiguous_or_unmatched(api_ids):
    left = {"찬성": Counter({"박지원": 1}), "반대": Counter(), "기권": Counter()}
    with pytest.raises(SupplementError, match="same-name pair"):
        match_names(left, ROSTER, api_ids=api_ids)


def test_unknown_or_repeated_names_fail():
    unknown = {"찬성": Counter({"홍길동": 1}), "반대": Counter(), "기권": Counter()}
    with pytest.raises(SupplementError, match="no roster member"):
        match_names(unknown, ROSTER, api_ids=set())
    twice = {"찬성": Counter({"한동훈": 1}), "반대": Counter({"한동훈": 1}), "기권": Counter()}
    with pytest.raises(SupplementError, match="more than once"):
        match_names(twice, ROSTER, api_ids=set())


def _votes(levels):
    return pd.DataFrame({"vote_time": [t for t, _ in levels],
                         "rows_short": [n for _, n in levels]})


def test_seat_starts_follow_the_steps_and_the_first_list_entry():
    votes = _votes([("20260101 100000", 0), ("20260115 100000", 1), ("20260201 100000", 1),
                    ("20260611 100000", 3), ("20260612 100000", 3)])
    listed = pd.DataFrame({"member_id": ["A", "B", "C", "B"],
                           "vote_time": ["20260201 100000", "20260611 100000",
                                         "20260612 100000", "20260612 100000"]})
    got = seat_starts(votes, listed, ["A", "B", "C", "D"])
    assert got == {"A": "20260115 100000", "B": "20260611 100000", "C": "20260611 100000"}


def test_seat_starts_fail_when_a_step_cannot_be_assigned():
    votes = _votes([("20260101 100000", 0), ("20260115 100000", 1), ("20260201 100000", 1)])
    nobody = pd.DataFrame({"member_id": [], "vote_time": []})
    with pytest.raises(SupplementError, match="cannot be chosen"):
        seat_starts(votes, nobody, ["A", "B"])
    falling = _votes([("20260101 100000", 1), ("20260115 100000", 0)])
    with pytest.raises(SupplementError, match="fall"):
        seat_starts(falling, nobody, ["A"])


def test_merge_supplement_api_wins_and_keys_are_unique():
    df = pd.DataFrame({
        "term": [22, 22, 22, 22],
        "bill_id": ["B1", "B1", "B1", "B1"],
        "member_id": ["M1", "M2", "M1", "M3"],
        "vote": ["찬성", "불참", "반대", "기권"],
        "source": ["api", "api", SOURCE_LISTED, SOURCE_ABSENT],
    })
    out = merge_supplement(df)
    assert not out.duplicated(["term", "bill_id", "member_id"]).any()
    assert out.set_index("member_id").loc["M1", ["vote", "source"]].tolist() == ["찬성", "api"]
    assert sorted(out["member_id"]) == ["M1", "M2", "M3"]
    assert set(out["source"]) <= SOURCES


# ── data tests ──────────────────────────────────────────────────────

def _raw(kdata, name) -> pd.DataFrame:
    p = kdata.raw / name
    if not p.exists():
        pytest.skip(f"{name} not in {kdata.raw}")
    return pd.read_parquet(p)


def _tallies(kdata) -> pd.DataFrame:
    t = _raw(kdata, "ncocpgfiaoituanbr_22.parquet")
    for c in ["MEMBER_TCNT", "YES_TCNT", "NO_TCNT", "BLANK_TCNT"]:
        t[c] = pd.to_numeric(t[c])
    return t.rename(columns={"BILL_ID": "bill_id", "BILL_NO": "bill_no"})


def test_supplement_schema_and_values(kdata):
    supp = _raw(kdata, "roll_calls_22_supplement.parquet")
    api_cols = list(pd.read_parquet(kdata.raw / "roll_calls_22.parquet").columns)
    assert list(supp.columns) == api_cols + ["source"]
    assert set(supp["source"]) <= {SOURCE_LISTED, SOURCE_ABSENT}
    assert set(supp.loc[supp["source"] == SOURCE_LISTED, "vote"]) <= {"찬성", "반대", "기권"}
    assert set(supp.loc[supp["source"] == SOURCE_ABSENT, "vote"]) == {"불참"}
    assert supp["member_id"].notna().all() and supp["bill_id"].notna().all()
    assert (supp["age"] == 22).all()


def test_supplement_adds_only_rows_the_api_lacks(kdata):
    supp = _raw(kdata, "roll_calls_22_supplement.parquet")
    api = _raw(kdata, "roll_calls_22.parquet")[["bill_id", "member_id"]]
    key = ["bill_id", "member_id"]
    assert not supp.duplicated(key).any()
    overlap = supp[key].merge(api, on=key)
    assert overlap.empty, f"{len(overlap)} supplement rows duplicate API rows"
    # Only members the API omits for the whole term, never the other 박지원
    assert not set(supp["member_id"]) & set(api["member_id"])
    assert "H7X3372O" in set(supp["member_id"]) and "8BF5855P" not in set(supp["member_id"])
    roster = kdata.parquet("members_22.parquet") if kdata.has("members_22.parquet") else \
        pd.read_parquet(kdata.raw.parent / "processed" / "members_22.parquet")
    assert set(supp["member_id"]) <= set(roster["mona_cd"])


def test_supplement_fills_every_vote_to_member_tcnt(kdata):
    supp = _raw(kdata, "roll_calls_22_supplement.parquet")
    api = _raw(kdata, "roll_calls_22.parquet")
    rows = pd.concat([api[["bill_id"]], supp[["bill_id"]]]).groupby("bill_id").size()
    t = _tallies(kdata).set_index("bill_id")
    diff = (t["MEMBER_TCNT"] - rows.reindex(t.index, fill_value=0))
    assert (diff == 0).all(), f"{int((diff != 0).sum())} votes differ from MEMBER_TCNT"


def test_page_of_2215128_differs_from_its_own_header(kdata):
    p = kdata.raw / "roll_calls_22_supplement_check.csv"
    if not p.exists():
        pytest.skip(f"{p.name} not in {kdata.raw}")
    c = pd.read_csv(p, dtype={"bill_no": str}).set_index("bill_no")
    r = c.loc["2215128"]
    assert bool(r["page_header_matches_tally"]) and not bool(r["lists_match_tally"])
    off = set(c.index[~c["lists_match_tally"].astype(bool)])
    assert off == KNOWN_22_TALLY_DIFF


def _rc22(kdata) -> pd.DataFrame:
    rc = kdata.parquet("roll_calls_all.parquet",
                       ["term", "bill_id", "member_id", "member_name", "vote", "source"])
    rc = rc[rc["term"] == 22]
    if not (rc["source"] != "api").any():
        pytest.skip("roll_calls_all was built without the 22nd supplement")
    return rc


def test_roll_calls_all_sources(kdata):
    # The 17th-19th rows come from the minutes (tests/test_minutes_votes.py)
    rc = kdata.parquet("roll_calls_all.parquet", ["term", "source"])
    rc = rc[rc["source"] != "minutes_pdf"]
    assert set(rc["source"]) <= SOURCES
    assert set(rc.loc[rc["source"] != "api", "term"]) <= {22}


def test_roll_calls_22_match_tallies_with_the_supplement(kdata):
    rc = _rc22(kdata)
    t = _tallies(kdata).set_index("bill_id")
    g = rc.groupby("bill_id")["vote"]
    got = pd.DataFrame({"rows": g.size(), "yes": g.apply(lambda s: (s == "찬성").sum()),
                        "no": g.apply(lambda s: (s == "반대").sum()),
                        "abstain": g.apply(lambda s: (s == "기권").sum())}).reindex(t.index)
    assert (got["rows"] == t["MEMBER_TCNT"]).all(), "22nd votes with rows != MEMBER_TCNT"
    off = ((got["yes"] != t["YES_TCNT"]) | (got["no"] != t["NO_TCNT"])
           | (got["abstain"] != t["BLANK_TCNT"]))
    assert set(t.loc[off, "bill_no"]) == KNOWN_22_TALLY_DIFF


def test_same_name_pair_22_keeps_both(kdata):
    rc = _rc22(kdata)
    both = rc[rc["member_id"].isin(PAIR)]
    assert set(both["member_id"]) == PAIR
    assert (both.groupby("bill_id")["member_id"].nunique() == 2).any()
    assert (both.loc[both["member_id"] == "8BF5855P", "source"] == "api").all()
