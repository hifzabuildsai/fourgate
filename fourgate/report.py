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


def write(report, directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    json_path = directory / "fourgate-report.json"
    html_path = directory / "fourgate-report.html"
    _write_private(json_path, payload + "\n")
    # No JavaScript, remote content, links, or network requests in this file.
    title = "Fourgate Scan Report"
    document = ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
                "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
                f"<title>{title}</title><style>body{{font:16px system-ui;max-width:75rem;margin:2rem auto;"
                "padding:0 1rem}}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;"
                "padding:1rem}h1{color:#222}</style>"
                f"<h1>{title}</h1><p>Local, redacted evidence. Review before sharing.</p>"
                f"<pre>{html.escape(payload)}</pre></html>")
    _write_private(html_path, document)
    return json_path, html_path
