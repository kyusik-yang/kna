"""bill_documents.parquet and collect_likms_docs.py.

The table is built from data/raw/likms_billinfo_docs_{age}.parquet (the
document links that collect_likms_billinfo.py extract reads off the LIKMS
bill pages) and data/raw/likms_doc_files.parquet (what collect_likms_docs.py
measure finds in each downloaded file). The rebuild check runs the build
step on those raw files and compares the result with the shipped table. The
parser and status checks run on small synthetic inputs.
"""

from __future__ import annotations

import argparse
import io
import zipfile

import pandas as pd
import pytest

import collect_likms_billinfo as clb
import collect_likms_docs as cld
from conftest import AGES

DTYPES = {"age": "int64", "bill_no": "object", "bill_id": "object", "stage": "object", "seq": "int32",
          "committee": "object", "doc_seq": "int32", "doc_type": "object", "book_id": "object",
          "pdf_url": "object", "hwp_url": "object", "file_format": "object", "pages": "Int64",
          "chars": "Int64", "text_status": "object", "report_key": "object", "report_bills": "Int64"}


def test_schema_and_key(kdata):
    t = kdata.parquet("bill_documents.parquet")
    assert t.dtypes.astype(str).to_dict() == DTYPES
    assert not t.duplicated(["bill_no", "stage", "seq", "doc_seq"]).any()
    assert set(t["stage"]) <= set(cld.STAGES.values())
    assert (t["pdf_url"].notna() | t["hwp_url"].notna()).all()


def test_measures_only_on_collected_types(kdata):
    t = kdata.parquet("bill_documents.parquet")
    collected = t["doc_type"].isin(cld.TYPES)
    assert t.loc[collected, "text_status"].isin(cld.STATUSES).all()
    assert t.loc[~collected, ["file_format", "pages", "chars", "text_status", "report_key"]].isna().all().all()
    # report_key exactly on text documents, and report_bills counts the bills that share it
    assert (t["report_key"].notna() == (t["text_status"] == "text")).all()
    keyed = t[t["report_key"].notna()]
    n = keyed.groupby("report_key")["bill_no"].nunique()
    assert (keyed["report_bills"].to_numpy() == keyed["report_key"].map(n).to_numpy()).all()
    obtained = t[collected & (t["text_status"] != "not_obtained")]
    assert obtained["file_format"].isin(["pdf", "hwp"]).all()
    assert (obtained.loc[obtained["file_format"] == "pdf", "pages"].dropna() >= 1).all()
    # nearly every collected document is obtained and has text
    docs = t[collected].drop_duplicates(["bill_no", "book_id"])
    assert (docs["text_status"] == "text").mean() > 0.99


@pytest.mark.parametrize("age", AGES)
def test_bills_are_law_bills_of_the_master(kdata, age):
    t = kdata.parquet("bill_documents.parquet", ["age", "bill_no", "bill_id"])
    t = t[t["age"] == age].drop_duplicates("bill_no")
    master = kdata.master(age, ["bill_no", "bill_id", "bill_kind"])
    law = master[master["bill_kind"] == "법률안"].astype({"bill_no": str}).set_index("bill_no")["bill_id"]
    assert len(t) > 0.7 * len(law)
    assert t["bill_no"].isin(law.index).all()
    assert (t["bill_id"].to_numpy() == law.loc[t["bill_no"]].to_numpy()).all()


def test_rebuild_equals_shipped(kdata, tmp_path):
    shipped = kdata.parquet("bill_documents.parquet")
    missing = [p.name for p in [cld.FILES] + [clb.RAW_DIR / f"likms_billinfo_docs_{a}.parquet" for a in AGES]
               if not p.exists()]
    if missing:
        pytest.skip(f"no data/raw/{missing[0]}")
    cld.build(argparse.Namespace(out=str(tmp_path), master_dir=str(kdata.root)))
    built = pd.read_parquet(tmp_path / "bill_documents.parquet")
    pd.testing.assert_frame_equal(built, shipped)


