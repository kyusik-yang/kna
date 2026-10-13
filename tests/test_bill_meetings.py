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
          "present_date": "object", "result": "object", "conf_num": "Int64",
          "conf_check": "object", "conf_num_matched": "Int64", "conf_match": "object"}
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


def test_conf_check_values(kdata):
    t = kdata.parquet("bill_meetings.parquet", ["conf_num", "conf_check", "stage", "meeting_name"])
    s = kdata.parquet("hearing_meetings_summary.parquet", ["conf_num"])
    assert set(t["conf_check"].dropna()) <= {"ok", "date_differs", "other_meeting"}
    # null exactly where the row cannot be checked
    checkable = t["conf_num"].notna() & t["conf_num"].isin(set(s["conf_num"]))
    assert (t["conf_check"].notna() == checkable).all()
    assert (t["conf_check"] == "ok").sum() > 0.99 * checkable.sum()
    # every wrong-meeting row is a named subcommittee meeting of a committee stage
    other = t[t["conf_check"] == "other_meeting"]
    assert other["meeting_name"].str.contains("소위").all() and (other["stage"] != "plenary").all()


def test_no_withdrawal_rows(kdata):
    t = kdata.parquet("bill_meetings.parquet", ["stage", "result", "conf_num", "meeting_name"])
    plenary = t[t["stage"] == "plenary"]
    assert not ((plenary["result"] == "철회") & plenary["conf_num"].isna()).any()
    # the withdrawal rows printed the meeting name without a sitting number
    assert not plenary["meeting_name"].fillna("").str.contains("제차").any()


def test_conf_match(kdata):
    t = kdata.parquet("bill_meetings.parquet", ["stage", "meeting_name", "meeting_date", "conf_num",
                                                "conf_num_matched", "conf_match"])
    s = kdata.parquet("hearing_meetings_summary.parquet", ["conf_num", "date", "date_end", "is_subcommittee"])
    assert set(t["conf_match"].dropna()) <= {"agenda_and_name", "agenda", "name"}
    assert (t["conf_match"].notna() == t["conf_num_matched"].notna()).all()
    matched = t[t["conf_num_matched"].notna()]
    assert matched["conf_num"].isna().all()
    assert (matched["stage"] != "related_committee").all()
    # every matched meeting is in the hearing summary and was held on the row's date
    m = matched.merge(s, left_on="conf_num_matched", right_on="conf_num", how="left", suffixes=("", "_s"))
    assert m["date"].notna().all()
    assert ((m["meeting_date"] >= m["date"]) & (m["meeting_date"] <= m["date_end"])).all()
    # a named subcommittee row gets a subcommittee meeting unless it is a hearing
    name = m["meeting_name"].fillna("")
    plain = ~name.str.contains("공청회|청문회") & (m["stage"] == "committee")
    named_sub = name.str.contains("소위") & ~name.str.contains("안건조정")
    assert (named_sub[plain] == m.loc[plain, "is_subcommittee"]).all()
    # most rows without minutes get a meeting
    assert len(matched) > 0.8 * t["conf_num"].isna().sum()


def test_conf_check_rule():
    summary = pd.DataFrame({"conf_num": [1, 2, 3], "date": ["2026-09-11", "2026-09-15", "2016-02-23"],
                            "date_end": ["2026-09-11", "2026-09-15", "2016-03-02"],
                            "is_subcommittee": [False, True, False]})
    m = pd.DataFrame({
        "conf_num": pd.array([1, 1, 2, 1, 3, 3, None, 9], dtype="Int64"),
        "meeting_name": ["제439회 국회(정기회) 제1차 전체회의", "제439회 국회(정기회) 제1차 소위회의",
                         "제439회 국회(정기회) 제1차 법안심사제1소위원회", "제1차 안건조정위원회", None, None,
                         "제1차 전체회의", "제1차 전체회의"],
        "meeting_date": ["2026-09-11", "2026-09-15", "2026-09-16", "2026-09-11", "2016-03-02",
                         "2016-03-03", "2026-09-11", "2026-09-11"],
    }, index=[10, 11, 12, 13, 14, 15, 16, 17])
    got = clb.conf_check(m, summary)
    assert list(got.index) == list(m.index)
    # 안건조정위원회 is no subcommittee, a later day of a multi-day sitting is ok,
    # and a row without a conf_num or with one the summary lacks is null
    assert got.tolist()[:6] == ["ok", "other_meeting", "date_differs", "ok", "ok", "date_differs"]
    assert got.iloc[6:].isna().all()


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
