"""Bill texts, 17th-22nd, and alternative absorption links.

Texts. bill_texts_linked.parquet keeps every row of the LIKMS scrape (20th-22nd
member law bills) with its text and scrape_status, and adds the official
BPMBILLSUMMARY text of the other law bills (source column). It holds one row
per bill, never an empty string as a text, and covers each assembly's law
bills above the floors in TEXT_FLOOR.

Alternatives. Every link of alternative_absorption.parquet joins to a master
bill of the same assembly, and the absorbed bill is 대안반영폐기 unless its
alternative expired at the end of the term or is still pending.

    KBL_DATA=$PWD/data/_build python3 -m pytest -q tests/test_texts_alternatives.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from conftest import AGES, REPO

TEXTS = "bill_texts_linked.parquet"
TEXT_COLS = ["BILL_ID", "propose_reason", "scrape_status", "age", "bill_no", "source"]
TEXT_SOURCES = {"likms_scrape", "BPMBILLSUMMARY"}

# Floor for the share of 법률안 with a text. The build of 2026-09-28 reached
# 99.96, 97.64, 100, 99.87, 99.73 and 99.74 percent. Every law bill still
# without a text was answered by BPMBILLSUMMARY with an empty SUMMARY
# (reports/bill_texts_missing.csv), so the floors sit just under those shares
# and fail on a lost raw file or a partial collection, which drops an assembly
# by thousands of bills. The 18th is lower because the API has no text for
# 328 of its 1,693 government law bills. The 22nd leaves room for about 350
# law bills newer than the last collection, some two weeks of new bills.
TEXT_FLOOR = {17: 0.995, 18: 0.97, 19: 0.995, 20: 0.995, 21: 0.995, 22: 0.98}
# Floor per proposer kind (의원, 정부, 위원장), with the one known gap
KIND_FLOOR = 0.95
KIND_FLOOR_EXCEPTIONS = {(18, "정부"): 0.78}

# Floor for the share of 대안반영폐기 bills linked to an alternative. The
# 17th is low because TVBPMBILL11, and the LIKMS 대안정보 tab that shows the
# same data, return no absorbed bills for 282 of the 17th alternatives with a
# numeric BILL_ID (CODEBOOK.md section 4). The 18th-22nd are at 99.3% or more.
ALT_FLOOR = {17: 0.57, 18: 0.99, 19: 0.99, 20: 0.99, 21: 0.99, 22: 0.99}


def _texts(kdata) -> pd.DataFrame:
    t = kdata.parquet(TEXTS)
    missing = [c for c in TEXT_COLS if c not in t.columns]
    assert not missing, f"{TEXTS} lacks {missing}: a file built before the 17th-22nd texts"
    return t


def _laws(kdata, age: int) -> pd.DataFrame:
    m = kdata.master(age, ["bill_id", "bill_no", "bill_kind", "ppsr_kind"])
    return m[m["bill_kind"] == "법률안"]


# ── texts ───────────────────────────────────────────────────────────

def test_texts_columns(kdata):
    names = kdata.schema(TEXTS).names
    # The first three are the columns of the scrape-only file, in its order
    assert names == TEXT_COLS, names


def test_texts_one_row_per_bill(kdata):
    t = _texts(kdata)
    dup = t[t["BILL_ID"].duplicated(keep=False)]
    assert dup.empty, f"{len(dup)} rows repeat a BILL_ID, e.g. {dup['BILL_ID'].head(3).tolist()}"
    keyed = t.dropna(subset=["bill_no"])
    dup = keyed[keyed.duplicated(["age", "bill_no"], keep=False)]
    assert dup.empty, f"{len(dup)} rows repeat (age, bill_no), e.g. {dup['bill_no'].head(3).tolist()}"


def test_texts_no_empty_strings(kdata):
    t = _texts(kdata)
    txt = t["propose_reason"].dropna()
    blank = txt[txt.str.strip() == ""]
    assert blank.empty, f"{len(blank)} texts are empty or whitespace; store null instead"


def test_texts_sources(kdata):
    t = _texts(kdata)
    assert set(t["source"].unique()) <= TEXT_SOURCES, set(t["source"].unique())
    assert t["source"].notna().all()
    scraped = t["scrape_status"].notna()
    # A row outside the scrape exists only because the API had a text for it
    added = t[~scraped]
    assert (added["source"] == "BPMBILLSUMMARY").all()
    assert added["propose_reason"].notna().all()
    # A scraped text is never replaced
    ok = t[t["scrape_status"] == "ok"]
    assert (ok["source"] == "likms_scrape").all() and ok["propose_reason"].notna().all()
    # likms_scrape without a text only where the scrape failed
    lk = t[t["source"] == "likms_scrape"]
    assert (lk["propose_reason"].notna() | (lk["scrape_status"] != "ok")).all()


@pytest.mark.parametrize("age", AGES)
def test_texts_join_master(kdata, age):
    t = _texts(kdata)
    laws = _laws(kdata, age)
    rows = t[t["age"] == age].merge(laws, left_on="BILL_ID", right_on="bill_id", how="left",
                                     suffixes=("", "_m"))
    not_law = rows[rows["bill_id"].isna()]
    assert not_law.empty, f"{age}th: {len(not_law)} rows are not 법률안 of the master"
    wrong_no = rows[rows["bill_no"] != rows["bill_no_m"]]
    assert wrong_no.empty, f"{age}th: bill_no differs from the master for {wrong_no['BILL_ID'].head(3).tolist()}"


def test_texts_rows_outside_masters(kdata):
    t = _texts(kdata)
    orphans = t[t["age"].isna()]
    # One scraped row carries the old BILL_ID of bill 2203215, re-keyed upstream
    assert len(orphans) <= 1, f"{len(orphans)} rows join no master: {orphans['BILL_ID'].tolist()[:5]}"
    assert (orphans["source"] == "likms_scrape").all()
    assert orphans["bill_no"].isna().all()


@pytest.mark.parametrize("age", AGES)
def test_texts_coverage(kdata, age):
    t = _texts(kdata)
    laws = _laws(kdata, age)
    with_text = set(t.loc[t["propose_reason"].notna(), "BILL_ID"])
    share = laws["bill_id"].isin(with_text).mean()
    assert share >= TEXT_FLOOR[age], f"{age}th: {share:.4f} of law bills have a text"
    # Every proposer kind is covered, not only member bills
    by_kind = laws.assign(t=laws["bill_id"].isin(with_text)).groupby("ppsr_kind")["t"].mean()
    floor = {k: KIND_FLOOR_EXCEPTIONS.get((age, k), KIND_FLOOR) for k in by_kind.index}
    low = {k: round(v, 4) for k, v in by_kind.items() if v < floor[k]}
    assert not low, f"{age}th: low coverage by proposer kind {low}"


def test_texts_keep_scrape(kdata):
    ab = Path(os.environ.get("KNA_ASSEMBLY_BILLS_DIR",
                             REPO.parent / "korean-assembly-bills" / "data")) / "bill_texts.parquet"
    if not ab.exists():
        pytest.skip(f"{ab} not found (set KNA_ASSEMBLY_BILLS_DIR)")
    old = pd.read_parquet(ab)
    t = _texts(kdata).set_index("BILL_ID")
    missing = old.loc[~old["BILL_ID"].isin(t.index), "BILL_ID"]
    assert missing.empty, f"{len(missing)} scraped rows were dropped"
    j = old.set_index("BILL_ID").join(t, rsuffix="_new")
    assert (j["scrape_status"] == j["scrape_status_new"]).all()
    ok = j[j["scrape_status"] == "ok"]
    changed = ok[ok["propose_reason"] != ok["propose_reason_new"]]
    assert changed.empty, f"{len(changed)} scraped texts changed"


# ── alternatives ────────────────────────────────────────────────────

def _alt(kdata, age: int) -> pd.DataFrame:
    a = kdata.parquet("alternative_absorption.parquet")
    return a[a["age"] == age]


@pytest.mark.parametrize("age", AGES)
def test_alt_links_join_master(kdata, age):
    a = _alt(kdata, age)
    m = kdata.master(age, ["bill_id", "bill_no"]).set_index("bill_id")["bill_no"]
    bad_alt = a[~a["alt_bill_id"].isin(m.index)]
    assert bad_alt.empty, f"{age}th: alternatives not in the master {bad_alt['alt_bill_id'].unique()[:3]}"
    bad_abs = a[~a["absorbed_bill_id"].isin(m.index)]
    assert bad_abs.empty, f"{age}th: absorbed bills not in the master {bad_abs['absorbed_bill_id'].unique()[:3]}"
    assert (a["absorbed_bill_id"].map(m) == a["absorbed_bill_no"]).all(), f"{age}th: absorbed_bill_no"
    assert (a["alt_bill_id"].map(m) == a["alt_bill_no"]).all(), f"{age}th: alt_bill_no"


@pytest.mark.parametrize("age", AGES)
def test_alt_absorbed_are_alternative_discards(kdata, age):
    a = _alt(kdata, age)
    m = kdata.master(age, ["bill_id", "proc_rslt", "status"]).set_index("bill_id")
    abs_rslt = a["absorbed_bill_id"].map(m["proc_rslt"])
    alt_rslt = a["alt_bill_id"].map(m["proc_rslt"])
    alt_status = a["alt_bill_id"].map(m["status"])
    ok = ((abs_rslt == "대안반영폐기")
          # the alternative itself expired at the end of the term
          | ((abs_rslt == "임기만료폐기") & (alt_rslt == "임기만료폐기"))
          # the alternative is pending, so the absorbed bill has no result yet
          | (abs_rslt.isna() & (alt_status == "계류중")))
    bad = a[~ok]
    assert bad.empty, (f"{age}th: {len(bad)} absorbed bills are not 대안반영폐기, e.g. "
                       f"{list(zip(bad['absorbed_bill_no'], abs_rslt[~ok]))[:3]}")


@pytest.mark.parametrize("age", AGES)
def test_alt_links_unique(kdata, age):
    a = _alt(kdata, age)
    assert (a["alt_bill_id"] != a["absorbed_bill_id"]).all(), f"{age}th: self links"
    assert not a.duplicated(["alt_bill_id", "absorbed_bill_id"]).any(), f"{age}th: duplicate links"
    multi = a.groupby("absorbed_bill_id")["alt_bill_id"].nunique()
    assert (multi <= 1).all(), f"{age}th: bills linked to two alternatives {multi[multi > 1].index[:3].tolist()}"


@pytest.mark.parametrize("age", AGES)
def test_alt_coverage(kdata, age):
    a = _alt(kdata, age)
    m = kdata.master(age, ["bill_id", "proc_rslt"])
    discarded = m.loc[m["proc_rslt"] == "대안반영폐기", "bill_id"]
    share = discarded.isin(set(a["absorbed_bill_id"])).mean()
    assert share >= ALT_FLOOR[age], f"{age}th: {share:.4f} of 대안반영폐기 bills are linked"
