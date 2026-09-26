"""Regression tests for fixes made after the 0.7.0 verification pass.

1. birth_calendar comes from the roster endpoints (BTH_GBN_NM); ALLNAMEMBER's
   BIRDY_DIV_CD is coded the opposite way.
2. Every committee alternative in the master, including a vetoed alternative
   that is listed only under its GOV_ record, was queried for absorbed bills.
3. The documented party overrides reach members, roll calls and ideal points.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from conftest import AGES, VOTE_AGES


def _raw(kdata, rel: str):
    p = kdata.raw / rel
    if not p.exists():
        pytest.skip(f"{rel} not in {kdata.raw}")
    return p


@pytest.mark.parametrize("age", AGES)
def test_birth_calendar_matches_roster(kdata, age):
    mem = kdata.members(age)
    roster = pd.read_parquet(_raw(kdata, f"members/npffdutiapkzbfyvr_{age}.parquet"))
    current = pd.read_parquet(_raw(kdata, "members/nwvrqwxyaytdsfvhu.parquet"))
    want = pd.concat([roster[["MONA_CD", "BTH_GBN_NM"]], current[["MONA_CD", "BTH_GBN_NM"]]])
    want = want.drop_duplicates("MONA_CD").set_index("MONA_CD")["BTH_GBN_NM"]
    j = mem.set_index("mona_cd")["birth_calendar"].to_frame().join(want, how="inner")
    assert len(j) > 0
    bad = j[j["birth_calendar"] != j["BTH_GBN_NM"]]
    assert bad.empty, f"{age}th: {len(bad)} members' birth_calendar differs from the roster"


@pytest.mark.parametrize("age", AGES)
def test_every_alternative_was_queried(kdata, age):
    log = _raw(kdata, f"fetchlog/TVBPMBILL11_{age}.jsonl")
    queried = {json.loads(line)["key"] for line in open(log, encoding="utf-8") if line.strip()}
    m = kdata.master(age, ["bill_id", "bill_nm"])
    alts = set(m.loc[m["bill_nm"].fillna("").str.strip().str.endswith("(대안)"), "bill_id"])
    missing = sorted(a for a in alts - queried if not a.startswith("GOV_"))
    assert not missing, f"{age}th: {len(missing)} alternatives never queried, e.g. {missing[:3]}"


def _overrides(kdata) -> pd.DataFrame:
    return pd.read_csv(_raw(kdata, "members/party_overrides.csv"), dtype=str)


def test_party_overrides_in_members(kdata):
    ov = _overrides(kdata)
    for _, row in ov.iterrows():
        mem = kdata.members(int(row["age"]))
        got = mem.loc[mem["mona_cd"] == row["mona_cd"], "party"]
        assert list(got) == [row["party"]], f"{row['age']}th {row['member_name']}: {list(got)}"


def test_party_overrides_in_roll_calls(kdata):
    ov = _overrides(kdata)
    rc = kdata.parquet("roll_calls_all.parquet", ["term", "member_id", "party"]).drop_duplicates()
    for _, row in ov.iterrows():
        if int(row["age"]) not in VOTE_AGES:
            continue
        got = rc.loc[(rc["term"] == int(row["age"])) & (rc["member_id"] == row["mona_cd"]), "party"]
        assert set(got) <= {row["party"]}, f"{row['age']}th {row['member_name']}: {set(got)}"


@pytest.mark.parametrize("series", ["bridged", "wnominate", "dwnominate"])
def test_party_overrides_in_ideal_points(kdata, series):
    ov = _overrides(kdata)
    ip = kdata.csv(f"ideal_points_{series}.csv")
    for _, row in ov.iterrows():
        got = ip.loc[(ip["term"] == int(row["age"])) & (ip["member_id"] == row["mona_cd"]), "party"]
        assert set(got) <= {row["party"]}, f"{series} {row['age']}th {row['member_name']}: {set(got)}"
