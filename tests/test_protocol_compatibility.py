"""Spec-pinned local controls; these are not natural silent-success findings."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODERN = "2026-07-28"
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"


def setup(tmp_path, era, protocol, control="healthy", cases=1):
    trace, store = tmp_path / "trace.jsonl", tmp_path / "store.json"
    command = [sys.executable, str(ROOT / "fixtures/protocol_server.py"), "--era", era,
               "--trace", str(trace), "--store", str(store), "--control", control]
    contract = json.loads((ROOT / "fixtures/contracts/scan_demo.json").read_text(encoding="utf-8"))
    contract["server"].update(command=command, protocol_version=protocol)
    verifier = contract["cases"][0]["outcome_contract"]["verifier"]
    verifier.update(command=[sys.executable, str(ROOT / "fixtures/outcome_verifier.py")])
    verifier.pop("cwd")
    contract["cases"] *= cases
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    return path, trace, store, command


def run_scan(path, store):
    return subprocess.run([sys.executable, "-m", "fourgate", "scan", str(path),
                           "--confirm-test-account", "disposable-demo"], cwd=ROOT,
                          env={**os.environ, "FOURGATE_DEMO_STORE": str(store)},
                          text=True, capture_output=True, timeout=15)


def messages(trace):
    return [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("era,protocol", [("legacy", "2024-11-05"), ("legacy", "2025-11-25"),
                                         ("compat", "2024-11-05"), ("native", MODERN), ("compat", MODERN)])
def test_scan_uses_selected_lifecycle_and_authoritative_verifier(tmp_path, era, protocol):
    path, trace, store, _ = setup(tmp_path, era, protocol)
    result = run_scan(path, store)
    assert result.returncode == 0, result.stderr or result.stdout
    row = json.loads(result.stdout)["cases"][0]
    assert (row["status"], row["reason_code"]) == ("PASS", "postcondition_satisfied")
    assert json.loads(store.read_text())[0]["title"] == "FOURGATE-SCAN-TEST"
    observed = messages(trace)
    if protocol == MODERN:
        assert [m["method"] for m in observed] == ["server/discover", "tools/list", "tools/call"]
        assert all(m["params"]["_meta"][VERSION_KEY] == MODERN for m in observed)
        assert all(m["params"]["_meta"][CAPABILITIES_KEY] == {} for m in observed)
    else:
        assert [m["method"] for m in observed] == [
            "initialize", "notifications/initialized", "tools/list", "tools/call"]


@pytest.mark.parametrize("control,expected", [("missing", ("FAIL", "record_missing")),
                                             ("input_required", ("UNKNOWN", "incomplete_tool_result")),
                                             ("unknown_type", ("UNKNOWN", "unsupported_result_type")),
                                             ("missing_result_type", ("UNKNOWN", "missing_result_type"))])
def test_modern_call_controls_never_retry_write(tmp_path, control, expected):
    path, trace, store, _ = setup(tmp_path, "native", MODERN, control, cases=2)
    verifier_marker = tmp_path / "verifier-ran"
    if control != "missing":
        verifier = tmp_path / "marker_verifier.py"
        verifier.write_text(f"from pathlib import Path\nPath({str(verifier_marker)!r}).touch()\n"
                            "print('{\"status\":\"pass\"}')\n", encoding="utf-8")
        data = json.loads(path.read_text(encoding="utf-8"))
        for case in data["cases"]:
            case["outcome_contract"]["verifier"]["command"] = [sys.executable, str(verifier)]
        path.write_text(json.dumps(data), encoding="utf-8")
    result = run_scan(path, store)
    assert result.returncode == 1, result.stderr
    rows = json.loads(result.stdout)["cases"]
    assert (rows[0]["status"], rows[0]["reason_code"]) == expected
    calls = [m for m in messages(trace) if m["method"] == "tools/call"]
    if control == "missing":
        assert len(calls) == 2  # distinct, explicitly contracted cases; neither retried
    else:
        assert len(rows) == len(calls) == 1
        assert rows[0]["attempts"] == 0
        assert "tool_response" in rows[0]["evidence"]
        assert not verifier_marker.exists()
    if control != "missing_result_type":
        assert not store.exists()
    else:
        assert store.exists()  # persisted state alone must not bypass the protocol completion gate


@pytest.mark.parametrize("control", ["unsupported_version", "discovery_input_required", "discovery_missing_type",
                                    "wrong_versions", "list_missing_type"])
def test_modern_discovery_blocker_has_no_legacy_fallback_or_write(tmp_path, control):
    path, trace, store, _ = setup(tmp_path, "compat", MODERN, control)
    result = run_scan(path, store)
    assert result.returncode == 1, result.stderr
    row = json.loads(result.stdout)["cases"][0]
    assert row["status"] == "UNKNOWN" and row["tool"] is None
    expected = ["server/discover", "tools/list"] if control == "list_missing_type" else ["server/discover"]
    assert [m["method"] for m in messages(trace)] == expected
    assert not store.exists()


@pytest.mark.parametrize("era", ["native", "compat"])
def test_doctor_modern_discovery_only_is_readiness_not_an_outcome(tmp_path, era):
    _, trace, store, command = setup(tmp_path, era, MODERN)
    result = subprocess.run([sys.executable, "-m", "fourgate", "doctor", "--contracts",
                             str(ROOT / "fixtures/contracts/outcome_demo.json"),
                             "--protocol-version", MODERN, "--", *command],
                            cwd=ROOT, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr or result.stdout
    assert "Verdict: READY FOR SHADOW" in result.stdout
    assert "server/discover and tools/list answered" in result.stdout
    assert [m["method"] for m in messages(trace)] == ["server/discover", "tools/list"]
    assert not store.exists()


def test_doctor_legacy_mode_on_native_server_is_not_ready_without_write(tmp_path):
    _, trace, store, command = setup(tmp_path, "native", MODERN)
    result = subprocess.run([sys.executable, "-m", "fourgate", "doctor", "--contracts",
                             str(ROOT / "fixtures/contracts/outcome_demo.json"), "--", *command],
                            cwd=ROOT, text=True, capture_output=True, timeout=15)
    assert result.returncode == 1
    assert "Verdict: NOT READY" in result.stdout
    assert [m["method"] for m in messages(trace)] == ["initialize"]
    assert not store.exists()


def test_modern_stdio_shutdown_allows_eof_exit(tmp_path):
    from fourgate.scan import StdioClient

    _, _, store, command = setup(tmp_path, "native", MODERN)
    client = StdioClient(command, None, os.environ.copy())
    try:
        assert client.initialize(MODERN) == {"create_issue"}
    finally:
        client.close()
    assert client.proc.returncode == 0
    assert not store.exists()
