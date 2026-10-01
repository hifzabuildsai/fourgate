"""`fourgate summary` turns shape-only outcome logs into a local pilot page."""
import json

from fourgate import cli, report, summary
from wrap import outcome

DAY1 = 1790000000.0  # 2026-09-21 UTC
DAY2 = DAY1 + 86400


def _line(ts, status, reason, tool="send_email", server="mail", gate_ms=None, **extra):
    item = {"timestamp": ts, "server": server, "tool": tool, "mode": "shadow",
            "status": status, "reason_code": reason, "checked_fields": ["id"]}
    if gate_ms is not None:
        item["gate_ms"] = gate_ms
    item.update(extra)
    return json.dumps(item)


def _write_log(tmp_path, lines, name="outcomes.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_summarize_counts_tools_days_reasons_and_latency(tmp_path):
    log = _write_log(tmp_path, [
        _line(DAY1, "pass", "postcondition_satisfied", gate_ms=1200),
        _line(DAY1 + 60, "pass", "postcondition_satisfied", gate_ms=1400),
        _line(DAY2, "fail", "record_missing", tool="create_issue", server="tracker", gate_ms=1600),
        _line(DAY2 + 5, "unknown", "verifier_timeout", gate_ms=2100),
        "not json",
        json.dumps({"status": "maybe", "timestamp": DAY1}),
        json.dumps({"status": "pass"}),
        "",
    ])
    records, skipped = summary.load([log])
    result = summary.summarize(records, skipped)
    assert result["calls"] == 4 and skipped == 3
    assert result["totals"] == {"pass": 2, "fail": 1, "unknown": 1}
    assert result["by_tool"]["mail/send_email"] == {"pass": 2, "fail": 0, "unknown": 1}
    assert result["by_tool"]["tracker/create_issue"] == {"pass": 0, "fail": 1, "unknown": 0}
    assert list(result["by_day"]) == ["2026-09-21", "2026-09-22"]
    assert {"status": "fail", "reason_code": "record_missing", "count": 1} in result["reasons"]
    assert result["latency"] == {"samples": 4, "p50_ms": 1400, "p95_ms": 2100, "max_ms": 2100}
    assert result["servers"] == ["mail", "tracker"] and result["modes"] == ["shadow"]


def test_latency_absent_for_older_logs_without_gate_ms(tmp_path):
    records, _ = summary.load([_write_log(tmp_path, [_line(DAY1, "pass", "postcondition_satisfied")])])
    assert summary.summarize(records)["latency"] is None


def test_html_is_static_escaped_and_ignores_unknown_keys(tmp_path):
    secret = "CUSTOMER-SECRET-VALUE-91"
    log = _write_log(tmp_path, [
        _line(DAY1, "fail", "field_mismatch", tool="<script>alert(1)</script>", gate_ms=900,
              arguments={"to": secret}, extracted={"id": secret}),
        _line(DAY1 + 1, "pass", "postcondition_satisfied"),
    ])
    records, skipped = summary.load([log])
    page = summary.render_html(summary.summarize(records, skipped))
    assert secret not in page
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "Content-Security-Policy" in page and "default-src 'none'" in page
    assert "http://" not in page and "https://" not in page
    assert "Fourgate outcome summary" in page
    assert "Read-back proved" not in page  # record_missing not present
    assert "a contracted field has a different value" in page


def test_cli_summary_writes_page_and_prints_totals(tmp_path, capsys):
    log = _write_log(tmp_path, [_line(DAY1, "pass", "postcondition_satisfied", gate_ms=1300),
                                _line(DAY1 + 1, "unknown", "verifier_error", gate_ms=1800)])
    out = tmp_path / "out" / "summary.html"
    assert cli.main(["summary", str(log), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "2 protected calls" in printed and "PASS 1" in printed and "UNKNOWN 1" in printed
    assert "p50 1300 ms" in printed
    assert out.exists() and "Fourgate outcome summary" in out.read_text(encoding="utf-8")

    assert cli.main(["summary", str(log), "--out", str(out), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["totals"]["unknown"] == 1


def test_cli_summary_errors_exit_2(tmp_path, capsys):
    empty = _write_log(tmp_path, ["garbage"], name="empty.jsonl")
    assert cli.main(["summary", str(empty), "--out", str(tmp_path / "s.html")]) == 2
    assert cli.main(["summary", str(tmp_path / "missing.jsonl"), "--out", str(tmp_path / "s.html")]) == 2
    assert not (tmp_path / "s.html").exists()


def test_outcome_record_carries_gate_ms_only_when_valid():
    evaluation = {"status": "pass", "reason_code": "postcondition_satisfied", "checked_fields": ["id"]}
    assert outcome.record("s", "t", "shadow", evaluation, gate_ms=1234)["gate_ms"] == 1234
    assert "gate_ms" not in outcome.record("s", "t", "shadow", evaluation)
    assert "gate_ms" not in outcome.record("s", "t", "shadow", evaluation, gate_ms=-1)


def test_scan_html_report_has_cases_table(tmp_path):
    raw = {"scan_version": 1, "test_account": "disposable", "cases": [
        {"tool": "send_email", "status": "PASS", "reason_code": "postcondition_satisfied", "attempts": 1},
        {"tool": "create_issue", "status": "FAIL", "reason_code": "record_missing", "attempts": 3,
         "evidence": {"request": {}, "tool_response": {}, "readback": {"status": 404}}}]}
    _, html_path = report.write(report.build(raw, "scan.json"), tmp_path / "reports")
    page = html_path.read_text(encoding="utf-8")
    assert "<th>Read-back</th>" in page and "GET 404" in page
    assert "<code>create_issue</code>" in page and "Full evidence" in page
    assert "Content-Security-Policy" in page
