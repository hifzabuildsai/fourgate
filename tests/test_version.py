"""`fourgate --version` and the single source of the package version."""
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

import fourgate
from fourgate import cli, doctor, guard, init
from fourgate.demo import runner

ROOT = Path(__file__).resolve().parent.parent
RUN_TIMEOUT = 60


def test_version_is_0_3_0():
    assert fourgate.__version__ == "0.3.0"


def test_installed_metadata_matches_package_version():
    try:
        installed = importlib.metadata.version("fourgate")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("fourgate is not installed")
    assert installed == fourgate.__version__


def test_version_flag_prints_name_and_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == f"fourgate {fourgate.__version__}\n"
    assert captured.err == ""


def test_version_flag_from_module_entry_point():
    result = subprocess.run([sys.executable, "-m", "fourgate", "--version"], cwd=ROOT,
                            capture_output=True, text=True, timeout=RUN_TIMEOUT)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "fourgate 0.3.0\n"


@pytest.mark.parametrize("command, usage", [
    ("guard", guard.USAGE),
    ("doctor", doctor.USAGE),
    ("demo", runner.USAGE),
    ("init", init.USAGE),
])
def test_subcommands_keep_their_own_parsers(capsys, command, usage):
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith(f"usage: {usage}")
    assert "--version" not in out
