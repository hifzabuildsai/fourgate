"""Bounded, independent HTTP read-back for explicitly contracted writes.

The verifier performs GET requests only. It does not retry the write. A
missing/mismatched record becomes FAIL only after the configured attempts;
authentication, network, parse, and timeout uncertainty remain UNKNOWN.

How the read credential (``token_env``) is sent is set by ``readback.auth``
(``http`` read-back only; the default is ``Authorization: Bearer``):

    {"scheme": "bearer"}
    {"scheme": "header", "header": "X-Api-Key", "prefix": ""}
    {"scheme": "basic", "username_env": "READBACK_USER"}    # token is the password
    {"scheme": "basic", "username": "api"}                  # static, non-secret username
    {"scheme": "basic", "token_as": "username", "password": "X"}  # token is the username

``readback.headers`` adds static, non-secret request headers (for example an
API version). Credential-looking and transport header names are rejected so a
secret can only ever arrive through an environment variable.
"""
import base64
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
# RFC 9110 field-name token, bounded.
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}$")
# Printable ASCII only: no CR/LF or other control characters (header injection).
HEADER_VALUE = re.compile(r"^[\x20-\x7e]*$")
MAX_STATIC_HEADERS = 16
MAX_STATIC_VALUE = 256
AUTH_SCHEMES = ("bearer", "header", "basic")
AUTH_KEYS = {
    "bearer": {"scheme"},
    "header": {"scheme", "header", "prefix"},
    "basic": {"scheme", "username", "username_env", "token_as", "password"},
}
# Transport-controlled headers a contract must never set or carry a token in.
RESERVED_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection", "upgrade", "te", "trailer",
    "keep-alive", "expect", "proxy-authorization", "proxy-connection", "forwarded",
})
# Static headers are committed in contracts, so anything credential-shaped is
# refused there; credentials go through token_env and readback.auth only.
SECRET_HEADER = re.compile(r"(?:auth|token|secret|passw|key|cookie|credential|session|signature)", re.I)


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
    if config["type"] != "http" and ("auth" in config or "headers" in config):
        raise ValueError("readback.auth and readback.headers are supported only for type http")
    auth_header = _validate_auth(config.get("auth"), token)
    _validate_static_headers(config.get("headers"), auth_header)


def _validate_auth(auth, token_env):
    """Validate readback.auth; return the lower-case header name it sets, or None."""
    if auth is None:
        return "authorization" if token_env else None
    if not isinstance(auth, dict) or auth.get("scheme") not in AUTH_SCHEMES:
        raise ValueError("readback.auth.scheme must be bearer, header or basic")
    if not token_env:
        raise ValueError("readback.auth requires token_env")
    scheme = auth["scheme"]
    unknown = set(auth) - AUTH_KEYS[scheme]
    if unknown:
        raise ValueError(f"readback.auth ({scheme}) has unsupported keys: {', '.join(sorted(unknown))}")
    if scheme == "bearer":
        return "authorization"
    if scheme == "header":
        name = auth.get("header")
        if not isinstance(name, str) or not HEADER_NAME.fullmatch(name) or name.lower() in RESERVED_HEADERS:
            raise ValueError("readback.auth.header must be a valid, non-transport HTTP header name")
        prefix = auth.get("prefix", "")
        if not isinstance(prefix, str) or len(prefix) > 64 or not HEADER_VALUE.fullmatch(prefix):
            raise ValueError("readback.auth.prefix must be printable ASCII, at most 64 characters")
        return name.lower()
    token_as = auth.get("token_as", "password")
    if token_as not in ("password", "username"):
        raise ValueError("readback.auth.token_as must be password or username")
    username, username_env = auth.get("username"), auth.get("username_env")
    if token_as == "password":
        if (username is None) == (username_env is None):
            raise ValueError("basic auth needs exactly one of username or username_env")
        if username is not None and (not isinstance(username, str) or not username or len(username) > 128
                                     or ":" in username or not HEADER_VALUE.fullmatch(username)):
            raise ValueError("readback.auth.username must be printable ASCII without ':' (at most 128 characters)")
        if username_env is not None and (not isinstance(username_env, str) or not NAME.fullmatch(username_env)
                                         or username_env == token_env):
            raise ValueError("readback.auth.username_env must be an environment variable name other than token_env")
        if "password" in auth:
            raise ValueError("readback.auth.password is only for token_as username; the token is the password")
    else:
        if username is not None or username_env is not None:
            raise ValueError("basic auth with token_as username takes no username or username_env")
        filler = auth.get("password", "")
        if not isinstance(filler, str) or len(filler) > 16 or not HEADER_VALUE.fullmatch(filler):
            raise ValueError("readback.auth.password must be a short non-secret filler (at most 16 characters)")
    return "authorization"


