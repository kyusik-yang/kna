"""`kna search --proposer` matches lead-proposer names exactly.

rst_proposer holds one name, or several comma-joined names for joint
leads. A name must equal one of those tokens, so 김현 does not return the
bills of 김현정, and a joint lead listed second is still found.
"""

from __future__ import annotations

import re

import pytest
from click.testing import CliRunner

from kna.cli import cli
from kna.data import BillDB
from kna.queries import search_bills

AGE = 22


def _tokens(s) -> list[str]:
    return [t.strip() for t in str(s).split(",") if t.strip()] if isinstance(s, str) else []


@pytest.fixture(scope="module")
def bills22(kdata):
    return kdata.master(AGE, ["bill_id", "bill_nm", "rst_proposer"])


def _expected(bills, name: str) -> set:
    hit = bills["rst_proposer"].map(lambda s: name in _tokens(s))
    return set(bills.loc[hit, "bill_id"])


def test_proposer_is_exact_not_substring(data_dir, bills22):
    names = {t for s in bills22["rst_proposer"] for t in _tokens(s)}
    if not {"김현", "김현정"} <= names:
        pytest.skip("김현 and 김현정 are not both lead proposers in the 22nd")
    res, total = search_bills(BillDB(data_dir), "", age=AGE, proposer="김현",
                              limit=len(bills22))
    want = _expected(bills22, "김현")
    assert total == len(want) > 0
    assert set(res["bill_id"]) == want
    # No result is a 김현정-only bill
    assert all("김현" in _tokens(s) for s in res["rst_proposer"])


def test_joint_lead_listed_second_is_found(data_dir, bills22):
    joint = bills22[bills22["rst_proposer"].map(lambda s: len(_tokens(s)) > 1)]
    if joint.empty:
        pytest.skip("no joint-lead bills in the 22nd")
    row = joint.iloc[0]
    second = _tokens(row["rst_proposer"])[1]
    res, total = search_bills(BillDB(data_dir), "", age=AGE, proposer=second,
                              limit=len(bills22))
    assert row["bill_id"] in set(res["bill_id"])
    assert total == len(_expected(bills22, second))


def test_cli_proposer_count(data_dir, bills22, tmp_path):
    names = {t for s in bills22["rst_proposer"] for t in _tokens(s)}
    if "김현" not in names:
        pytest.skip("김현 is not a lead proposer in the 22nd")
    keyword = "법"
    sub = bills22[bills22["bill_nm"].str.contains(keyword, na=False)]
    want = len(_expected(sub, "김현"))
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        r = runner.invoke(cli, ["search", keyword, "--proposer", "김현",
                                "--assembly", str(AGE), "-n", "3"])
    assert r.exit_code == 0, r.output
    m = re.search(r"of (\d+) results", r.output)
    assert m, r.output
    assert int(m.group(1)) == want
