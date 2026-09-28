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
    broken_row = json.loads(broken.stdout)["cases"][0]
    assert (broken_row["tool"], broken_row["status"], broken_row["reason_code"], broken_row["attempts"]) == (
        "create_issue", "FAIL", "record_missing", 1)
    assert broken_row["evidence"]["request"]["params"]["name"] == "create_issue"
    assert broken_row["evidence"]["tool_response"]["result"]["structuredContent"]["issue_id"] == "ISSUE-001"
    assert broken_row["evidence"]["readback"] == {"lookup": {"issue_id": "ISSUE-001", "record": None}}
    healthy_store = tmp_path / "healthy.json"
    healthy = _run(contract, healthy_store, mode="healthy")
    assert healthy.returncode == 0
    assert json.loads(healthy.stdout)["cases"][0]["status"] == "PASS"
    assert json.loads(healthy_store.read_text())[0]["title"] == "FOURGATE-SCAN-TEST"


def test_verifier_timeout_is_unknown_never_pass(tmp_path):
    report = _run(_contract(tmp_path), tmp_path / "store.json", verifier="hang")
    assert report.returncode == 1
    row = json.loads(report.stdout)["cases"][0]
    assert (row["tool"], row["status"], row["reason_code"]) == (
        "create_issue", "UNKNOWN", "verifier_timeout")


def test_success_without_record_id_is_fail_without_readback(tmp_path):
    report = _run(_contract(tmp_path), tmp_path / "store.json", mode="no_record_id")
    assert report.returncode == 1
    row = json.loads(report.stdout)["cases"][0]
    assert (row["status"], row["reason_code"], row["attempts"]) == (
        "FAIL", "success_without_record_id", 0)
    assert row["evidence"]["tool_response"]["result"]["structuredContent"] == {}
    assert row["evidence"]["readback"] == {"reason_code": "readback_not_run_without_record_id"}


def test_record_id_selector_must_reference_result(tmp_path):
    contract = _contract(tmp_path)
    data = json.loads(contract.read_text())
    data["cases"][0]["outcome_contract"]["record_id_field"] = "title"
    contract.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="record_id_field"):
        load_contract(contract, "disposable-demo")


def test_malformed_authoritative_store_is_unknown(tmp_path):
    store = tmp_path / "malformed.json"
    store.write_text("not-json", encoding="utf-8")
    report = _run(_contract(tmp_path), store)
    assert report.returncode == 1
    row = json.loads(report.stdout)["cases"][0]
    assert row["status"] == "UNKNOWN" and row["reason_code"] == "verifier_error"


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


def test_cli_writes_both_redacted_report_formats(tmp_path):
    contract = _contract(tmp_path)
    reports = tmp_path / "reports"
    env = os.environ.copy()
    env.update(FOURGATE_DEMO_STORE=str(tmp_path / "store.json"), FOURGATE_DEMO_MODE="broken",
               FOURGATE_TEST_SECRET="SENSITIVE-SECRET-VALUE-123456")
    process = subprocess.run([sys.executable, "-m", "fourgate", "scan", str(contract),
                              "--confirm-test-account", "disposable-demo", "--report-dir", str(reports)],
                             cwd=ROOT, env=env, capture_output=True, text=True, timeout=12)
    assert process.returncode == 1
    report = json.loads((reports / "fourgate-report.json").read_text())
    assert report["cases"][0]["status"] == "FAIL"
    assert report["cases"][0]["evidence"]["request"]["params"]["arguments"]["title"] == "FOURGATE-SCAN-TEST"
    assert report["cases"][0]["evidence"]["tool_response"]["result"]["content"]
    assert "repro_steps" in report["cases"][0]
    assert (reports / "fourgate-report.html").read_text().startswith("<!doctype html>")
