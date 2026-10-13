"""hearings_agenda.py, bill_agenda_17.parquet and conf_num_matched of bill_meetings.

The rule checks run on small synthetic agendas. The table checks read the
shipped files. The rebuild check needs the kr-hearings-data v10 files in
KNA_HEARINGS_V10_DIR (default ../kr-hearings-data/v10/build/release) and the
hanja package, and skips without them.
"""

from __future__ import annotations

import argparse
import importlib.util

import pandas as pd
import pytest

import build_hearings_summary as bhs
import collect_likms_billinfo as clb
import hearings_agenda as ha
from conftest import AGES

DTYPES = {"bill_no": "object", "bill_id": "object", "conf_num": "int64", "meeting_date": "object",
          "committee": "object", "is_subcommittee": "bool", "match": "object",
          "in_bill_meetings": "bool", "title_in_minutes": "boolean"}


def _bills(rows):
    b = pd.DataFrame(rows, columns=["bill_no", "bill_id", "bill_nm", "ppsr_kind", "rst_proposer"])
    b["age"] = b["bill_no"].str[:2].astype(int)
    b["tn"] = b["bill_nm"].map(ha.norm)
    b["pn"] = [ha.norm(p) + "의원대표발의" if k == "의원" else ("정부제출" if k == "정부" else "")
               for k, p in zip(b["ppsr_kind"], b["rst_proposer"])]
    b["shared"] = (b["pn"] != "") & b.duplicated(["age", "tn", "pn"], keep=False)
    return b


def _items(texts, bill_ids=None, bill_nos=None):
    n = len(texts)
    a = pd.DataFrame({"conf_num": range(n), "text": texts,
                      "bill_id": bill_ids or [None] * n, "bill_no": bill_nos or [None] * n})
    return list(ha.prepare_agenda(a).itertuples())


BILLS = _bills([
    ("171718", "A1", "주택법 일부개정법률안", "의원", "홍길동"),
    ("171719", "A2", "주택법 일부개정법률안", "의원", "김철수"),
    ("171720", "A3", "주택법 일부개정법률안", "의원", "김철수"),
    ("171721", "A4", "주택법 일부개정법률안(대안)", "위원장", None),
    ("2100233", "B1", "국회법 일부개정법률안", "정부", None),
]).set_index("bill_no", drop=False)


def test_same_number():
    assert ha.same_number("1718", "171718") and ha.same_number("171718", "171718")
    assert ha.same_number("233", "2100233") and ha.same_number("2100233", "2100233")
    assert not ha.same_number("1719", "171718")


def test_lists_bill():
    pytest.importorskip("hanja")
    hong, kim, kim2, alt, gov = (BILLS.loc[b] for b in ["171718", "171719", "171720", "171721", "2100233"])
    items = _items([
        "1. 住宅法 일부개정법률안(홍길동 의원 대표발의)",            # Hanja title, 대표발의자
        "2. 주택법 일부개정법률안(이영희 의원 대표발의)(이영희ㆍ홍길동 의원 발의)",  # 홍길동 cosponsors only
        "3. 주택법 일부개정법률안(김철수 의원 대표발의)",            # two bills share it
        "4. 주택법 일부개정법률안(김철수 의원 대표발의)(의안번호 1720)",
        "5. 주택법 일부개정법률안(대안)(국토위원장 제출)",
        "6. 주택법 일부개정법률안(홍길동 의원 대표발의)",
        "7. 국회법 일부개정법률안(정부 제출)(의안번호 2100233)",
    ], bill_ids=[None, "A1", None, None, "A4", "A2", None])
    assert ha.lists_bill(items[0], hong) == "unique"
    assert ha.lists_bill(items[1], hong) == ""
    assert ha.lists_bill(items[2], kim) == "shared" and ha.lists_bill(items[2], kim2) == "shared"
    assert ha.lists_bill(items[3], kim2) == "number" and ha.lists_bill(items[3], kim) == ""
    assert ha.lists_bill(items[4], alt) == "id"
    # a bill_id link alone does not count for a bill with a 대표발의자
    assert ha.lists_bill(items[5], kim) == "" and ha.lists_bill(items[5], hong) == "unique"
    assert ha.lists_bill(items[6], gov) == "number"


