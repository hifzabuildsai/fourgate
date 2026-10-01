"""Local JSON and single-file HTML scan reports with conservative redaction."""
import copy
import datetime
import html
import json
import os
import re
import tempfile
from pathlib import Path

SECRET_KEY = re.compile(r"(?:token|secret|password|api[_-]?key|authorization|cookie|credential)", re.I)
SECRET_VALUE = re.compile(r"(?i)(?:github_pat_[A-Za-z0-9_]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|\bBearer\s+\S+|\bsk(?:-|_(?:test|live)_)[A-Za-z0-9_-]{12,})")
URL_USERINFO = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@")


def _secrets():
    return sorted((value for key, value in os.environ.items()
                   if (SECRET_KEY.search(key) or key.upper() == "PWD" or key.upper().endswith("_URL"))
                   and len(value) >= 8),
                  key=len, reverse=True)


def sanitize(value, secrets=None):
    """Redact named fields, recognized token patterns, and secret env values.

    This is best effort. An arbitrary secret embedded in an unmarked field
    cannot be recognized with certainty; review reports before sharing.
    """
    if secrets is None:
        secrets = _secrets()
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if SECRET_KEY.search(str(key)) else sanitize(item, secrets))
                for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        value = URL_USERINFO.sub(r"\1[REDACTED]@", value)
        return SECRET_VALUE.sub("[REDACTED]", value)
    return value


def build(raw, contract_path):
    result = sanitize(copy.deepcopy(raw))
    result["generated_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for row in result["cases"]:
        if row["status"] == "FAIL":
            row["repro_steps"] = [
                "Use only the named disposable test account and check verifier read access.",
                "Set required credential environment variables locally; never paste them into the contract.",
                "Run: fourgate scan " + str(contract_path) +
                " --confirm-test-account " + result["test_account"] + " --report-dir REPORT_DIR",
                "Compare the tool result to the independent read-back in this report.",
            ]
    return sanitize(result)


def _write_private(path, content):
    """Write privately in the destination directory; replace atomically."""
    path = Path(path)
    descriptor, temp = tempfile.mkstemp(prefix=".fourgate-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_private_file(path, content):
    """Write a single private file, creating its parent directory if needed."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_private(path, content)
    return path


def write(report, directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    json_path = directory / "fourgate-report.json"
    html_path = directory / "fourgate-report.html"
    _write_private(json_path, payload + "\n")
    # No JavaScript, remote content, links, or network requests in this file.
    _write_private(html_path, render_html(report, payload))
    return json_path, html_path


_STATUS_CLASS = {"PASS": "pass", "FAIL": "fail", "UNKNOWN": "unknown"}
_STATUS_ICON = {"PASS": "\u2713", "FAIL": "\u2715", "UNKNOWN": "?"}
_CSS = """
:root{--bg:#fcfcfb;--ink:#1d1d1b;--ink2:#555550;--line:#e4e4df;--card:#f4f4f1;
--pass:#0ca30c;--fail:#d03b3b;--unknown:#fab219}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--ink:#f1f1ee;--ink2:#c4c4be;--line:#34342f;--card:#242422}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:75rem;margin:0 auto;padding:2rem 1rem 3rem}
h1{font-size:1.6rem;margin:0 0 .25rem}h2{font-size:1.1rem;margin:2rem 0 .75rem}.sub{color:var(--ink2)}
.tiles{display:flex;gap:.75rem;flex-wrap:wrap;margin:1.25rem 0}
.tile{background:var(--card);border-radius:10px;padding:.8rem 1rem;min-width:8rem}
.tile .v{font-size:1.7rem;font-weight:650;line-height:1.2}.tile .k{color:var(--ink2);font-size:.85rem}
.dot{display:inline-block;width:.7rem;height:.7rem;border-radius:3px;margin-right:.35rem}
.dot.pass{background:var(--pass)}.dot.fail{background:var(--fail)}.dot.unknown{background:var(--unknown)}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.5rem;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
th{color:var(--ink2);font-size:.85rem}
.scroll{overflow-x:auto}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--card);padding:1rem;border-radius:10px}
code{font:.88em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
"""


def render_html(report, payload):
    """Self-contained scan report page: summary table first, full evidence below."""
    e = html.escape
    cases = report.get("cases") or []
    counts = {status: sum(1 for c in cases if c.get("status") == status) for status in _STATUS_CLASS}
    tiles = "".join(
        f'<div class="tile"><div class="k"><span class="dot {cls}" aria-hidden="true"></span>'
        f'{_STATUS_ICON[status]} {status}</div><div class="v">{counts[status]}</div></div>'
        for status, cls in _STATUS_CLASS.items())
    rows = []
    for case in cases:
        status = str(case.get("status", "UNKNOWN"))
        cls = _STATUS_CLASS.get(status, "unknown")
        evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
        readback = evidence.get("readback") if isinstance(evidence.get("readback"), dict) else {}
        rb_status = readback.get("status")
        rb = f"GET {rb_status}" if isinstance(rb_status, int) else "-"
        rows.append(
            f'<tr><td><code>{e(str(case.get("tool")))}</code></td>'
            f'<td><span class="dot {cls}" aria-hidden="true"></span>{e(status)}</td>'
            f'<td><code>{e(str(case.get("reason_code", "")))}</code></td>'
            f'<td>{e(str(case.get("attempts", "-")))}</td><td>{e(rb)}</td></tr>')
    title = "Fourgate Scan Report"
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            f"<title>{title}</title><style>{_CSS}</style></head><body><main>"
            f"<h1>{title}</h1><p class=\"sub\">Test account: <code>{e(str(report.get('test_account', '')))}</code>"
            f" &middot; Generated {e(str(report.get('generated_at_utc', '')))}. Local, redacted evidence. Review before sharing.</p>"
            f'<div class="tiles">{tiles}</div>'
            "<h2>Cases</h2><div class=\"scroll\"><table><thead><tr><th>Tool</th><th>Result</th><th>Reason</th>"
            f"<th>Attempts</th><th>Read-back</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            "<p class=\"sub\">UNKNOWN is never counted as PASS. FAIL requires authoritative read-back evidence.</p>"
            f"<h2>Full evidence</h2><pre>{e(payload)}</pre></main></body></html>")
