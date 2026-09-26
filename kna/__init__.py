"""Korean National Assembly CLI (kna)."""

import re
from importlib import metadata
from pathlib import Path


def _version() -> str:
    # A source checkout reports its own pyproject version, not the version of
    # whatever kna distribution happens to be installed.
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        if re.search(r'^name\s*=\s*"kna"', text, re.M):
            m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
            if m:
                return m.group(1)
    try:
        return metadata.version("kna")
    except metadata.PackageNotFoundError:
        return "unknown"


__version__ = _version()

from kna.data import BillDB  # noqa: E402

__all__ = ["BillDB", "__version__"]