def test_match_rows():
    meetings = pd.DataFrame({
        "conf_num": [1, 2, 3, 4, 5],
        "term": 17, "class_name": ["상임위원회"] * 4 + ["국회본회의"],
        "committee_raw": ["건설교통위원회", "건설교통위원회", "법제사법위원회", "건설교통위원회", "본회의"],
        "committee_key": ["land", "land", "judiciary", "land", "plenary"],
        "is_subcommittee": [False, True, False, False, False],
        "session_no": [250.0, 250.0, 250.0, 251.0, 250.0],
        "sitting": ["제3차", "제1차", "제17차", "제2차", "제5차"],
        "date": ["2004-12-07", "2004-12-07", "2004-12-07", "2004-12-20", "2004-12-08"],
        "date_end": [None, None, None, None, "2004-12-09"],
    })
    agenda = ha.prepare_agenda(pd.DataFrame({
        "conf_num": [1, 3, 4],
        "text": ["1. 주택법 일부개정법률안(홍길동 의원 대표발의)", "2. 주택법 일부개정법률안(홍길동 의원 대표발의)",
                 "1. 주택법 일부개정법률안(김철수 의원 대표발의)"],
        "bill_id": [None, None, None], "bill_no": [None, None, None]}))
    raw = pd.DataFrame({"section": ["소관위 심사정보"] * 3, "bill_no": ["171718", "171719", "171720"],
                        "committee": ["건설교통위원회"] * 3})
    bills = BILLS.reset_index(drop=True).assign(committee_nm="건설교통위원회")
    rows = pd.DataFrame({
        "bill_no": ["171718", "171718", "171718", "171718", "171719", "171719", "171718"],
        "stage": ["committee", "committee", "judiciary", "plenary", "committee", "committee", "related_committee"],
        "meeting_name": ["제250회 국회(임시회) 제3차 전체회의", "제250회 국회(임시회) 제1차 법안심사소위원회",
                         "제17회 국회(임시회) 제250차 전체회의", "제250회 국회(정기회)제5차 본회의",
                         "제251회 국회(정기회) 제2차 전체회의", "제251회 국회(정기회) 제9차 전체회의",
                         "제250회 국회(임시회) 제3차 전체회의"],
        "meeting_date": ["2004-12-07", "2004-12-07", "2004-12-07", "2004-12-09", "2004-12-20", "2004-12-20",
                         "2004-12-07"],
    }, index=[10, 11, 12, 13, 14, 15, 16])
    got = ha.match_rows(rows, bills, raw, meetings, agenda)
    # the agenda and the name agree; the name only; the 17th 법사위 swap; a later day of a
    # plenary sitting; a shared title with the name; a shared title without it; a related committee
    assert got["conf_match"].tolist()[:5] == ["agenda_and_name", "name", "agenda_and_name", "name", "name"]
    assert got["conf_num_matched"].tolist()[:5] == [1, 2, 3, 5, 4]
    assert got.loc[[15, 16]].isna().all().all()


def test_schema_and_key(kdata):
    t = kdata.parquet(ha.OUT_NAME)
    assert t.dtypes.astype(str).to_dict() == DTYPES
    assert not t.duplicated(["bill_no", "conf_num"]).any()
    assert set(t["match"]) <= {"number", "title", "id"}


def test_bills_and_meetings(kdata):
    t = kdata.parquet(ha.OUT_NAME)
    m = kdata.master(17, ["bill_no", "bill_id", "bill_kind"]).astype({"bill_no": str})
    law = m[m["bill_kind"] == "법률안"].set_index("bill_no")["bill_id"].astype(str)
    assert t["bill_no"].isin(law.index).all()
    assert (t["bill_id"].to_numpy() == law.loc[t["bill_no"]].to_numpy()).all()
    s = kdata.parquet("hearing_meetings_summary.parquet", ["conf_num", "term", "date", "is_subcommittee"])
    x = t.merge(s, on="conf_num", how="left", suffixes=("", "_s"))
    assert (x["term"] == 17).all() and (x["date"] == x["meeting_date"]).all()
    assert (x["is_subcommittee"] == x["is_subcommittee_s"]).all()


def test_in_bill_meetings(kdata):
    t = kdata.parquet(ha.OUT_NAME)
    bm = kdata.parquet("bill_meetings.parquet", ["age", "bill_no", "stage", "conf_num", "conf_num_matched",
                                                 "meeting_date"])
    bm = bm[(bm["age"] == 17) & (bm["stage"] == "committee")]
    known = (set(zip(bm["bill_no"], bm["conf_num"].dropna().astype(int)))
             | set(zip(bm["bill_no"], bm["conf_num_matched"].dropna().astype(int)))
             | set(zip(bm["bill_no"], bm["meeting_date"])))
    want = [(b, c) in known or (b, d) in known for b, c, d in zip(t["bill_no"], t["conf_num"], t["meeting_date"])]
    assert t["in_bill_meetings"].tolist() == want
    # the agenda finds most of the committee meetings the pages list for these bills
    assert t["in_bill_meetings"].mean() > 0.3


def test_rebuild_equals_shipped(kdata, tmp_path):
    if importlib.util.find_spec("hanja") is None:
        pytest.skip("the hanja package is not installed")
    if bhs.v10_layout(bhs.V10_DIR)[0] is None:
        pytest.skip(f"no kr-hearings-data v10 files in {bhs.V10_DIR} (set KNA_HEARINGS_V10_DIR)")
    missing = [a for a in AGES if not (clb.RAW_DIR / f"likms_billinfo_{a}.parquet").exists()]
    if missing:
        pytest.skip(f"no data/raw/likms_billinfo_{missing[0]}.parquet")
    root = str(kdata.root)
    clb.build(argparse.Namespace(out=str(tmp_path), master_dir=root, v10_dir=str(bhs.V10_DIR), v10_version=None))
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "bill_meetings.parquet"),
                                  kdata.parquet("bill_meetings.parquet"))
    ha.build(argparse.Namespace(out=str(tmp_path), master_dir=root, v10_dir=str(bhs.V10_DIR), v10_version=None))
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / ha.OUT_NAME), kdata.parquet(ha.OUT_NAME))
