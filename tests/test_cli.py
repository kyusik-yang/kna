"""Run the documented CLI commands through click's CliRunner.

The commands are read from the README "CLI Usage" block and from the
"Examples:" section of every command's help, so the tests follow the docs.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys

import click
import pytest
from click.testing import CliRunner

from conftest import REPO
from kna.cli import cli


def _readme_commands() -> list[list[str]]:
    readme = REPO / "README.md"
    if not readme.exists():
        return []
    text = readme.read_text(encoding="utf-8")
    m = re.search(r"## CLI Usage\s*```bash\n(.*?)```", text, re.S)
    if not m:
        return []
    return [shlex.split(line.strip())[1:] for line in m.group(1).splitlines()
            if line.strip().startswith("kna ")]


def _docstring_commands() -> list[list[str]]:
    cmds = []

    def walk(group: click.Group):
        for c in group.commands.values():
            if isinstance(c, click.Group):
                walk(c)
            for line in (c.help or "").splitlines():
                if line.strip().startswith("kna "):
                    cmds.append(shlex.split(line.strip())[1:])

    walk(cli)
    return cmds


README_COMMANDS = _readme_commands()
DOC_COMMANDS = _docstring_commands()


def _run(args, tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        return runner.invoke(cli, args, catch_exceptions=True)


def _ok(result, args):
    assert result.exit_code == 0, (
        f"kna {' '.join(args)} exited {result.exit_code}\n{result.output}\n{result.exception!r}")


def test_readme_block_found():
    if not (REPO / "README.md").exists():
        pytest.skip("README.md not found")
    assert README_COMMANDS, "no kna commands found in the README 'CLI Usage' block"


@pytest.mark.parametrize("args", README_COMMANDS, ids=[" ".join(a) for a in README_COMMANDS])
def test_readme_command(data_dir, tmp_path, args):
    _ok(_run(args, tmp_path), args)


@pytest.mark.parametrize("args", DOC_COMMANDS, ids=[" ".join(a) for a in DOC_COMMANDS])
def test_docstring_example(data_dir, tmp_path, args):
    _ok(_run(args, tmp_path), args)


@pytest.mark.parametrize("age", [17, 18, 19, 20, 21, 22])
def test_funnel_every_assembly(data_dir, tmp_path, age):
    _ok(_run(["stats", "funnel", "--assembly", str(age)], tmp_path), age)


@pytest.mark.parametrize("status", ["expired", "reflected", "rejected", "pending"])
def test_status_groups(data_dir, tmp_path, status):
    args = ["search", "법", "--assembly", "21", "--status", status, "-n", "3"]
    _ok(_run(args, tmp_path), args)


def test_same_name_lists_candidates(data_dir, tmp_path):
    from kna.data import BillDB
    mem = BillDB(data_dir).members(assembly=21)
    ids = sorted(mem.loc[mem["member_name"] == "김병욱", "mona_cd"])
    if len(ids) < 2:
        pytest.skip("김병욱 is not a same-name pair in members_21")
    r = _run(["legislator", "김병욱", "--assembly", "21"], tmp_path)
    assert r.exit_code == 2, r.output
    for mona in ids:
        assert mona in r.output
    r = _run(["legislator", "김병욱", "--assembly", "21", "--mona", ids[0]], tmp_path)
    _ok(r, ids[0])
    assert ids[0] in r.output and ids[1] not in r.output


def test_legislator_shows_own_district(data_dir, tmp_path):
    from kna.data import BillDB
    mem = BillDB(data_dir).members(assembly=22)
    kim, other = mem[mem["member_name"] == "김현"], mem[mem["member_name"] == "김현정"]
    if len(kim) != 1 or other.empty:
        pytest.skip("김현/김현정 not both in members_22")
    r = _run(["legislator", "김현", "--assembly", "22"], tmp_path)
    _ok(r, "김현")
    assert kim["district"].iloc[0] in r.output
    assert other["district"].iloc[0] not in r.output


def test_legislator_without_bills_still_profiled(data_dir, tmp_path):
    # The Speaker leads no bills; the profile must still print
    r = _run(["legislator", "우원식", "--assembly", "22"], tmp_path)
    _ok(r, "우원식")
    assert "led" in r.output


def test_bad_input_is_a_usage_error(data_dir, tmp_path):
    for args in (["stats", "funnel", "--assembly", "16"],
                 ["search", "법", "--assembly", "23"],
                 ["export", "x.xlsx", "--assembly", "22"]):
        r = _run(args, tmp_path)
        assert r.exit_code == 2, f"kna {' '.join(args)}: {r.exit_code}\n{r.output}"


def test_version_and_module_entry():
    r = CliRunner().invoke(cli, ["--version"])
    assert r.exit_code == 0 and re.search(r"\d+\.\d+\.\d+", r.output)
    for module in ("kna.cli", "kna"):
        out = subprocess.run([sys.executable, "-m", module, "--version"], cwd=REPO,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0 and out.stdout.strip(), f"python -m {module}: {out.stderr}"
