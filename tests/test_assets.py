"""Checks of the asset disclosure panel and of build_assets.py.

1. The panel in KBL_DATA: schema, keys, identities between the totals, roster
   membership, and the wealth_year 2025 rows from the March 2026 국회공보.
2. Provenance: the 2015-2024 rows equal a rebuild from the OpenWatch CSVs in
   KNA_ASSETS_DIR (skipped when that directory is not available).
3. The 국회공보 parser and the name matching, on small synthetic tables.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import build_assets as B

NAME = "assets_wealth_panel.parquet"

COLUMNS = {
    "mona_cd": "object", "wealth_year": "int64", "member_name": "object",
    "total_assets": "float64", "total_debt": "float64", "net_worth": "float64",
    "total_building": "float64", "total_land": "float64", "total_deposits": "float64",
    "total_stocks": "float64", "total_realestate": "float64",
    "n_properties_all": "int64", "n_properties_self": "int64", "n_properties_owned": "int64",
    "n_apt_total": "int64", "n_apt_owned": "int64", "n_rental_given": "int64",
    "has_seoul_re": "int64", "has_gangnam_re": "int64", "n_seoul_bldg": "int64",
    "re_self": "float64", "re_spouse": "float64", "n_stock_items": "int64",
    "political_fund": "float64", "n_family_relations": "int64", "n_land_parcels": "int64",
    "re_share": "float64", "log_total_realestate": "float64", "log_total_assets": "float64",
    "log_net_worth": "float64", "log_total_building": "float64", "log_total_land": "float64",
    "log_total_deposits": "float64", "log_total_stocks": "float64",
    "total_realestate_q": "object", "total_assets_q": "object", "net_worth_q": "object",
    "assembly": "int64",
}

# Member-years per wealth year. 2015-2024 are the 0.6.0 rows, 2025 is the
# March 2026 disclosure.
ROWS = {2015: 290, 2016: 299, 2017: 286, 2018: 289, 2019: 290, 2020: 298,
        2021: 289, 2022: 297, 2023: 291, 2024: 299, 2025: 287}


@pytest.fixture(scope="module")
def panel(kdata):
    return kdata.parquet(NAME)


# ---------------------------------------------------------------------------
# 1. The panel
# ---------------------------------------------------------------------------

def test_schema(panel):
    assert list(panel.columns) == list(COLUMNS)
    got = {c: str(t) for c, t in panel.dtypes.items()}
    assert got == COLUMNS


def test_keys_and_order(panel):
    assert not panel.duplicated(["mona_cd", "wealth_year"]).any()
    assert panel["mona_cd"].str.fullmatch(r"[0-9A-Z]{8}").all()
    key = list(zip(panel["mona_cd"], panel["wealth_year"]))
    assert key == sorted(key), "rows are not sorted by mona_cd, wealth_year"


def test_rows_per_year_and_assembly(panel):
    assert panel.groupby("wealth_year").size().to_dict() == ROWS
    assert (panel["assembly"] == panel["wealth_year"].map(B.assembly_of)).all()


def test_total_identities(panel):
    p = panel
    assert (p["net_worth"] == p["total_assets"] - p["total_debt"]).all()
    assert (p["total_realestate"] == p["total_building"] + p["total_land"]).all()
    parts = p["total_building"] + p["total_land"] + p["total_deposits"] + p["total_stocks"]
    assert (p["total_assets"] >= parts).all()
    assert (p["re_self"] + p["re_spouse"] <= p["total_realestate"]).all()
    pos = p["total_assets"] > 0
    assert np.allclose(p.loc[pos, "re_share"], p.loc[pos, "total_realestate"] / p.loc[pos, "total_assets"],
                       rtol=1e-12, atol=0)
    assert p.loc[~pos, "re_share"].isna().all()
    for col in ["total_realestate", "total_assets", "net_worth", "total_building",
                "total_land", "total_deposits", "total_stocks"]:
        x, lg = p[col], p[f"log_{col}"]
        assert np.allclose(lg[x > 0], np.log(x[x > 0]), rtol=1e-12, atol=0), col
        assert lg[x <= 0].isna().all(), col


def test_count_identities(panel):
    p = panel
    assert (p["n_properties_owned"] + p["n_rental_given"] == p["n_properties_all"]).all()
    assert (p["n_apt_owned"] <= p["n_apt_total"]).all()
    assert (p["n_apt_total"] <= p["n_properties_all"]).all()
    assert (p["n_properties_self"] <= p["n_properties_all"]).all()
    assert (p["n_seoul_bldg"] <= p["n_properties_all"]).all()
    assert (p["has_gangnam_re"] <= p["has_seoul_re"]).all()
    assert p[["has_seoul_re", "has_gangnam_re"]].isin([0, 1]).all().all()
    for c in B.QUARTILE_COLS:
        assert p[f"{c}_q"].isin(["Q1", "Q2", "Q3", "Q4"]).all()


def test_quartile_cut_points_come_from_2015_2024(panel):
    base = panel[panel["wealth_year"] <= 2024]
    for c in B.QUARTILE_COLS:
        want = pd.qcut(base[c], 4, labels=["Q1", "Q2", "Q3", "Q4"]).astype(str)
        assert (base[f"{c}_q"] == want).all(), c


@pytest.mark.parametrize("assembly", [19, 20, 21, 22])
def test_members_in_roster(kdata, panel, assembly):
    roster = kdata.members(assembly)
    rows = panel[panel["assembly"] == assembly]
    missing = rows[~rows["mona_cd"].isin(roster["mona_cd"])]
    assert missing.empty, missing[["mona_cd", "member_name", "wealth_year"]].to_dict("records")


def test_2025_rows(kdata, panel):
    rows = panel[panel["wealth_year"] == 2025]
    roster = kdata.members(22).set_index("mona_cd")["member_name"]
    assert rows["mona_cd"].isin(roster.index).all()
    assert (rows["member_name"] == rows["mona_cd"].map(roster)).all()
    # Same-name members: only 8BF5855P was in office for the March 2026 disclosure
    assert set(rows.loc[rows["member_name"] == "박지원", "mona_cd"]) == {"8BF5855P"}
    # Holdings are in thousands of won. A member's median net worth is in the
    # billions of won, so a median outside 0.1 to 10 billion would signal a unit slip.
    assert 1e5 < rows["net_worth"].median() < 1e7


def test_2025_follows_2024(panel):
    """Every member in both years: the change is recorded, not a unit or key slip."""
    w = panel.pivot(index="mona_cd", columns="wealth_year", values="net_worth")[[2024, 2025]].dropna()
    assert len(w) == 283
    both = (w[2024] > 0) & (w[2025] > 0)
    ratio = np.log(w.loc[both, 2025] / w.loc[both, 2024])
    assert abs(ratio.median()) < 0.3
    assert (ratio.abs() > 1).sum() <= 10


# ---------------------------------------------------------------------------
# 2. Provenance
# ---------------------------------------------------------------------------

def test_rebuild_2015_2024_from_openwatch(panel):
    if not (B.SOURCE_DIR / "openwatch").is_dir():
        pytest.skip(f"OpenWatch CSVs not in {B.SOURCE_DIR} (set KNA_ASSETS_DIR)")
    items = B.load_openwatch()
    rebuilt = B.csv_floats(B.finish(B.add_quartiles(B.aggregate(items), B.OPENWATCH_YEAR.values())))
    shipped = panel[panel["wealth_year"] <= 2024].reset_index(drop=True)
    pd.testing.assert_frame_equal(shipped, rebuilt, check_exact=True)


# ---------------------------------------------------------------------------
# 3. Parser and matching, synthetic input
# ---------------------------------------------------------------------------

HEADER = ["소속", "국회", None, "직위", "국회의원", None, "성명", "홍길동"]


def _sub(cat, prev, inc, dec, cur):
    return [f"▶ {cat}(소계)", None, None, prev, inc, dec, cur, ""]


def _total(prev, inc, dec, cur):
    return ["총 계", None, None, prev, inc, dec, cur, "증감액"]


def _pages(*pages):
    """(page, first_on_page, last_on_page, cells) rows from lists of rows per page."""
    out = []
    for pno, rows in enumerate(pages, 1):
        for i, r in enumerate(rows):
            out.append((pno, i == 0, i == len(rows) - 1, r))
    return out


def test_parser_repeated_row_is_one_item_when_the_subtotal_says_so():
    part1 = ["배우자", "상장주식", "가 1주,\n나", "0", "300", "0", "300", ""]
    part2 = ["배우자", "상장주식", "2주", "0", "300", "0", "300", "매수"]
    rows = _pages([HEADER, _sub("증권", "0", "300", "0", "300"), part1],
                  [part2, _total("0", "300", "0", "300")])
    P, I, S, log = B.parse_gongbo(rows)
    assert len(I) == 1 and log["repeated_merged"] == 1
    assert I.loc[0, "detail"] == "가 1주,나2주"
    assert I.loc[0, "reason"] == "매수"
    assert I.loc[0, "current_value"] == 300


def test_parser_identical_items_are_kept_when_the_subtotal_counts_both():
    item = ["배우자", "오피스텔", "시흥시 정왕동", "0", "140", "0", "140", "혼인으로 추가"]
    rows = _pages([HEADER, _sub("건물", "0", "280", "0", "280"), item],
                  [list(item), _total("0", "280", "0", "280")])
    P, I, S, log = B.parse_gongbo(rows)
    assert len(I) == 2 and log["repeated_kept"] == 1


def test_parser_blank_part_merged_cells_and_six_cell_total():
    blank = ["배우자", "상장주식", "가 1주,", "", "", "", "", ""]
    valued = ["배우자", "상장주식", "나 2주", "0", "300", "0", "300", "매수"]
    merged_rel = [None, "비상장주식", "다 3주", "0", "0", "0", "0", None]
    debt = ["본인", "금융채무", "은행 50", "0", "50", "0", "50", "대출"]
    rows = _pages([HEADER, _sub("증권", "0", "300", "0", "300"), blank],
                  [valued, merged_rel, _sub("채무", "0", "50", "0", "50"), debt],
                  [["총 계", "0", "350", "0", "250", "증감액"]])
    P, I, S, log = B.parse_gongbo(rows)
    assert log["blank_continuations"] == 1
    assert I["asset_kind"].tolist() == ["상장주식", "비상장주식", "금융채무"]
    assert I["relation"].tolist() == ["배우자", "배우자", "본인"]
    assert I.loc[0, "detail"] == "가 1주,나 2주" and I.loc[0, "current_value"] == 300
    assert P.loc[0, "tot_current_value"] == 250


def test_parser_stops_when_items_do_not_add_up():
    item = ["본인", "아파트", "서울특별시", "0", "100", "0", "100", ""]
    rows = _pages([HEADER, _sub("건물", "0", "100", "0", "999"), item, _total("0", "100", "0", "999")])
    with pytest.raises(ValueError, match="subtotals"):
        B.parse_gongbo(rows)


def test_amount_cell_with_transaction_price():
    assert B._num("10,370\n(3,000)") == (10370, 3000)
    assert B._num("-") == (None, None)
    with pytest.raises(ValueError):
        B._num("10,370\n3,000")


def test_same_name_members_need_an_explicit_rule():
    members = pd.DataFrame({"member_name": ["박지원", "박지원", "우원식"],
                            "mona_cd": ["H7X3372O", "8BF5855P", "XBT9550Q"]})
    prior = pd.DataFrame({"mona_cd": ["8BF5855P"], "net_worth": [100.0]})
    P = pd.DataFrame({"name": ["박지원", "우원식"], "position": ["국회의원", "국회의장"],
                      "tot_prev_value": [100, 5]})
    got = B.resolve_names(P, 2025, members, prior)
    assert got.tolist() == ["8BF5855P", "XBT9550Q"]
    with pytest.raises(SystemExit, match="no SAME_NAME rule"):
        B.resolve_names(P, 2031, members, prior)
    with pytest.raises(SystemExit, match="differs from the disclosed"):
        B.resolve_names(P.assign(tot_prev_value=[999, 5]), 2025, members, prior)
    with pytest.raises(SystemExit, match="not in the roster"):
        B.resolve_names(P.assign(name=["홍길동", "우원식"]), 2025, members, prior)
