"""Bounded, independent HTTP read-back for explicitly contracted writes.

The verifier performs GET requests only. It does not retry the write. A
missing/mismatched record becomes FAIL only after the configured attempts;
authentication, network, parse, and timeout uncertainty remain UNKNOWN.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from wrap import outcome

MAX_ATTEMPTS = 5
MAX_TOTAL_MS = 10000
MAX_BODY_BYTES = 1024 * 1024
NAME = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(_NoRedirect)


def validate(config, extract):
    if not isinstance(config, dict) or config.get("type") not in ("http", "github_issue"):
        raise ValueError("readback.type must be http or github_issue")
    if not isinstance(extract, dict) or not extract:
        raise ValueError("readback requires extraction selectors")
    if config["type"] == "http":
        template = config.get("url_template")
        if not isinstance(template, str):
            raise ValueError("http readback requires url_template")
        _validate_template(template, extract)
        missing = config.get("missing_statuses", [])
        if not isinstance(missing, list) or any(type(s) is not int or s < 400 or s > 499 or s in (401, 403) for s in missing):
            raise ValueError("missing_statuses must contain explicit 4xx statuses other than 401/403")
    else:
        if not isinstance(config.get("repository"), str) or not REPOSITORY.fullmatch(config["repository"]):
            raise ValueError("github_issue.repository must be owner/name")
        number = config.get("issue_number_field")
        if number not in extract:
            raise ValueError("github_issue.issue_number_field must reference an extracted field")
        if type(config.get("missing_is_fail", False)) is not bool:
            raise ValueError("missing_is_fail must be boolean")
    expected = config.get("expected_fields")
    if not isinstance(expected, dict) or not expected or any(
        not isinstance(path, str) or not path or key not in extract for path, key in expected.items()
    ):
        raise ValueError("expected_fields must map JSON response paths to extracted field names")
    attempts = config.get("attempts", 3)
    delay = config.get("interval_ms", 250)
    budget = config.get("timeout_ms", 5000)
    if type(attempts) is not int or not 1 <= attempts <= MAX_ATTEMPTS:
        raise ValueError("attempts must be within 1..5")
    if type(delay) is not int or not 0 <= delay <= 2000:
        raise ValueError("interval_ms must be within 0..2000")
    if type(budget) is not int or not 1 <= budget <= MAX_TOTAL_MS:
        raise ValueError("timeout_ms must be within 1..10000")
    token = config.get("token_env")
    if token is not None and (not isinstance(token, str) or not NAME.fullmatch(token)):
        raise ValueError("token_env must be an environment variable name")
    if config["type"] == "github_issue" and not token:
        raise ValueError("github_issue requires token_env")


def _validate_template(template, extract):
    # A dynamic hostname could send an env-token to an attacker-controlled URL.
    parts = urllib.parse.urlsplit(template)
    if not parts.hostname or "{" in parts.netloc or "}" in parts.netloc or parts.username or parts.password:
        raise ValueError("readback URL must use a static host without userinfo")
    loopback = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (loopback and parts.scheme == "http"):
        raise ValueError("readback URL must be HTTPS (HTTP permitted only on loopback)")
    if "#" in template or "{" in template[:template.find(parts.netloc) + len(parts.netloc)]:
        raise ValueError("readback URL cannot contain a fragment or dynamic authority")
    names = PLACEHOLDER.findall(template)
    if template.count("{") != len(names) or template.count("}") != len(names) or any(name not in extract for name in names):
        raise ValueError("URL placeholders must reference extracted field names")


def _url(config, extracted):
    if config["type"] == "github_issue":
        number = extracted[config["issue_number_field"]]
        if type(number) is not int or number <= 0:
            raise ValueError("issue number must be a positive integer")
        return f"https://api.github.com/repos/{config['repository']}/issues/{number}"
    return PLACEHOLDER.sub(lambda m: urllib.parse.quote(str(extracted[m.group(1)]), safe=""),
                           config["url_template"])


def _get(url, token, timeout):
    headers = {"Accept": "application/vnd.github+json" if url.startswith("https://api.github.com/") else "application/json",
               "User-Agent": "Fourgate/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                return response.status, None
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        return exc.code, None


def evaluate(config, contract, arguments, response):
    """Return a structural evaluation; never interpret uncertainty as PASS."""
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict) or result.get("isError"):
        return {"status": "unknown", "reason_code": "not_success_result", "attempts": 0}
    extracted, error = outcome._extract(contract, arguments, response)
    if error:
        return {"status": "unknown", "reason_code": error, "attempts": 0}
    token_env = config.get("token_env")
    token = os.environ.get(token_env) if token_env else None
    if token_env and not token:
        return {"status": "unknown", "reason_code": "credential_missing", "attempts": 0}
    try:
        url = _url(config, extracted)
    except (ValueError, KeyError, TypeError):
        return {"status": "unknown", "reason_code": "readback_selector_invalid", "attempts": 0}
    deadline = time.monotonic() + config.get("timeout_ms", 5000) / 1000
    attempts = 0
    last = {"status": "unknown", "reason_code": "readback_timeout", "attempts": 0}
    for index in range(config.get("attempts", 3)):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempts += 1
        try:
            status, document = _get(url, token, min(2.0, remaining))
        except (OSError, ValueError, UnicodeDecodeError, TimeoutError):
            last = {"status": "unknown", "reason_code": "readback_error", "attempts": attempts}
        else:
            if status == 200 and isinstance(document, dict):
                if any(outcome._path_get(document, path) is outcome.MISSING
                       for path in config["expected_fields"]):
                    last = {"status": "unknown", "reason_code": "readback_shape_invalid", "attempts": attempts}
                    continue
                mismatched = [{"path": path, "expected": extracted[field],
                               "observed": outcome._path_get(document, path)}
                              for path, field in config["expected_fields"].items()
                              if outcome._path_get(document, path) != extracted[field]]
                if not mismatched:
                    return {"status": "pass", "reason_code": "postcondition_satisfied", "attempts": attempts,
                            "checked_fields": sorted(config["expected_fields"])}
                last = {"status": "fail", "reason_code": "field_mismatch", "attempts": attempts,
                        "checked_fields": sorted(config["expected_fields"]), "mismatched_fields": mismatched,
                        "readback_evidence": {"method": "GET", "url": url, "status": status, "body": document}}
            elif status in (config.get("missing_statuses", []) if config["type"] == "http"
                            else ([404] if config.get("missing_is_fail", False) else [])):
                last = {"status": "fail", "reason_code": "record_missing", "attempts": attempts,
                        "readback_evidence": {"method": "GET", "url": url, "status": status, "body": document}}
            else:
                last = {"status": "unknown", "reason_code": "readback_unconfirmed", "attempts": attempts}
        if index + 1 < config.get("attempts", 3):
            time.sleep(min(config.get("interval_ms", 250) / 1000, max(0, deadline - time.monotonic())))
    return last
