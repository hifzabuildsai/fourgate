"""Real subprocess acceptance checks for the contracted scan path."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fourgate.scan import load_contract

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "fixtures" / "contracts" / "scan_demo.json"


def _contract(tmp_path, *, server_command=None, case_tool="create_issue"):
    data = json.loads(DEMO.read_text(encoding="utf-8"))
    data["server"]["command"] = server_command or [sys.executable, str(ROOT / "fixtures" / "outcome_server.py")]
    data["cases"][0]["tool"] = case_tool
    verifier = data["cases"][0]["outcome_contract"]["verifier"]
    verifier["command"] = [sys.executable, str(ROOT / "fixtures" / "outcome_verifier.py")]
    verifier.pop("cwd")
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run(path, store, *, mode="broken", verifier="normal", confirmation="disposable-demo"):
    env = os.environ.copy()
    env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE=mode,
               FOURGATE_DEMO_VERIFIER=verifier)
    return subprocess.run([sys.executable, "-m", "fourgate", "scan", str(path),
                           "--confirm-test-account", confirmation], cwd=ROOT, env=env,
                          text=True, capture_output=True, timeout=12)


def test_real_scan_distinguishes_persisted_from_false_success(tmp_path):
    contract = _contract(tmp_path)
    broken = _run(contract, tmp_path / "broken.json")
    assert broken.returncode == 1
    assert json.loads(broken.stdout)["cases"] == [
        {"tool": "create_issue", "status": "FAIL", "reason_code": "record_missing", "attempts": 1}]
    healthy_store = tmp_path / "healthy.json"
    healthy = _run(contract, healthy_store, mode="healthy")
    assert healthy.returncode == 0
    assert json.loads(healthy.stdout)["cases"][0]["status"] == "PASS"
    assert json.loads(healthy_store.read_text())[0]["title"] == "FOURGATE-SCAN-TEST"


def test_verifier_timeout_is_unknown_never_pass(tmp_path):
    report = _run(_contract(tmp_path), tmp_path / "store.json", verifier="hang")
    assert report.returncode == 1
    assert json.loads(report.stdout)["cases"][0] == {
        "tool": "create_issue", "status": "UNKNOWN", "reason_code": "verifier_timeout", "attempts": 1}


def test_test_account_gate_rejects_before_spawning(tmp_path):
    marker = tmp_path / "spawned"
    program = tmp_path / "marker.py"
    program.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('spawned')\n")
    contract = _contract(tmp_path, server_command=[sys.executable, str(program)])
    report = _run(contract, tmp_path / "store.json", confirmation="production")
    assert report.returncode == 2
    assert not marker.exists()
    assert report.stdout == ""


def test_unlisted_tool_is_rejected_before_spawning(tmp_path):
    contract = _contract(tmp_path, case_tool="dangerous_write")
    with pytest.raises(ValueError, match="allowed write tool"):
        load_contract(contract, "disposable-demo")


def test_duplicate_or_non_string_allowlist_rejected(tmp_path):
    contract = _contract(tmp_path)
    data = json.loads(contract.read_text())
    for tools in (["create_issue", "create_issue"], [{"name": "create_issue"}]):
        data["write_tools"] = tools
        contract.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="write_tools"):
            load_contract(contract, "disposable-demo")
