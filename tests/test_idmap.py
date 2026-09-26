"""legislator_id_mapping.parquet from link_external.py idmap.

in_dw_nominate is kept for one release as a deprecated alias of
in_ideal_points, so code written against the old column keeps working.
"""

from __future__ import annotations

import pytest

IDMAP = "legislator_id_mapping.parquet"


def test_in_dw_nominate_is_alias_of_in_ideal_points(kdata):
    m = kdata.parquet(IDMAP)
    if "in_ideal_points" not in m.columns:
        pytest.skip(f"{IDMAP} predates in_ideal_points")
    assert "in_dw_nominate" in m.columns, "deprecated alias in_dw_nominate is missing"
    assert m["in_dw_nominate"].equals(m["in_ideal_points"])


def test_in_ideal_points_matches_bridged_series(kdata):
    m = kdata.parquet(IDMAP)
    if "in_ideal_points" not in m.columns:
        pytest.skip(f"{IDMAP} predates in_ideal_points")
    ip = kdata.csv("ideal_points_bridged.csv")
    assert set(m.loc[m["in_ideal_points"], "mona_cd"]) == set(ip["member_id"])
