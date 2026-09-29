"""HTTP read-back tests use a local server, never an external account."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fourgate import readback

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "fixtures" / "contracts" / "scan_demo.json"


def _run(tmp_path, mode, status, delayed=0, token_env=None, server_command=None, token_value=None,
         without_record_id=False, subject_values=None, report_dir=None):
    store = tmp_path / "store.json"
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            code = 404 if len(calls) <= delayed else status
            if code == 200:
                document = {"title": "FOURGATE-SCAN-TEST"}
                if subject_values:
                    document["subject"] = subject_values[1]
                body = json.dumps(document).encode()
            else:
                body = b"{}"
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        contract = json.loads(DEMO.read_text())
        contract["server"]["command"] = server_command or [sys.executable, str(ROOT / "fixtures" / "outcome_server.py")]
        case = contract["cases"][0]
        case["outcome_contract"] = {"extract": case["outcome_contract"]["extract"],
                                    "record_id_field": "issue_id"}
        case["readback"] = {
            "type": "http", "url_template": f"http://127.0.0.1:{httpd.server_port}/issues/{{issue_id}}",
            "expected_fields": {"title": "title"}, "missing_statuses": [404],
            "attempts": 3, "interval_ms": 10, "timeout_ms": 1000,
        }
        if subject_values:
            case["arguments"]["subject"] = subject_values[0]
            case["outcome_contract"]["extract"]["subject"] = {"source": "arguments", "path": "subject"}
            case["readback"]["expected_fields"] = {"subject": "subject"}
        if without_record_id:
            case["outcome_contract"].pop("record_id_field")
            case["outcome_contract"]["extract"].pop("issue_id")
            case["readback"]["url_template"] = f"http://127.0.0.1:{httpd.server_port}/issues/test-record"
        if token_env:
            case["readback"]["token_env"] = token_env
        contract_path = tmp_path / "scan.json"
        contract_path.write_text(json.dumps(contract))
        env = os.environ.copy()
        env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE=mode)
        if token_env and token_value:
            env[token_env] = token_value
        env["FOURGATE_WRITE_TEST_TOKEN"] = "write-token-supplied-to-server"
        command = [sys.executable, "-m", "fourgate", "scan", str(contract_path),
                   "--confirm-test-account", "disposable-demo"]
        if report_dir:
            command.extend(["--report-dir", str(report_dir)])
        result = subprocess.run(command, cwd=ROOT, env=env,
                                text=True, capture_output=True, timeout=12)
        return result, json.loads(result.stdout)["cases"][0], calls
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_delayed_visibility_retries_to_pass(tmp_path):
    result, row, calls = _run(tmp_path, "healthy", 200, delayed=2)
    assert result.returncode == 0
    assert row["status"] == "PASS" and row["attempts"] == 3
    assert calls == ["/issues/ISSUE-001"] * 3


def test_confirmed_missing_after_retries(tmp_path):
    result, row, calls = _run(tmp_path, "broken", 404)
    assert result.returncode == 1
    assert row["status"] == "FAIL" and row["reason_code"] == "record_missing"
    assert row["attempts"] == len(calls) == 3


def test_subject_mismatch_details_reach_json_and_html_reports(tmp_path):
    reports = tmp_path / "reports"
    result, row, calls = _run(tmp_path, "healthy", 200, subject_values=("Expected subject", "Observed subject"),
                              report_dir=reports)
    assert result.returncode == 1
    assert (row["status"], row["reason_code"], row["attempts"]) == ("FAIL", "field_mismatch", 3)
    assert row["checked_fields"] == ["subject"]
    assert row["mismatched_fields"] == [{"path": "subject", "expected": "Expected subject",
                                         "observed": "Observed subject"}]
    assert calls == ["/issues/ISSUE-001"] * 3
    on_disk = json.loads((reports / "fourgate-report.json").read_text())["cases"][0]
    assert on_disk["checked_fields"] == row["checked_fields"]
    assert on_disk["mismatched_fields"] == row["mismatched_fields"]
    page = (reports / "fourgate-report.html").read_text()
    assert all(value in page for value in ("checked_fields", "mismatched_fields",
                                        "Expected subject", "Observed subject"))


def test_subject_mismatch_details_use_report_redaction(tmp_path):
    secret = "sk_test_" + "x" * 24
    reports = tmp_path / "reports"
    result, row, _ = _run(tmp_path, "healthy", 200, subject_values=(secret, "Bearer " + secret),
                          report_dir=reports)
    assert result.returncode == 1 and row["status"] == "FAIL"
    assert row["mismatched_fields"] == [{"path": "subject", "expected": "[REDACTED]",
                                         "observed": "[REDACTED]"}]
    assert secret not in (reports / "fourgate-report.json").read_text()
    assert secret not in (reports / "fourgate-report.html").read_text()


def test_auth_failure_is_unknown(tmp_path):
    result, row, _ = _run(tmp_path, "broken", 401)
    assert result.returncode == 1
    assert row["status"] == "UNKNOWN"


def test_success_without_record_id_is_unknown_and_skips_http_readback(tmp_path):
    result, row, calls = _run(tmp_path, "no_record_id", 200)
    assert result.returncode == 1
    assert (row["status"], row["reason_code"], row["attempts"]) == (
        "UNKNOWN", "success_without_record_id", 0)
    assert calls == []


def test_without_record_id_field_runs_static_readback(tmp_path):
    result, row, calls = _run(tmp_path, "no_record_id", 200, without_record_id=True)
    assert result.returncode == 0
    assert row["status"] == "PASS" and row["attempts"] == 1
    assert calls == ["/issues/test-record"]


def test_missing_token_never_sends_request(tmp_path):
    result, row, calls = _run(tmp_path, "healthy", 200, token_env="FOURGATE_NOT_SET_TEST_TOKEN")
    assert result.returncode == 1
    assert row["status"] == "UNKNOWN" and row["reason_code"] == "credential_missing"
    assert calls == []
    assert not (tmp_path / "store.json").exists(), "missing verifier credentials must skip the write"


def test_read_token_not_inherited_by_mcp_server(tmp_path):
    marker = tmp_path / "child_env.json"
    probe = tmp_path / "probe.py"
    probe.write_text("import json, os, runpy, sys\n"
                     "from pathlib import Path\n"
                     f"Path({str(marker)!r}).write_text(json.dumps({{'read': 'FOURGATE_READ_TEST_TOKEN' in os.environ, "
                     "'write': 'FOURGATE_WRITE_TEST_TOKEN' in os.environ}))\n"
                     "runpy.run_path(sys.argv[1], run_name='__main__')\n")
    command = [sys.executable, str(probe), str(ROOT / "fixtures" / "outcome_server.py")]
    result, row, _ = _run(tmp_path, "healthy", 200, token_env="FOURGATE_READ_TEST_TOKEN",
                          server_command=command, token_value="read-only-secret-token")
    assert result.returncode == 0 and row["status"] == "PASS"
    assert json.loads(marker.read_text()) == {"read": False, "write": True}


def test_github_issue_url_and_404_default_uncertain(monkeypatch):
    config = {"type": "github_issue", "repository": "example/disposable", "issue_number_field": "number",
              "token_env": "FOURGATE_GITHUB_TEST", "expected_fields": {"title": "title"},
              "attempts": 1, "timeout_ms": 500}
    extract = {"number": {"source": "result", "path": "result.structuredContent.number"},
               "title": {"source": "arguments", "path": "title"}}
    readback.validate(config, extract)
    urls = []

    def fake_get(url, token, timeout):
        urls.append((url, token))
        return 404, None

    monkeypatch.setattr(readback, "_get", fake_get)
    monkeypatch.setenv("FOURGATE_GITHUB_TEST", "local-test-token")
    result = readback.evaluate(config, {"extract": extract}, {"title": "test"},
                               {"result": {"structuredContent": {"number": 42}}})
    assert result["status"] == "unknown"
    assert urls == [("https://api.github.com/repos/example/disposable/issues/42", "local-test-token")]


def test_dynamic_host_and_non_https_rejected():
    extract = {"issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
               "title": {"source": "arguments", "path": "title"}}
    for template in ("https://{issue_id}/issue", "http://example.com/issues/{issue_id}"):
        config = {"type": "http", "url_template": template, "expected_fields": {"title": "title"}}
        try:
            readback.validate(config, extract)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe URL was accepted: {template}")
