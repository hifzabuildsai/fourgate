"""Real stdio scan and local read-back for Resend-style MCP text results."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from fourgate.scan import load_contract, scan

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("selector", [
    {"parse": "embedded_json", "field": "id"},
    {"parse": "regex", "pattern": r'"id"\s*:\s*"(?P<id>[^"]+)"', "group": "id"},
])
@pytest.mark.parametrize("mode, expected", [
    ("healthy", ("PASS", "postcondition_satisfied")),
    ("no_id", ("UNKNOWN", "success_without_record_id")),
])
def test_resend_style_text_id_with_independent_readback(tmp_path, monkeypatch, selector, mode, expected):
    store = tmp_path / "sent.json"
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            record = json.loads(store.read_text()) if store.exists() else None
            status = 200 if record and self.path == "/emails/" + record["id"] else 404
            payload = json.dumps(record or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("FOURGATE_DEMO_STORE", str(store))
        monkeypatch.setenv("FOURGATE_RESEND_MODE", mode)
        parsed = {"source": "result", "path": "result.content.0.text", **selector}
        contract = {"scan_version": 1, "server": {
            "transport": "stdio", "command": [sys.executable, str(ROOT / "fixtures" / "resend_text_server.py")],
            "test_account": "disposable-resend-fixture"}, "write_tools": ["send_email"], "cases": [{
            "tool": "send_email", "arguments": {"to": "recipient@example.invalid"},
            "outcome_contract": {"record_id_field": "email_id", "extract": {
                "email_id": parsed, "to": {"source": "arguments", "path": "to"}}},
            "readback": {"type": "http", "url_template":
                f"http://127.0.0.1:{server.server_port}/emails/{{email_id}}",
                "expected_fields": {"id": "email_id", "to": "to"},
                "missing_statuses": [404], "attempts": 1, "timeout_ms": 1000}}]}
        path = tmp_path / "scan.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        row = scan(path, "disposable-resend-fixture")["cases"][0]
        assert (row["status"], row["reason_code"]) == expected
        assert calls == (["/emails/email_test_001"] if mode == "healthy" else [])
        if mode == "no_id":
            assert row["attempts"] == 0
            assert row["evidence"]["readback"] == {
                "reason_code": "readback_not_run_without_record_id"}
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("selector", [
    {"parse": "regex", "pattern": "(", "group": 1},
    {"parse": "regex", "pattern": "id", "group": 1},
    {"parse": "embedded_json", "field": ""},
    {"parse": "embedded_json", "field": "id", "path": "result.error"},
])
def test_invalid_text_selector_is_rejected_before_write(tmp_path, selector):
    contract = json.loads((ROOT / "fixtures" / "contracts" / "scan_demo.json").read_text())
    contract["cases"][0]["outcome_contract"]["extract"]["issue_id"] = {
        "source": "result", "path": "result.content.0.text", **selector}
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(contract))
    with pytest.raises(ValueError):
        load_contract(path, "disposable-demo")
