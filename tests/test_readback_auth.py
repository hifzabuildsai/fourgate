"""readback.auth and readback.headers: loopback server only, never an external account."""
import base64
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from fourgate import readback

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "fixtures" / "contracts" / "scan_demo.json"
TOKEN_ENV = "FOURGATE_AUTH_TEST_READ_TOKEN"
USER_ENV = "FOURGATE_AUTH_TEST_READ_USER"
TOKEN = "local-fake-read-token-7c1d"
EXTRACTED = {"issue_id": "ISSUE-001", "title": "REQUESTED-TITLE"}
EXTRACT = {"issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
           "title": {"source": "arguments", "path": "title"}}


@contextmanager
def _http(status=200, title="REQUESTED-TITLE"):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append({k.lower(): v for k, v in self.headers.items()})
            body = json.dumps({"id": "ISSUE-001", "title": title}).encode() if status == 200 else b"{}"
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield httpd.server_port, seen
    finally:
        httpd.shutdown()
        httpd.server_close()


def _config(port, **overrides):
    config = {"type": "http", "url_template": f"http://127.0.0.1:{port}/issues/{{issue_id}}",
              "expected_fields": {"title": "title"}, "missing_statuses": [404],
              "token_env": TOKEN_ENV, "attempts": 1, "timeout_ms": 1000}
    config.update(overrides)
    return config


def _verify(tmp_path, config, env_extra=None, token=TOKEN):
    path = tmp_path / "readback.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in (TOKEN_ENV, USER_ENV)}
    if token:
        env[TOKEN_ENV] = token
    env.update(env_extra or {})
    result = subprocess.run([sys.executable, "-m", "fourgate.verify_http", str(path)], cwd=ROOT, env=env,
                            input=json.dumps(EXTRACTED), text=True, capture_output=True, timeout=10)
    encoded = base64.b64encode(TOKEN.encode()).decode()
    for leaked in (TOKEN, encoded):
        assert leaked not in result.stdout and leaked not in result.stderr
    return result


