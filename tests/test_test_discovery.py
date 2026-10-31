"""Default developer checks must not collect preserved acceptance evidence."""
import os
from pathlib import Path
import subprocess
import sys


def test_default_collection_preserves_archived_source_snapshots(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text("def test_example():\n    pass\n", encoding="utf-8")
    archive = tmp_path / "fourgate-output" / "previous-source" / "tests"
    archive.mkdir(parents=True)
    evidence = archive / "test_example.py"
    original = b"raise AssertionError('preserved evidence must not be collected')\n"
    evidence.write_bytes(original)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=tmp_path,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/test_example.py::test_example" in result.stdout
    assert "fourgate-output" not in result.stdout
    assert "1 test collected" in result.stdout
    assert evidence.read_bytes() == original
