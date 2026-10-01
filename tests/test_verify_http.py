"""Runtime HTTP read-back verifier tests use a loopback server, never an external account."""
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from _support import ScriptedSession, run_initialize

ROOT = Path(__file__).resolve().parent.parent
WRAP = ROOT / "wrap" / "wrap.py"
SERVER = ROOT / "fixtures" / "outcome_server.py"
TOKEN_ENV = "FOURGATE_VERIFY_HTTP_TEST_TOKEN"
TOKEN = "local-fake-verify-token-3b9e"
EXTRACTED = {"issue_id": "ISSUE-001", "title": "REQUESTED-SECRET-TITLE"}


@contextmanager
def _http(status=200, title="REQUESTED-SECRET-TITLE", delay=0.0):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append((self.path, self.headers.get("Authorization")))
            if delay:
                time.sleep(delay)
            body = json.dumps({"id": "ISSUE-001", "title": title}).encode() if status == 200 else b"{}"
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield httpd.server_port, seen
    finally:
        httpd.shutdown()
        httpd.server_close()


def _config(tmp_path, port, **overrides):
    config = {"type": "http", "url_template": f"http://127.0.0.1:{port}/issues/{{issue_id}}",
              "expected_fields": {"title": "title"}, "missing_statuses": [404],
              "token_env": TOKEN_ENV, "attempts": 2, "interval_ms": 10, "timeout_ms": 1000}
    config.update(overrides)
    path = tmp_path / "readback.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _verify(config_path, extracted=EXTRACTED, token=TOKEN):
    env = os.environ.copy()
    env.pop(TOKEN_ENV, None)
    if token:
        env[TOKEN_ENV] = token
    stdin = extracted if isinstance(extracted, str) else json.dumps(extracted)
    result = subprocess.run([sys.executable, "-m", "fourgate.verify_http", str(config_path)], cwd=ROOT, env=env,
                            input=stdin, text=True, capture_output=True, timeout=10)
    assert TOKEN not in result.stdout and TOKEN not in result.stderr
    return result


def test_matching_record_passes_with_token(tmp_path):
    with _http() as (port, seen):
        result = _verify(_config(tmp_path, port))
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"status": "pass"}
    assert seen == [("/issues/ISSUE-001", f"Bearer {TOKEN}")]


def test_field_mismatch_fails_with_structural_evidence_only(tmp_path):
    with _http(title="OBSERVED-SECRET-TITLE") as (port, seen):
        result = _verify(_config(tmp_path, port))
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "status": "fail", "reason_code": "field_mismatch",
        "evidence": {"method": "GET", "status": 200, "attempts": 2,
                     "checked_fields": ["title"], "mismatched_fields": ["title"]}}
    for value in ("OBSERVED-SECRET-TITLE", "REQUESTED-SECRET-TITLE", "ISSUE-001", "127.0.0.1"):
        assert value not in result.stdout
    assert len(seen) == 2


def test_configured_missing_status_fails_record_missing(tmp_path):
    with _http(status=404) as (port, _):
        result = _verify(_config(tmp_path, port))
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "status": "fail", "reason_code": "record_missing",
        "evidence": {"method": "GET", "status": 404, "attempts": 2}}


@pytest.mark.parametrize("status", [401, 403, 503])
def test_auth_denied_and_unconfigured_status_exit_nonzero(tmp_path, status):
    with _http(status=status) as (port, seen):
        result = _verify(_config(tmp_path, port))
    assert result.returncode != 0
    assert result.stdout == ""
    assert f"GET status {status}" in result.stderr
    assert seen and all(auth == f"Bearer {TOKEN}" for _, auth in seen)


def test_unconfigured_404_exits_nonzero(tmp_path):
    with _http(status=404) as (port, _):
        result = _verify(_config(tmp_path, port, missing_statuses=[]))
    assert result.returncode != 0 and result.stdout == ""


def test_timeout_exits_nonzero(tmp_path):
    with _http(delay=1.5) as (port, _):
        start = time.monotonic()
        result = _verify(_config(tmp_path, port, attempts=1, timeout_ms=300))
        elapsed = time.monotonic() - start
    assert result.returncode != 0 and result.stdout == ""
    assert elapsed < 1.5


