"""Shared fixtures for the kna tests.

The data directory is the one KBL_DATA points to (falling back to the
package default, data/processed). Every check reads whatever files that
directory holds and skips, with the reason, when an input is missing.

    KBL_DATA=data/_build python3 -m pytest tests -v -rs
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

REPO = Path(__file__).resolve().parent.parent
# Test the package in this checkout, not an installed kna distribution
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

AGES = [17, 18, 19, 20, 21, 22]
VOTE_AGES = [20, 21, 22]


def _data_dir() -> Path:
    env = os.getenv("KBL_DATA")
    if env:
        return Path(env).expanduser().resolve()
    from kna.data import _resolve_data_dir
    return _resolve_data_dir().resolve()


def _raw_dir() -> Path:
    return Path(os.getenv("KNA_RAW_DIR", REPO / "data" / "raw")).expanduser()


def pytest_report_header(config):
    import kna
    return [f"kna package: {Path(kna.__file__).parent} (version {kna.__version__})",
            f"kna data dir: {_data_dir()}",
            f"kna raw dir (committee cap check): {_raw_dir()}"]


class Data:
    """Cached readers over one data directory. Missing files skip the test."""

    def __init__(self, root: Path, raw: Path):
        self.root = root
        self.raw = raw
        self._cache: dict = {}

    def path(self, name: str) -> Path:
        p = self.root / name
        if not p.exists():
            pytest.skip(f"{name} not in {self.root}")
        return p

    def has(self, name: str) -> bool:
        return (self.root / name).exists()

    def parquet(self, name: str, columns=None) -> pd.DataFrame:
        key = (name, tuple(columns) if columns else None)
        if key not in self._cache:
            self._cache[key] = pd.read_parquet(self.path(name), columns=columns)
        return self._cache[key]

    def schema(self, name: str):
        return pq.read_schema(self.path(name))

    def master(self, age: int, columns=None) -> pd.DataFrame:
        return self.parquet(f"master_bills_{age}.parquet", columns)

    def members(self, age: int) -> pd.DataFrame:
        return self.parquet(f"members_{age}.parquet")

    def csv(self, name: str) -> pd.DataFrame:
        if name not in self._cache:
            self._cache[name] = pd.read_csv(self.path(name), dtype={"member_id": str})
        return self._cache[name]


@pytest.fixture(scope="session")
def data_dir() -> Path:
    d = _data_dir()
    if not d.is_dir():
        pytest.skip(f"data directory {d} does not exist")
    # The CLI reads KBL_DATA itself, from inside isolated working
    # directories, so pin it to the absolute path of the directory under test
    os.environ["KBL_DATA"] = str(d)
    return d


@pytest.fixture(scope="session")
def kdata(data_dir) -> Data:
    return Data(data_dir, _raw_dir())
