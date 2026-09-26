"""hearing_meetings_summary.parquet and build_hearings_summary.py.

The v9 check rebuilds the table from the kr-hearings-data v9 speech corpus,
read from KNA_HEARINGS_DIR (default ../kr-hearings-data/data), and skips
when the corpus is missing. It reads 9.9 million speech rows and takes about
a minute and a half. The v10 check runs on a small synthetic build in the
v10 release layout.
"""

from __future__ import annotations

import pandas as pd
import pytest

import build_hearings_summary as bhs

DTYPES = {"meeting_id": "object", "term": "Int64", "committee": "object",
          "hearing_type": "object", "date": "object", "n_speeches": "int64",
          "n_legislators": "int64", "parties": "object"}


def test_v9_reproduces_shipped_summary(kdata):
    shipped = kdata.parquet("hearing_meetings_summary.parquet")
    src = bhs.V9_DIR / bhs.V9_FILE
    if not src.exists():
        pytest.skip(f"{bhs.V9_FILE} not in {bhs.V9_DIR} (set KNA_HEARINGS_DIR)")
    built = bhs.summarize_v9(src)
    pd.testing.assert_frame_equal(built, shipped)


def _write_v10(root, meetings: pd.DataFrame, turns: pd.DataFrame):
    (root / "turns" / "t21").mkdir(parents=True)
    meetings.to_parquet(root / "meetings.parquet", index=False)
    turns.to_parquet(root / "turns" / "t21" / "part-00000.parquet", index=False)


def test_v10_layout_gives_the_v9_schema(tmp_path):
    meetings = pd.DataFrame({
        "conf_num": [3, 1, 2],
        "conf_id": ["050003", "050001", "050002"],
        "v9_meeting_id": ["050003", "050001", None],
        "term": pd.Series([21, 21, 21], dtype="int16"),
        "hearing_type": ["국정감사", "상임위원회", "특별위원회"],
        "committee_raw": ["행정안전위원회", "법제사법위원회", "윤리특별위원회"],
        "date": ["2020-10-07", "2020-06-16", "2020-07-01"],
        "audit_team": ["제1반", None, None],
    })
    turns = pd.DataFrame({
        "conf_num": [1, 1, 1, 1, 3, 3],
        "naas_cd": ["AAAAAAA1", "AAAAAAA1", "BBBBBBB2", None, "", "CCCCCCC3"],
        "party": ["더불어민주당", "더불어민주당", "국민의힘", None, "", "정의당"],
    })
    _write_v10(tmp_path, meetings, turns)

    got = bhs.summarize_v10(tmp_path)
    assert got[bhs.COLUMNS].dtypes.astype(str).to_dict() == DTYPES
    # Meeting 2 has no turn and is left out
    assert got["meeting_id"].tolist() == ["050001", "050003"]
    one = got.set_index("meeting_id").loc["050001"]
    assert (one["n_speeches"], one["n_legislators"], one["parties"]) == (4, 2, "국민의힘,더불어민주당")
    three = got.set_index("meeting_id").loc["050003"]
    # The audit team is appended, and an empty code or party does not count
    assert three["committee"] == "행정안전위원회-제1반"
    assert (three["n_legislators"], three["parties"]) == (1, "정의당")

    ref = got[bhs.COLUMNS].copy()
    ref.loc[0, "n_speeches"] = 5
    res = bhs.compare(got, ref, key="v9_meeting_id")
    assert res["matched"] == 2 and res["mismatch"]["n_speeches"] == 1
    assert sum(v for k, v in res["mismatch"].items() if k != "n_speeches") == 0