def test_missing_credential_exits_nonzero_without_request(tmp_path):
    with _http() as (port, seen):
        result = _verify(_config(tmp_path, port), token=None)
    assert result.returncode != 0 and result.stdout == ""
    assert "credential_missing" in result.stderr
    assert seen == []


@pytest.mark.parametrize("overrides", [
    {"url_template": "http://example.com/issues/{issue_id}"},
    {"url_template": "https://{issue_id}/issues"},
    {"url_template": "http://127.0.0.1:1/issues/{not_extracted}"},
    {"timeout_ms": 5000},
    {"expected_fields": {}},
])
def test_bad_config_exits_nonzero_without_request(tmp_path, overrides):
    with _http() as (port, seen):
        result = _verify(_config(tmp_path, port, **overrides))
    assert result.returncode == 2 and result.stdout == ""
    assert seen == []


@pytest.mark.parametrize("stdin", ["", "not json", "[]", "{}"])
def test_bad_input_exits_nonzero(tmp_path, stdin):
    with _http() as (port, seen):
        result = _verify(_config(tmp_path, port), extracted=stdin)
    assert result.returncode == 2 and result.stdout == ""
    assert seen == []


def test_missing_config_file_exits_nonzero(tmp_path):
    result = _verify(tmp_path / "absent.json")
    assert result.returncode == 2 and result.stdout == ""


def _wrap_session(cmd, store):
    env = os.environ.copy()
    env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE="broken")
    env[TOKEN_ENV] = TOKEN
    session = ScriptedSession(cmd, env=env)
    run_initialize(session)
    assert "result" in session.send_request("tools/list", {})
    return session


def _call_and_close(session, title):
    try:
        response = session.send_request("tools/call", {"name": "create_issue", "arguments": {"title": title}})
        captured = session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()
    return response, captured


@pytest.mark.parametrize("observed_title,expected_status,expected_reason", [
    ("REQUESTED-SECRET-TITLE", "pass", "postcondition_satisfied"),
    ("OBSERVED-SECRET-TITLE", "fail", "field_mismatch"),
])
def test_wrap_shadow_mode_is_byte_identical_and_logs_evaluation(tmp_path, observed_title, expected_status,
                                                                 expected_reason):
    title = "REQUESTED-SECRET-TITLE"
    log = tmp_path / "outcomes.jsonl"
    with _http(title=observed_title) as (port, seen):
        config = _config(tmp_path, port, attempts=1, timeout_ms=1000)
        contracts = tmp_path / "contracts.json"
        contracts.write_text(json.dumps({"contract_version": 1, "tools": {"create_issue": {
            "extract": {"issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
                        "title": {"source": "arguments", "path": "title"}},
            "verifier": {"command": ["{python}", "-m", "fourgate.verify_http", str(config)],
                         "cwd": str(ROOT), "timeout_ms": 2000},
            "allowed_failure_reasons": ["record_missing", "field_mismatch"],
            "recovery": "stop"}}}), encoding="utf-8")
        direct, direct_bytes = _call_and_close(
            _wrap_session([sys.executable, str(SERVER)], tmp_path / "direct.json"), title)
        shadow, shadow_bytes = _call_and_close(_wrap_session(
            [sys.executable, str(WRAP), "--outcome-contracts", str(contracts), "--outcome-mode", "shadow",
             "--outcome-log", str(log), "--server-label", "demo", "--", sys.executable, str(SERVER)],
            tmp_path / "shadow.json"), title)
    assert shadow == direct
    assert shadow_bytes == direct_bytes
    call_id = direct["id"]
    def result_line(captured):
        return [line for line in captured.splitlines() if json.loads(line).get("id") == call_id]
    assert result_line(shadow_bytes) == result_line(direct_bytes) != []
    assert seen == [("/issues/ISSUE-001", f"Bearer {TOKEN}")]
    logged = log.read_text(encoding="utf-8")
    record = json.loads(logged.strip())
    assert (record["mode"], record["tool"], record["server"]) == ("shadow", "create_issue", "demo")
    assert (record["status"], record["reason_code"]) == (expected_status, expected_reason)
    assert record["checked_fields"] == ["issue_id", "title"]
    for value in (title, observed_title, "ISSUE-001", TOKEN):
        assert value not in logged
