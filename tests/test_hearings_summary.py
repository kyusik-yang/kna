"""hearing_meetings_summary.parquet and build_hearings_summary.py.

Since 0.8.1 the shipped table is built from kr-hearings-data version 10. The
v10 rebuild check reads the v10 files from KNA_HEARINGS_V10_DIR (default
../kr-hearings-data/v10/build/release) and skips when they are missing. It
reads 15 million turns. The v9 check reproduces the table of 0.6.0 to 0.8.0
and runs only against that table. The layout checks run on small synthetic
builds.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

import build_hearings_summary as bhs

DTYPES = {"meeting_id": "object", "term": "Int64", "committee": "object",
          "hearing_type": "object", "date": "object", "n_speeches": "int64",
          "n_legislators": "int64", "parties": "object", "conf_num": "int64",
          "is_subcommittee": "bool", "is_confirmation_hearing": "bool"}


def test_shipped_summary_schema(kdata):
    shipped = kdata.parquet("hearing_meetings_summary.parquet")
    if "conf_num" not in shipped.columns:
        pytest.skip("the shipped table is the v9 one (0.6.0 to 0.8.0)")
    assert shipped.dtypes.astype(str).to_dict() == DTYPES
    assert shipped["conf_num"].is_unique
    ids = shipped["meeting_id"].dropna()
    assert ids.is_unique
    assert (shipped["n_legislators"] <= shipped["n_speeches"]).all()


def test_v10_rebuild_equals_shipped_summary(kdata):
    shipped = kdata.parquet("hearing_meetings_summary.parquet")
    if "conf_num" not in shipped.columns:
        pytest.skip("the shipped table is the v9 one (0.6.0 to 0.8.0)")
    if bhs.v10_layout(bhs.V10_DIR)[0] is None:
        pytest.skip(f"no kr-hearings-data v10 files in {bhs.V10_DIR} (set KNA_HEARINGS_V10_DIR)")
    meetings, turns, _ = bhs.load_v10(bhs.V10_DIR)
    built = bhs.summarize_v10(meetings, turns)[bhs.V10_COLUMNS]
    pd.testing.assert_frame_equal(built, shipped)


def test_v9_reproduces_shipped_summary(kdata):
    shipped = kdata.parquet("hearing_meetings_summary.parquet")
    if "conf_num" in shipped.columns:
        pytest.skip("the shipped table is built from v10 since 0.8.1")
    src = bhs.V9_DIR / bhs.V9_FILE
    if not src.exists():
        pytest.skip(f"{bhs.V9_FILE} not in {bhs.V9_DIR} (set KNA_HEARINGS_DIR)")
    built = bhs.summarize_v9(src)
    pd.testing.assert_frame_equal(built, shipped)


MEETINGS = pd.DataFrame({
    "conf_num": [3, 1, 2, 4],
    "conf_id": ["050003", "050001", "050002", None],
    "v9_meeting_id": ["050003", "050001", None, None],
    "term": pd.Series([21, 21, 21, 21], dtype="int16"),
    "hearing_type": ["국정감사", "상임위원회", "특별위원회", "상임위원회"],
    "committee_raw": ["행정안전위원회", "법제사법위원회", "윤리특별위원회", "법제사법위원회"],
    "date": ["2020-10-07", "2020-06-16", "2020-07-01", "2020-06-17"],
    "is_subcommittee": [False, False, False, True],
    "is_confirmation_hearing": [False, True, False, False],
    "audit_team": ["제1반", None, None, None],
})
TURNS = pd.DataFrame({
    "conf_num": [1, 1, 1, 1, 1, 3, 3, 4],
    "naas_cd": ["AAAAAAA1", "AAAAAAA1", "BBBBBBB2", None, "DDDDDDD4", "", "CCCCCCC3", "AAAAAAA1"],
    "party": ["더불어민주당", "더불어민주당", "국민의힘", None, None, "", "정의당", "더불어민주당"],
    # DDDDDDD4 holds a seat but speaks as minister, so it is no legislator here
    "role_group": ["legislator", "legislator", "legislator", "nonlegislator", "nonlegislator",
                   "legislator", "legislator", "legislator"],
})


def _write_build(root):
    (root / "turns" / "t21").mkdir(parents=True)
    MEETINGS.to_parquet(root / "meetings.parquet", index=False)
    TURNS.to_parquet(root / "turns" / "t21" / "part-00000.parquet", index=False)
    (root / "MANIFEST.json").write_text(json.dumps({"run": {"run_id": "RUN1"}}), encoding="utf-8")


def _write_assets(root, version="v10.1"):
    root.mkdir(parents=True, exist_ok=True)
    MEETINGS.to_parquet(root / f"meetings_{version}.parquet", index=False)
    for t in bhs.V10_TERMS:
        part = TURNS if t == 21 else TURNS.iloc[0:0]
        part.to_parquet(root / f"turns_t{t}_{version}.parquet", index=False)
    (root / f"MANIFEST_{version}.json").write_text(json.dumps({"run": {"run_id": "RUN1"}}),
                                                   encoding="utf-8")


def _check(got):
    assert got[bhs.V10_COLUMNS].dtypes.astype(str).to_dict() == DTYPES
    # Meeting 2 has no turn and is left out. Meeting 4 has no conf_id and keeps
    # a null meeting_id, sorted last
    assert got["conf_num"].tolist() == [1, 3, 4]
    assert got["meeting_id"].tolist()[:2] == ["050001", "050003"] and pd.isna(got["meeting_id"].iloc[2])
    one = got.set_index("conf_num").loc[1]
    assert (one["n_speeches"], one["n_legislators"], one["parties"]) == (5, 2, "국민의힘,더불어민주당")
    three = got.set_index("conf_num").loc[3]
    # The audit team is appended, and an empty code or party does not count
    assert three["committee"] == "행정안전위원회-제1반"
    assert (three["n_legislators"], three["parties"]) == (1, "정의당")
    assert got.set_index("conf_num").loc[4, "is_subcommittee"]
    # A confirmation hearing held by a standing committee
    assert got.set_index("conf_num").loc[1, "is_confirmation_hearing"]


def test_v10_build_layout(tmp_path):
    _write_build(tmp_path)
    assert bhs.v10_layout(tmp_path) == ("build", None)
    meetings, turns, info = bhs.load_v10(tmp_path)
    assert info["run_id"] == "RUN1"
    got = bhs.summarize_v10(meetings, turns)
    _check(got)

    ref = got[bhs.COLUMNS].dropna(subset=["meeting_id"]).copy()
    ref.loc[ref.index[0], "n_speeches"] = 6
    res = bhs.compare(got, ref, key="v9_meeting_id")
    assert res["matched"] == 2 and res["mismatch"]["n_speeches"] == 1
    assert sum(v for k, v in res["mismatch"].items() if k != "n_speeches") == 0


def test_v10_asset_layout(tmp_path):
    _write_assets(tmp_path)
    assert bhs.v10_layout(tmp_path) == ("assets", "v10.1")
    meetings, turns, info = bhs.load_v10(tmp_path)
    assert (info["layout"], info["version"], info["run_id"]) == ("assets", "v10.1", "RUN1")
    _check(bhs.summarize_v10(meetings, turns))


def test_v10_asset_layout_with_two_versions(tmp_path):
    _write_assets(tmp_path, "v10")
    _write_assets(tmp_path, "v10.1")
    with pytest.raises(SystemExit):
        bhs.v10_layout(tmp_path)
    assert bhs.v10_layout(tmp_path, "v10") == ("assets", "v10")


def test_v10_rejects_repeated_keys():
    m = MEETINGS.copy()
    m.loc[1, "conf_id"] = "050003"
    with pytest.raises(SystemExit):
        bhs.summarize_v10(m, TURNS)
    m = MEETINGS.copy()
    m.loc[1, "conf_num"] = 3
    with pytest.raises(SystemExit):
        bhs.summarize_v10(m, TURNS)


def test_compare_with_a_repeated_key():
    ref = pd.DataFrame({"meeting_id": ["1", "2"], "term": pd.array([21, 21], dtype="Int64"),
                        "committee": ["법제사법위원회"] * 2, "hearing_type": ["상임위원회"] * 2,
                        "date": ["2020-06-16"] * 2, "n_speeches": [3, 4],
                        "n_legislators": [1, 2], "parties": ["", ""]})
    # Two v10 meetings that name the same v9 meeting
    new = pd.concat([ref.assign(v9_meeting_id=ref["meeting_id"]),
                     ref.iloc[[0]].assign(meeting_id="3", v9_meeting_id="1", n_speeches=9)],
                    ignore_index=True)
    res = bhs.compare(new, ref, key="v9_meeting_id")
    assert (res["matched"], res["only_new"], res["only_ref"]) == (2, 1, 0)
    assert sum(res["mismatch"].values()) == 0