DOCS = ('<div class="report"><a class="icon_pdf" href="/filegate/servlet/FileGate?bookId=9DE06B4A-E84F&amp;type=0" '
        'title="소관위 심사정보 검토보고서 (PDF 파일 다운로드)">PDF</a><span>검토보고서</span></div>'
        '<div class="report"><a class="icon_hwp" href="/filegate/servlet/FileGate?bookId=64F5A243&amp;type=0" '
        'title="소관위 심사정보 심사보고서 (HWP 파일 다운로드)">한글</a>'
        '<a class="icon_pdf" href="/filegate/servlet/FileGate?bookId=64F5A243&amp;type=1" '
        'title="소관위 심사정보 심사보고서 (PDF 파일 다운로드)">PDF</a><span>심사보고서</span></div>')


def test_parse_page_reads_document_links():
    from test_bill_meetings import _row, _section
    page = _section("소관위 심사정보", _row(("committeeName", "국방위원회"), ("submitDt", "2021-04-26"),
                                        ("presentDt", "2021-06-18"), ("procDt", "2021-09-24"),
                                        ("inscResultCd", "대안반영폐기"), ("doc", DOCS)))
    rows, docs = clb.parse_page(21, "2109281", page)
    d = pd.DataFrame(docs)
    assert list(d["doc_type"]) == ["검토보고서", "심사보고서"] and list(d["doc_seq"]) == [1, 2]
    assert (d["seq"] == 1).all() and (d["section"] == "소관위 심사정보").all()
    # the link is kept as the page gives it, here a PDF served under type=0
    assert d.loc[0, "pdf_url"].endswith("bookId=9DE06B4A-E84F&type=0") and d.loc[0, "hwp_url"] is None
    assert d.loc[1, "book_id"] == "64F5A243" and d.loc[1, "hwp_url"].endswith("type=0")
    two_ids = DOCS.replace("bookId=64F5A243&amp;type=1", "bookId=OTHER&amp;type=1")
    with pytest.raises(ValueError, match="two bookIds"):
        clb.parse_page(21, "1", _section("소관위 심사정보", _row(("committeeName", "x"), ("submitDt", "x"),
                                                                 ("presentDt", "x"), ("procDt", "x"),
                                                                 ("inscResultCd", "x"), ("doc", two_ids))))


def test_text_status_rules():
    ph = "국회법제58조제4항에따라바로법안심사소위원회에회부하여검토보고서가없음."
    assert cld.text_status("검토보고서", "pdf", 1, ph, 0) == "placeholder"
    # the same words in a longer report, or in a 심사보고서, are not a placeholder
    assert cld.text_status("심사보고서", "pdf", 1, ph, 0) == "text"
    assert cld.text_status("검토보고서", "pdf", 3, ph + "가" * 600, 0) == "text"
    assert cld.text_status("심사보고서", "pdf", 1, "", 0) == "empty"
    assert cld.text_status("검토보고서", "pdf", 12, "목차", 24) == "scanned"
    assert cld.text_status("검토보고서", "pdf", 12, "목차", 0) == "empty"
    # one page with a title only stays text
    assert cld.text_status("체계자구검토보고서", "pdf", 1, "국민연금법일부개정법률안", 0) == "text"
    assert cld.text_status("심사보고서", "hwp", None, "", 0) == "empty"


def test_report_key_ignores_layout_only():
    a = "국회법 일부개정법률안\n검  토  보  고\n\f- 1 -\n가ㆍ나"
    assert cld.report_key(a) == cld.report_key("국회법일부개정법률안 검토보고 -1- 가·나")
    assert cld.report_key(a) != cld.report_key(a.replace("1", "2"))


def test_hwpx_text():
    xml = ('<hs:sec><hp:p><hp:run><hp:t>검토</hp:t><hp:t>보고</hp:t></hp:run></hp:p>'
           '<hp:p><hp:run><hp:t>A &amp; B</hp:t></hp:run></hp:p></hs:sec>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", xml)
    text, err = cld.hwpx_text(buf.getvalue())
    assert err is None and text.split("\n")[:2] == ["검토보고", "A & B"]
