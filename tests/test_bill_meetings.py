"""bill_meetings.parquet and collect_likms_billinfo.py.

The table is built from data/raw/likms_billinfo_{age}.parquet, which
collect_likms_billinfo.py extract writes from the LIKMS bill pages. The
rebuild check runs the build step on those raw files and compares the result
with the shipped table. The parser checks run on a small synthetic page.
"""

from __future__ import annotations

import argparse

import pandas as pd
import pytest

import collect_likms_billinfo as clb
from conftest import AGES

DTYPES = {"age": "int64", "bill_no": "object", "bill_id": "object", "stage": "object",
          "seq": "int32", "meeting_name": "object", "meeting_date": "object",
          "present_date": "object", "result": "object", "conf_num": "Int64"}
# kr-hearings-data keeps 35218 as an identical duplicate copy of 35291, and the
# hearing summary leaves duplicate copies out
DUPLICATE_COPIES = {35218}


def test_schema_and_key(kdata):
    t = kdata.parquet("bill_meetings.parquet")
    assert t.dtypes.astype(str).to_dict() == DTYPES
    assert not t.duplicated(["bill_no", "stage", "seq"]).any()
    assert set(t["stage"]) == set(clb.STAGES.values())
    assert t["meeting_date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    assert (t["seq"] >= 1).all()
    # a row without a meeting name is a plenary row that links the minutes
    nameless = t[t["meeting_name"].isna()]
    assert (nameless["stage"] == "plenary").all() and nameless["conf_num"].notna().all()
    assert t.loc[t["stage"] != "plenary", "present_date"].isna().all()


@pytest.mark.parametrize("age", AGES)
def test_bills_are_law_bills_of_the_master(kdata, age):
    t = kdata.parquet("bill_meetings.parquet", ["age", "bill_no", "bill_id"])
    t = t[t["age"] == age].drop_duplicates("bill_no")
    master = kdata.master(age, ["bill_no", "bill_id", "bill_kind"])
    law = master[master["bill_kind"] == "법률안"].astype({"bill_no": str}).set_index("bill_no")["bill_id"]
    assert len(t) > 0.7 * len(law)
    assert t["bill_no"].isin(law.index).all()
    assert (t["bill_id"].to_numpy() == law.loc[t["bill_no"]].to_numpy()).all()


def test_minutes_are_in_the_hearing_summary(kdata):
    t = kdata.parquet("bill_meetings.parquet", ["conf_num", "meeting_date"])
    s = kdata.parquet("hearing_meetings_summary.parquet", ["conf_num", "date"])
    linked = t[t["conf_num"].notna()]
    missing = linked[~linked["conf_num"].isin(set(s["conf_num"]))]
    # only meetings held after the summary ends, and duplicate copies
    early = missing[missing["meeting_date"] <= s["date"].max()]
    assert set(early["conf_num"]) <= DUPLICATE_COPIES
    assert len(missing) < 0.005 * len(linked)


def test_rebuild_equals_shipped(kdata, tmp_path):
    shipped = kdata.parquet("bill_meetings.parquet")
    missing = [a for a in AGES if not (clb.RAW_DIR / f"likms_billinfo_{a}.parquet").exists()]
    if missing:
        pytest.skip(f"no data/raw/likms_billinfo_{missing[0]}.parquet")
    clb.build(argparse.Namespace(out=str(tmp_path), master_dir=str(kdata.root)))
    built = pd.read_parquet(tmp_path / "bill_meetings.parquet")
    pd.testing.assert_frame_equal(built, shipped)


def _row(*cells):
    return "<tr>" + "".join(f'<td class="{c}"><i>x</i><span>{v}</span></td>' if c != "doc"
                            else f'<td class="doc">{v}</td>' for c, v in cells) + "</tr>"


def _section(title, *rows):
    return f"<div><h4>{title}</h4><table><thead><tr><th>x</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


PDF = '<div class="report"><a class="icon_pdf" href="https://record.assembly.go.kr/assembly/viewer/minutes/download/pdf.do?id={}">PDF</a></div>'
PAGE = "".join([
    _section("소관위 심사정보", _row(("committeeName", "법제사법위원회"), ("submitDt", "2021-04-26"),
                                ("presentDt", "2021-06-18"), ("procDt", "2021-09-24"),
                                ("inscResultCd", "대안반영폐기"), ("doc align_left", ""))),
    _section("소관위 회의정보",
             _row(("mtngName", "제388회 국회(임시회) 제3차 전체회의"), ("mtngDt", "2021-06-18"),
                  ("procResultName", "상정/제안설명"), ("doc", PDF.format(45915))),
             _row(("mtngName", "제390회 국회(정기회) 제1차 법안심사제1소위원회"), ("mtngDt", "2021-09-23"),
                  ("procResultName", "축조심사"), ("doc", ""))),
    _section("본회의 심의정보",
             _row(("mtngName", ""), ("presentDt", "2021-09-28"), ("procDt", "2021-09-28"),
                  ("inscResultCd", "대안반영폐기"), ("doc", PDF.format(46511)))),
])


def test_parse_page_reads_meetings_and_minutes():
    rows, _ = clb.parse_page(21, "2109681", PAGE)
    rows = pd.DataFrame(rows)
    assert list(rows["section"]) == ["소관위 심사정보", "소관위 회의정보", "소관위 회의정보", "본회의 심의정보"]
    assert list(rows["seq"]) == [1, 1, 2, 1]
    assert rows.loc[0, "committee"] == "법제사법위원회" and pd.isna(rows.loc[0, "conf_num"])
    assert rows.loc[1, "conf_num"] == 45915 and rows.loc[1, "meeting_dt"] == "2021-06-18"
    assert pd.isna(rows.loc[2, "conf_num"])
    assert rows.loc[3, "conf_num"] == 46511 and rows.loc[3, "meeting_name"] is None
    assert rows.loc[3, "proc_dt"] == "2021-09-28"


def test_parse_page_stops_on_unknown_layout():
    with pytest.raises(ValueError, match="unknown heading"):
        clb.parse_page(21, "1", _section("새 정보", _row(("mtngName", "x"))))
    with pytest.raises(ValueError, match="cells"):
        clb.parse_page(21, "1", _section("소관위 회의정보", _row(("mtngName", "x"), ("mtngDt", "2021-01-01"))))
    with pytest.raises(ValueError, match="no review section"):
        clb.parse_page(21, "1", "<div>tabs only</div>")
