"""Live scans must refuse unreplaced template markers."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fourgate import scan

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "examples" / "github-issue"
DEMO = ROOT / "fixtures" / "contracts" / "scan_demo.json"


def _configured_github(tmp_path):
    data = json.loads((PACK / "scan.example.json").read_text(encoding="utf-8"))
    data["server"]["command"] = [sys.executable, "-c", "pass"]
    data["cases"][0]["arguments"].update(
        owner="acme-test", repo="disposable", title="Configured title",
        body="Configured body")
    data["cases"][0]["readback"]["repository"] = "acme-test/disposable"
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def test_github_template_loads_but_scan_refuses_placeholders():
    data = scan.load_contract(PACK / "scan.example.json", "disposable-github-issue")
    with pytest.raises(ValueError, match="template placeholders"):
        scan.assert_ready_to_execute(data)


def test_fixture_github_example_refuses_placeholders():
    data = scan.load_contract(
        ROOT / "fixtures" / "contracts" / "scan_github_issue.example.json",
        "disposable-github-repository")
    with pytest.raises(ValueError, match="template placeholders"):
        scan.assert_ready_to_execute(data)


def test_configured_contract_is_ready(tmp_path):
    _, data = _configured_github(tmp_path)
    scan.assert_ready_to_execute(data)


def test_cli_scan_exits_2_on_placeholders(tmp_path):
    raw = json.loads((PACK / "scan.example.json").read_text(encoding="utf-8"))
    # Keep REPLACE markers; give a command that would otherwise be spawnable.
    raw["server"]["command"] = [sys.executable, "-c", "pass"]
    path = tmp_path / "unfinished.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "fourgate", "scan", str(path),
         "--confirm-test-account", "disposable-github-issue"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 2
    assert "template placeholders" in completed.stderr


def test_demo_fixture_still_scans(tmp_path):
    store = tmp_path / "issues.json"
    env = os.environ.copy()
    env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE="broken",
               PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run(
        [sys.executable, "-m", "fourgate", "scan", str(DEMO),
         "--confirm-test-account", "disposable-demo",
         "--report-dir", str(tmp_path / "out")],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["cases"][0]["status"] == "FAIL"
