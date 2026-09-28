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


def _run(tmp_path, mode, status, delayed=0, token_env=None, server_command=None, token_value=None):
    store = tmp_path / "store.json"
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            code = 404 if len(calls) <= delayed else status
            if code == 200:
                body = json.dumps({"title": "FOURGATE-SCAN-TEST"}).encode()
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
        case["outcome_contract"] = {"extract": case["outcome_contract"]["extract"]}
        case["readback"] = {
            "type": "http", "url_template": f"http://127.0.0.1:{httpd.server_port}/issues/{{issue_id}}",
            "expected_fields": {"title": "title"}, "missing_statuses": [404],
            "attempts": 3, "interval_ms": 10, "timeout_ms": 1000,
        }
        if token_env:
            case["readback"]["token_env"] = token_env
        contract_path = tmp_path / "scan.json"
        contract_path.write_text(json.dumps(contract))
        env = os.environ.copy()
        env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE=mode)
        if token_env and token_value:
            env[token_env] = token_value
        env["FOURGATE_WRITE_TEST_TOKEN"] = "write-token-supplied-to-server"
        result = subprocess.run([sys.executable, "-m", "fourgate", "scan", str(contract_path),
                                 "--confirm-test-account", "disposable-demo"], cwd=ROOT, env=env,
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


def test_auth_failure_is_unknown(tmp_path):
    result, row, _ = _run(tmp_path, "broken", 401)
    assert result.returncode == 1
    assert row["status"] == "UNKNOWN"


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
