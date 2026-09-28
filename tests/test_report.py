"""Evidence reports must stay local and avoid leaking recognized credentials."""
import json
import os

from fourgate import report


def test_failure_report_preserves_repro_and_redacts_credentials(tmp_path, monkeypatch):
    token = "github_pat_SENSITIVE_TEST_VALUE_123456"
    monkeypatch.setenv("FOURGATE_GITHUB_READ_TOKEN", token)
    raw = {"scan_version": 1, "test_account": "disposable",
           "cases": [{"tool": "create_issue", "status": "FAIL", "reason_code": "field_mismatch",
                      "evidence": {
                          "request": {"params": {"name": "create_issue", "arguments": {
                              "title": "<script>alert(1)</script>", "api_key": token}}},
                          "tool_response": {"result": {"content": [
                              {"type": "text", "text": "Bearer " + token}]}}},
                      "readback": {"status": 200, "body": {"title": "different"}}}]}
    redacted = report.build(raw, "scan.json")
    json_path, html_path = report.write(redacted, tmp_path / "reports")
    payload = json_path.read_text(encoding="utf-8")
    page = html_path.read_text(encoding="utf-8")
    assert token not in payload and token not in page
    assert "[REDACTED]" in payload
    assert json.loads(payload)["cases"][0]["evidence"]["request"]["params"]["name"] == "create_issue"
    assert "repro_steps" in json.loads(payload)["cases"][0]
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "Content-Security-Policy" in page
    if os.name != "nt":
        assert json_path.stat().st_mode & 0o077 == 0
        assert html_path.stat().st_mode & 0o077 == 0