def _validate_static_headers(headers, auth_header):
    if headers is None:
        return
    if not isinstance(headers, dict) or len(headers) > MAX_STATIC_HEADERS:
        raise ValueError(f"readback.headers must be an object of at most {MAX_STATIC_HEADERS} headers")
    seen = set()
    for name, value in headers.items():
        lower = name.lower() if isinstance(name, str) else ""
        if not HEADER_NAME.fullmatch(name if isinstance(name, str) else ""):
            raise ValueError("readback.headers names must be valid HTTP header names")
        if lower in seen:
            raise ValueError(f"readback.headers repeats {name!r}")
        seen.add(lower)
        if lower in RESERVED_HEADERS or lower == "user-agent":
            raise ValueError(f"readback.headers cannot set {name!r}")
        if SECRET_HEADER.search(name) or lower == auth_header:
            raise ValueError(f"readback.headers cannot carry credentials ({name!r}); use token_env with readback.auth")
        if not isinstance(value, str) or len(value) > MAX_STATIC_VALUE or not HEADER_VALUE.fullmatch(value):
            raise ValueError(f"readback.headers[{name!r}] must be printable ASCII, at most {MAX_STATIC_VALUE} characters")


def credential_envs(config):
    """Environment variable names the read-back needs before any write is sent."""
    names = []
    if isinstance(config, dict):
        if config.get("token_env"):
            names.append(config["token_env"])
        auth = config.get("auth")
        if isinstance(auth, dict) and auth.get("username_env"):
            names.append(auth["username_env"])
    return names


def _request_headers(config, url, token, username=None):
    headers = {"Accept": "application/vnd.github+json" if url.startswith("https://api.github.com/") else "application/json",
               "User-Agent": "Fourgate/0.2"}
    for name, value in (config.get("headers") or {}).items():
        # Static headers replace defaults case-insensitively (e.g. a vendor Accept type).
        for existing in [k for k in headers if k.lower() == name.lower()]:
            del headers[existing]
        headers[name] = value
    if not token:
        return headers
    auth = config.get("auth") or {"scheme": "bearer"}
    if auth["scheme"] == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    elif auth["scheme"] == "header":
        headers[auth["header"]] = f"{auth.get('prefix', '')}{token}"
    else:
        if auth.get("token_as", "password") == "username":
            pair = f"{token}:{auth.get('password', '')}"
        else:
            pair = f"{username if username is not None else auth['username']}:{token}"
        headers["Authorization"] = "Basic " + base64.b64encode(pair.encode("utf-8")).decode("ascii")
    return headers


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


def _get(url, headers, timeout):
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
    return evaluate_extracted(config, extracted)


def evaluate_extracted(config, extracted):
    """Read back already-extracted fields; shared by scan and the runtime verifier."""
    token_env = config.get("token_env")
    token = os.environ.get(token_env) if token_env else None
    if token_env and not token:
        return {"status": "unknown", "reason_code": "credential_missing", "attempts": 0}
    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    username_env = auth.get("username_env")
    username = os.environ.get(username_env) if username_env else None
    if username_env and (not username or ":" in username):
        return {"status": "unknown", "reason_code": "credential_missing", "attempts": 0}
    try:
        url = _url(config, extracted)
    except (ValueError, KeyError, TypeError):
        return {"status": "unknown", "reason_code": "readback_selector_invalid", "attempts": 0}
    headers = _request_headers(config, url, token, username)
    deadline = time.monotonic() + config.get("timeout_ms", 5000) / 1000
    attempts = 0
    last = {"status": "unknown", "reason_code": "readback_timeout", "attempts": 0}
    for index in range(config.get("attempts", 3)):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempts += 1
        try:
            status, document = _get(url, headers, min(2.0, remaining))
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
                if config["type"] == "http":
                    last["readback_evidence"] = {"method": "GET", "status": status}
        if index + 1 < config.get("attempts", 3):
            time.sleep(min(config.get("interval_ms", 250) / 1000, max(0, deadline - time.monotonic())))
    return last