def _basic(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


@pytest.mark.parametrize("auth, header, expected", [
    (None, "authorization", f"Bearer {TOKEN}"),
    ({"scheme": "bearer"}, "authorization", f"Bearer {TOKEN}"),
    ({"scheme": "header", "header": "X-Api-Key"}, "x-api-key", TOKEN),
    ({"scheme": "header", "header": "Authorization", "prefix": "Token "}, "authorization", f"Token {TOKEN}"),
    ({"scheme": "basic", "username": "api"}, "authorization", _basic("api", TOKEN)),
    ({"scheme": "basic", "token_as": "username"}, "authorization", _basic(TOKEN, "")),
    ({"scheme": "basic", "token_as": "username", "password": "X"}, "authorization", _basic(TOKEN, "X")),
])
def test_auth_scheme_sends_token_in_configured_header(tmp_path, auth, header, expected):
    overrides = {"auth": auth} if auth else {}
    with _http() as (port, seen):
        result = _verify(tmp_path, _config(port, **overrides))
    assert result.returncode == 0 and json.loads(result.stdout) == {"status": "pass"}
    assert len(seen) == 1 and seen[0][header] == expected
    if header != "authorization":
        assert "authorization" not in seen[0]


def test_basic_username_from_env(tmp_path):
    with _http() as (port, seen):
        result = _verify(tmp_path, _config(port, auth={"scheme": "basic", "username_env": USER_ENV}),
                         env_extra={USER_ENV: "reader-account-7"})
    assert result.returncode == 0
    assert seen[0]["authorization"] == _basic("reader-account-7", TOKEN)
    assert "reader-account-7" not in result.stdout + result.stderr


def test_missing_basic_username_env_is_unknown_without_request(tmp_path):
    with _http() as (port, seen):
        result = _verify(tmp_path, _config(port, auth={"scheme": "basic", "username_env": USER_ENV}))
    assert result.returncode != 0 and result.stdout == ""
    assert "credential_missing" in result.stderr
    assert seen == []


def test_static_headers_are_sent_and_can_replace_accept(tmp_path):
    headers = {"Api-Version": "2024-01-01", "accept": "application/vnd.vendor+json"}
    with _http() as (port, seen):
        result = _verify(tmp_path, _config(port, headers=headers,
                                           auth={"scheme": "header", "header": "X-Api-Key"}))
    assert result.returncode == 0
    assert seen[0]["api-version"] == "2024-01-01"
    assert seen[0]["accept"] == "application/vnd.vendor+json"
    assert seen[0]["x-api-key"] == TOKEN


def test_static_headers_without_token(tmp_path):
    config = _config(0, headers={"Api-Version": "1"})
    config.pop("token_env")
    with _http() as (port, seen):
        config["url_template"] = f"http://127.0.0.1:{port}/issues/{{issue_id}}"
        result = _verify(tmp_path, config, token=None)
    assert result.returncode == 0
    assert seen[0]["api-version"] == "1" and "authorization" not in seen[0]


@pytest.mark.parametrize("status", [401, 403])
def test_wrong_auth_stays_unknown(tmp_path, status):
    with _http(status=status) as (port, _):
        result = _verify(tmp_path, _config(port, auth={"scheme": "header", "header": "X-Api-Key"}))
    assert result.returncode != 0 and result.stdout == ""


@pytest.mark.parametrize("overrides, message", [
    ({"auth": {"scheme": "digest"}}, "scheme"),
    ({"auth": "bearer"}, "scheme"),
    ({"auth": {"scheme": "bearer", "header": "X-Api-Key"}}, "unsupported keys"),
    ({"auth": {"scheme": "header"}}, "header name"),
    ({"auth": {"scheme": "header", "header": "X Api Key"}}, "header name"),
    ({"auth": {"scheme": "header", "header": "Host"}}, "header name"),
    ({"auth": {"scheme": "header", "header": "Proxy-Authorization"}}, "header name"),
    ({"auth": {"scheme": "header", "header": "X-Api-Key", "prefix": "a\r\nInjected: 1"}}, "prefix"),
    ({"auth": {"scheme": "basic"}}, "exactly one"),
    ({"auth": {"scheme": "basic", "username": "a", "username_env": USER_ENV}}, "exactly one"),
    ({"auth": {"scheme": "basic", "username": "a:b"}}, "username"),
    ({"auth": {"scheme": "basic", "username_env": TOKEN_ENV}}, "username_env"),
    ({"auth": {"scheme": "basic", "username_env": "not a name"}}, "username_env"),
    ({"auth": {"scheme": "basic", "username": "api", "password": "x"}}, "token_as username"),
    ({"auth": {"scheme": "basic", "token_as": "username", "username": "api"}}, "no username"),
    ({"auth": {"scheme": "basic", "token_as": "body"}}, "token_as"),
    ({"headers": {"Authorization": "Bearer static"}}, "credentials"),
    ({"headers": {"X-Api-Key": "static"}}, "credentials"),
    ({"headers": {"Cookie": "session=1"}}, "credentials"),
    ({"headers": {"X-Auth-Token": "static"}}, "credentials"),
    ({"headers": {"Ocp-Apim-Subscription-Key": "static"}}, "credentials"),
    ({"headers": {"Host": "evil.example"}}, "cannot set"),
    ({"headers": {"User-Agent": "other"}}, "cannot set"),
    ({"headers": {"Api-Version": "1\r\nX-Injected: 1"}}, "printable ASCII"),
    ({"headers": {"Api-Version": 1}}, "printable ASCII"),
    ({"headers": {"Bad Name": "1"}}, "header names"),
    ({"headers": {"Api-Version": "1", "api-version": "2"}}, "repeats"),
    ({"headers": {f"X-H{i}": "1" for i in range(17)}}, "at most 16"),
    ({"headers": ["Api-Version: 1"]}, "at most 16"),
    ({"auth": {"scheme": "header", "header": "X-Vendor-Key"}, "headers": {"x-vendor-key": "1"}}, "credentials"),
])
def test_invalid_auth_and_headers_rejected(overrides, message):
    config = _config(1, **overrides)
    with pytest.raises(ValueError, match=message):
        readback.validate(config, EXTRACT)


def test_auth_requires_token_env():
    config = _config(1, auth={"scheme": "header", "header": "X-Api-Key"})
    config.pop("token_env")
    with pytest.raises(ValueError, match="requires token_env"):
        readback.validate(config, EXTRACT)


def test_auth_and_headers_rejected_for_github_issue():
    base = {"type": "github_issue", "repository": "example/disposable", "issue_number_field": "issue_id",
            "token_env": TOKEN_ENV, "expected_fields": {"title": "title"}}
    for extra in ({"auth": {"scheme": "bearer"}}, {"headers": {"Api-Version": "1"}}):
        with pytest.raises(ValueError, match="only for type http"):
            readback.validate({**base, **extra}, EXTRACT)


def test_invalid_config_sends_no_request(tmp_path):
    with _http() as (port, seen):
        result = _verify(tmp_path, _config(port, headers={"Authorization": "Bearer static"}))
    assert result.returncode == 2 and result.stdout == ""
    assert seen == []


def test_credential_envs_lists_token_and_username():
    assert readback.credential_envs(None) == []
    assert readback.credential_envs({"token_env": "A"}) == ["A"]
    assert readback.credential_envs({"token_env": "A", "auth": {"scheme": "basic", "username_env": "B"}}) == ["A", "B"]


def _scan(tmp_path, port, readback_config, env_extra):
    store = tmp_path / "store.json"
    contract = json.loads(DEMO.read_text())
    contract["server"]["command"] = [sys.executable, str(ROOT / "fixtures" / "outcome_server.py")]
    case = contract["cases"][0]
    case["outcome_contract"] = {"extract": case["outcome_contract"]["extract"], "record_id_field": "issue_id"}
    case["readback"] = {"type": "http", "url_template": f"http://127.0.0.1:{port}/issues/{{issue_id}}",
                        "expected_fields": {"title": "title"}, "missing_statuses": [404],
                        "attempts": 1, "timeout_ms": 1000, **readback_config}
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(contract))
    env = {k: v for k, v in os.environ.items() if k not in (TOKEN_ENV, USER_ENV)}
    env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE="healthy", **env_extra)
    result = subprocess.run([sys.executable, "-m", "fourgate", "scan", str(path),
                             "--confirm-test-account", "disposable-demo"],
                            cwd=ROOT, env=env, text=True, capture_output=True, timeout=12)
    assert TOKEN not in result.stdout and TOKEN not in result.stderr
    return result, json.loads(result.stdout)["cases"][0], store


def test_scan_skips_write_when_basic_username_env_missing(tmp_path):
    with _http() as (port, seen):
        result, row, store = _scan(tmp_path, port, {"token_env": TOKEN_ENV,
                                                    "auth": {"scheme": "basic", "username_env": USER_ENV}},
                                   {TOKEN_ENV: TOKEN})
    assert row["status"] == "UNKNOWN" and row["reason_code"] == "credential_missing"
    assert seen == []
    assert not store.exists(), "a missing read-back credential must skip the write"


def test_scan_header_auth_passes_with_static_headers(tmp_path):
    rb = {"token_env": TOKEN_ENV, "auth": {"scheme": "header", "header": "X-Api-Key"},
          "headers": {"Api-Version": "2024-01-01"}}
    with _http(title="FOURGATE-SCAN-TEST") as (port, seen):
        result, row, _ = _scan(tmp_path, port, rb, {TOKEN_ENV: TOKEN})
    assert seen and seen[0]["x-api-key"] == TOKEN and seen[0]["api-version"] == "2024-01-01"
    assert "authorization" not in seen[0]
    assert result.returncode == 0 and row["status"] == "PASS"
