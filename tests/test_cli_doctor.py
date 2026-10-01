"""`fourgate doctor`: non-destructive preflight for a `fourgate guard` setup.

Proves the safety invariants (no tools/call, no verifier run, no network, no
file written, secret_env withheld, nothing secret printed) and the
OK / WARN / FAIL / SKIP checks.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from fourgate import cli, doctor, readback, verify_http
from wrap import outcome

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "fixtures" / "outcome_server.py"
DEMO_CONTRACTS = ROOT / "fixtures" / "contracts" / "outcome_demo.json"
TOKEN_ENV = "FOURGATE_DOCTOR_TEST_READ_TOKEN"
SECRET = "doctor-secret-sentinel-4b7e"
ARG_SENTINEL = "doctor-arg-sentinel-c21f"
RUN_TIMEOUT = 60
FOOTER_NO_SIDE_EFFECTS = "Fourgate sent no tools/call, ran no verifier, made no network request and wrote no file."
FOOTER_STARTED = ("The server was started only for initialize and tools/list, then stopped. "
                  "Anything the server does on its own at start-up is outside Fourgate's control.")
FOOTER_NOT_STARTED = "The server was not started."
READBACK = {
    "type": "http",
    "url_template": "https://api.example.test/issues/{issue_id}",
    "token_env": TOKEN_ENV,
    "missing_statuses": [404],
    "expected_fields": {"title": "title"},
    "attempts": 3,
    "interval_ms": 250,
    "timeout_ms": 1500,
}


# --- helpers -----------------------------------------------------------------

def _setup(tmp_path, readback_config=READBACK, edit=None, write_readback=True):
    """A runtime contract using the bundled verify_http verifier, plus its readback.json."""
    contract = {
        "extract": {"issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
                    "title": {"source": "arguments", "path": "title"}},
        "verifier": {"command": ["{python}", "-m", "fourgate.verify_http", "readback.json"],
                     "cwd": ".", "timeout_ms": 2000, "secret_env": [TOKEN_ENV]},
        "allowed_failure_reasons": ["record_missing", "field_mismatch"],
        "recovery": "stop",
    }
    data = {"contract_version": 1, "tools": {"create_issue": contract}}
    if edit is not None:
        edit(data)
    if write_readback:
        (tmp_path / "readback.json").write_text(json.dumps(readback_config), encoding="utf-8")
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _custom(command):
    def edit(data):
        verifier = data["tools"]["create_issue"]["verifier"]
        verifier["command"] = command
        del verifier["cwd"], verifier["secret_env"]
    return edit


def _verifier(**changes):
    def edit(data):
        data["tools"]["create_issue"]["verifier"].update(changes)
    return edit


def _doctor(capsys, *args):
    rc = cli.main(["doctor", *map(str, args)])
    out, err = capsys.readouterr()
    return rc, out, err


def _server(*extra):
    return [sys.executable, str(SERVER), *extra]


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv(TOKEN_ENV, SECRET)
    monkeypatch.setenv("FOURGATE_DEMO_STORE", str(tmp_path / "store.json"))
    return monkeypatch


def _snapshot(directory):
    return {p: (p.is_dir(), p.stat().st_size, p.stat().st_mtime_ns) for p in directory.rglob("*")}


def _probe(tmp_path):
    """A wrapper around outcome_server.py that records each JSON-RPC method and its env."""
    methods, env_file = tmp_path / "methods.jsonl", tmp_path / "server_env.json"
    probe = tmp_path / "probe_server.py"
    probe.write_text(
        "import json, os, runpy, sys\n"
        "from pathlib import Path\n"
        f"Path({str(env_file)!r}).write_text(json.dumps({{'secret': {TOKEN_ENV!r} in os.environ}}))\n"
        "class Tap:\n"
        "    def __init__(self, stream): self.stream = stream\n"
        "    def __iter__(self):\n"
        "        for raw in self.stream:\n"
        "            try: method = json.loads(raw).get('method')\n"
        "            except ValueError: method = None\n"
        f"            with open({str(methods)!r}, 'a', encoding='utf-8') as f: f.write(json.dumps(method) + '\\n')\n"
        "            yield raw\n"
        "sys.stdin = Tap(sys.stdin)\n"
        f"runpy.run_path({str(SERVER)!r}, run_name='__main__')\n", encoding="utf-8")
    return [sys.executable, str(probe)], methods, env_file


def _run(args, extra_env=None):
    process_env = os.environ.copy()
    process_env.update(extra_env or {})
    return subprocess.run([sys.executable, "-m", "fourgate", "doctor", *map(str, args)], stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=RUN_TIMEOUT, env=process_env, cwd=ROOT)


# --- happy path and invariants -------------------------------------------------

def test_happy_path_verify_http_is_ready_for_shadow(tmp_path, env, capsys):
    contracts = _setup(tmp_path)
    log = tmp_path / "outcomes.jsonl"
    before = _snapshot(tmp_path)
    rc, out, err = _doctor(capsys, "--contracts", contracts, "--server", "demo", "--log", log, "--", *_server())
    assert rc == 0, out
    assert "Verdict: READY FOR SHADOW (0 warning(s))" in out
    assert "[WARN]" not in out and "[FAIL]" not in out
    for expected in ("[ OK ] bundled HTTP verifier; read-back config readback.json is valid (type http)",
                     "[ OK ] HTTPS read-back to a static host",
                     "[ OK ] redirects are never followed (built in)",
                     f"[ OK ] {TOKEN_ENV} is set",
                     f"[ OK ] create_issue: {TOKEN_ENV} is withheld from the MCP server",
                     "[ OK ] create_issue is advertised by the server",
                     "[ OK ] create_issue: read-back retries are GET only (attempts: 3)",
                     FOOTER_NO_SIDE_EFFECTS, FOOTER_STARTED):
        assert expected in out
    assert err == ""
    assert _snapshot(tmp_path) == before  # nothing created, truncated or modified
    assert not log.exists()


def test_server_receives_only_handshake_messages(tmp_path):
    target, methods, _ = _probe(tmp_path)
    store = tmp_path / "store.json"
    result = _run(["--contracts", DEMO_CONTRACTS, "--", *target], {"FOURGATE_DEMO_STORE": str(store)})
    assert result.returncode == 0, result.stdout
    recorded = [json.loads(line) for line in methods.read_text(encoding="utf-8").splitlines()]
    assert recorded == ["initialize", "notifications/initialized", "tools/list"]
    assert not store.exists()


def test_custom_verifier_is_never_executed(tmp_path, env, capsys):
    marker = tmp_path / "verifier-ran"
    contracts = _setup(tmp_path, edit=_custom(["{python}", "-c", f"open({str(marker)!r}, 'w').close()"]),
                       write_readback=False)
    rc, out, _ = _doctor(capsys, "--contracts", contracts, "--log", tmp_path / "o.jsonl", "--", *_server())
    assert rc == 0, out
    assert not marker.exists()


def test_no_network_and_no_verifier_calls(tmp_path, env, capsys):
    calls = []

    def recorder(name):
        def record(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"doctor called {name}")
        return record

    env.setattr(readback.OPENER, "open", recorder("OPENER.open"))
    env.setattr(urllib.request, "urlopen", recorder("urlopen"))
    env.setattr(socket, "create_connection", recorder("create_connection"))
    env.setattr(socket, "getaddrinfo", recorder("getaddrinfo"))
    env.setattr(subprocess, "run", recorder("subprocess.run"))
    env.setattr(readback, "evaluate_extracted", recorder("readback.evaluate_extracted"))
    env.setattr(outcome, "evaluate", recorder("outcome.evaluate"))
    env.setattr(verify_http, "main", recorder("verify_http.main"))
    contracts = _setup(tmp_path)
    rc, out, _ = _doctor(capsys, "--contracts", contracts, "--log", tmp_path / "o.jsonl", "--", *_server())
    assert rc == 0, out
    assert calls == []


def test_log_is_checked_without_writing(tmp_path, capsys):
    new_log = tmp_path / "logs" / "outcomes.jsonl"
    new_log.parent.mkdir()
    rc, out, _ = _doctor(capsys, "--contracts", DEMO_CONTRACTS, "--log", new_log)
    assert rc == 0, out
    assert f"[ OK ] outcome log {new_log} can be created (directory is writable)" in out
    assert not new_log.exists()

    existing = tmp_path / "existing.jsonl"
    existing.write_text('{"prior": 1}\n', encoding="utf-8")
    before = existing.stat().st_mtime_ns
    rc, out, _ = _doctor(capsys, "--contracts", DEMO_CONTRACTS, "--log", existing)
    assert rc == 0, out
    assert "exists and is writable (guard appends)" in out
    assert existing.read_text(encoding="utf-8") == '{"prior": 1}\n'
    assert existing.stat().st_mtime_ns == before


def test_secret_env_withheld_during_handshake_and_never_printed(tmp_path):
    target, _, env_file = _probe(tmp_path)
    contracts = _setup(tmp_path)
    result = _run(["--contracts", contracts, "--", *target, ARG_SENTINEL],
                  {TOKEN_ENV: SECRET, "FOURGATE_DEMO_STORE": str(tmp_path / "store.json")})
    assert result.returncode == 0, result.stdout
    assert json.loads(env_file.read_text()) == {"secret": False}
    stdout, stderr = result.stdout.decode(), result.stderr.decode()
    assert f"{TOKEN_ENV} is set" in stdout
    assert "(+2 args)" in stdout
    for stream in (stdout, stderr):
        assert SECRET not in stream
        assert ARG_SENTINEL not in stream


# --- FAIL cases ----------------------------------------------------------------

def _fail_invalid_contract(tmp_path, monkeypatch):
    path = tmp_path / "runtime.json"
    path.write_text("{", encoding="utf-8")
    return ["--contracts", path, "--", *_server()], "[FAIL] contract error:"


def _fail_readback_missing(tmp_path, monkeypatch):
    return ["--contracts", _setup(tmp_path, write_readback=False)], "read-back config readback.json cannot be read"


def _fail_readback_http_remote(tmp_path, monkeypatch):
    config = dict(READBACK, url_template="http://api.example.test/issues/{issue_id}")
    return ["--contracts", _setup(tmp_path, config)], "readback.json is invalid: readback URL must be HTTPS"


def _fail_readback_dynamic_host(tmp_path, monkeypatch):
    config = dict(READBACK, url_template="https://{issue_id}.example.test/issues")
    return ["--contracts", _setup(tmp_path, config)], "readback.json is invalid: readback URL must use a static host"


def _fail_secret_unset(tmp_path, monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    return ["--contracts", _setup(tmp_path)], f"[FAIL] {TOKEN_ENV} is not set or empty: read-back would be UNKNOWN"


def _fail_secret_empty(tmp_path, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "")
    return ["--contracts", _setup(tmp_path)], f"[FAIL] {TOKEN_ENV} is not set or empty: read-back would be UNKNOWN"


def _fail_tool_not_discovered(tmp_path, monkeypatch):
    def rename(data):
        data["tools"]["close_issue"] = data["tools"].pop("create_issue")
    return (["--contracts", _setup(tmp_path, edit=rename), "--", *_server()],
            "[FAIL] close_issue is not advertised by the server (tools/list)")


def _fail_server_not_found(tmp_path, monkeypatch):
    return (["--contracts", _setup(tmp_path), "--", "fourgate-no-such-server-binary"],
            "[FAIL] server start failed (FileNotFoundError)")


def _fail_log_parent_missing(tmp_path, monkeypatch):
    return (["--contracts", _setup(tmp_path), "--log", tmp_path / "missing" / "o.jsonl"],
            "is missing or not writable (guard would refuse to start)")


def _fail_custom_verifier_missing(tmp_path, monkeypatch):
    return (["--contracts", _setup(tmp_path, edit=_custom(["fourgate-no-such-verifier"]), write_readback=False)],
            "[FAIL] verifier executable not found: fourgate-no-such-verifier")


def _demo_with_script(tmp_path, script):
    data = json.loads(DEMO_CONTRACTS.read_text(encoding="utf-8"))
    data["tools"]["create_issue"]["verifier"].update(command=["{python}", script], cwd=str(ROOT))
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fail_verifier_script_missing(tmp_path, monkeypatch):
    return (["--contracts", _demo_with_script(tmp_path, "fixtures/no_such_verifier.py")],
            "[FAIL] verifier script not found: no_such_verifier.py")


def _fail_verify_http_no_argument(tmp_path, monkeypatch):
    return (["--contracts", _setup(tmp_path, edit=_verifier(command=["{python}", "-m", "fourgate.verify_http"]))],
            "[FAIL] verify_http command must be: {python} -m fourgate.verify_http <readback-config.json>")


def _fail_verify_http_two_arguments(tmp_path, monkeypatch):
    command = ["{python}", "-m", "fourgate.verify_http", "readback.json", "extra.json"]
    return (["--contracts", _setup(tmp_path, edit=_verifier(command=command))],
            "[FAIL] verify_http command must be: {python} -m fourgate.verify_http <readback-config.json>")


@pytest.mark.parametrize("case", [_fail_invalid_contract, _fail_readback_missing, _fail_readback_http_remote,
                                  _fail_readback_dynamic_host, _fail_secret_unset, _fail_secret_empty,
                                  _fail_tool_not_discovered, _fail_server_not_found, _fail_log_parent_missing,
                                  _fail_custom_verifier_missing, _fail_verifier_script_missing,
                                  _fail_verify_http_no_argument, _fail_verify_http_two_arguments],
                         ids=lambda case: case.__name__[6:])
def test_fail_cases_are_not_ready(tmp_path, env, capsys, case):
    args, expected = case(tmp_path, env)
    rc, out, _ = _doctor(capsys, *args)
    assert rc == 1, out
    assert expected in out
    assert "Verdict: NOT READY:" in out
    assert "READY FOR SHADOW" not in out
    assert out.isascii()


def test_invalid_contract_skips_every_later_check(tmp_path, capsys):
    args, _ = _fail_invalid_contract(tmp_path, None)
    rc, out, _ = _doctor(capsys, *args)
    assert rc == 1
    assert out.count("[SKIP] contract is invalid") == len(doctor.LATER_SECTIONS)
    assert FOOTER_NOT_STARTED in out
    assert "Verdict: NOT READY: 1 problem(s)" in out


# --- WARN cases ----------------------------------------------------------------

def _allow(*reasons):
    def edit(data):
        data["tools"]["create_issue"]["allowed_failure_reasons"] = list(reasons)
    return edit


WARN_CASES = [pytest.param(build, expected, id=name) for name, build, expected in [
    ("record_missing_without_missing_statuses",
     lambda p: [_setup(p, dict(READBACK, missing_statuses=[]))],
     "record_missing is allowed but missing_statuses is not set: a missing record can only ever be UNKNOWN"),
    ("missing_statuses_without_record_missing",
     lambda p: [_setup(p, edit=_allow("field_mismatch"))],
     "missing_statuses is set but record_missing is not in allowed_failure_reasons"),
    ("github_record_missing_without_missing_is_fail",
     lambda p: [_setup(p, {"type": "github_issue", "repository": "octo/repo", "issue_number_field": "issue_id",
                           "expected_fields": {"title": "title"}, "token_env": TOKEN_ENV,
                           "timeout_ms": 1500})],
     "record_missing is allowed but missing_is_fail is not set"),
    ("budget_over_verifier_timeout_minus_headroom",
     lambda p: [_setup(p, dict(READBACK, timeout_ms=1800))],
     "read-back timeout_ms 1800 leaves under 300 ms of the 2000 ms verifier timeout"),
    ("retry_spacing_exceeds_budget",
     lambda p: [_setup(p, dict(READBACK, attempts=5, interval_ms=500))],
     "retry spacing (4 x 500 ms) uses the whole 1500 ms read-back budget"),
    ("read_credential_not_in_secret_env",
     lambda p: [_setup(p, edit=_verifier(secret_env=[]))],
     f"create_issue: {TOKEN_ENV} is visible to the MCP server (add it to secret_env)"),
    ("custom_verifier",
     lambda p: [DEMO_CONTRACTS],
     "custom verifier: Fourgate cannot inspect what it reads or which credentials it uses"),
    ("enforce_mode",
     lambda p: [_setup(p), "--mode", "enforce"],
     "enforce requested; run shadow until shadow results are clean"),
    ("no_log",
     lambda p: [_setup(p)],
     "no --log: outcomes go to stderr, which MCP clients usually discard; fourgate summary needs a log file"),
]]


@pytest.mark.parametrize("build,expected", WARN_CASES)
def test_warn_cases_are_still_ready_for_shadow(tmp_path, env, capsys, build, expected):
    contracts, *rest = build(tmp_path)
    rc, out, _ = _doctor(capsys, "--contracts", contracts, *rest)
    assert rc == 0, out
    assert f"[WARN] {expected}" in out
    assert "Verdict: READY FOR SHADOW (" in out
    assert "[FAIL]" not in out
    assert "ready for enforce" not in out.lower()


def test_malformed_verify_http_command_skips_custom_checks(tmp_path, env, capsys):
    contracts = _setup(tmp_path, edit=_verifier(command=["{python}", "-m", "fourgate.verify_http"]))
    rc, out, _ = _doctor(capsys, "--contracts", contracts, "--log", tmp_path / "o.jsonl")
    assert rc == 1
    assert "custom verifier:" not in out and "verifier executable" not in out
    assert "Verdict: NOT READY: 1 problem(s)" in out


def test_demo_fixture_is_ready_and_its_script_is_found(capsys):
    rc, out, _ = _doctor(capsys, "--contracts", DEMO_CONTRACTS, "--", *_server())
    assert rc == 0, out
    assert "[ OK ] verifier script found: outcome_verifier.py" in out
    assert "Verdict: READY FOR SHADOW (2 warning(s))" in out


def test_footer_states_whether_the_server_was_started(tmp_path, capsys):
    rc, out, _ = _doctor(capsys, "--contracts", DEMO_CONTRACTS, "--", *_server())
    assert rc == 0, out
    assert out.rstrip().splitlines()[-3:-1] == [FOOTER_NO_SIDE_EFFECTS, FOOTER_STARTED]
    assert FOOTER_NOT_STARTED not in out
    rc, out, _ = _doctor(capsys, "--contracts", DEMO_CONTRACTS)
    assert rc == 0, out
    assert out.rstrip().splitlines()[-3:-1] == [FOOTER_NO_SIDE_EFFECTS, FOOTER_NOT_STARTED]
    assert "started only for initialize" not in out


def test_info_lines_are_not_counted(tmp_path, env, capsys):
    rc, out, _ = _doctor(capsys, "--contracts", _setup(tmp_path, edit=_verifier(secret_env=[])), "--mode", "enforce")
    assert rc == 0, out
    assert "[INFO] Fourgate cannot verify the read credential is read-only or valid" in out
    assert "[INFO] the verifier process inherits the full environment" in out
    assert "[ OK ] Fourgate cannot verify" not in out and "[WARN] Fourgate cannot verify" not in out
    warnings = out.count("[WARN]")
    assert warnings == 3  # credential visible to the server, enforce, no --log
    assert f"Verdict: READY FOR SHADOW ({warnings} warning(s))" in out


def test_loopback_http_is_reported(tmp_path, env, capsys):
    config = dict(READBACK, url_template="http://127.0.0.1:8080/issues/{issue_id}")
    rc, out, _ = _doctor(capsys, "--contracts", _setup(tmp_path, config))
    assert rc == 0, out
    assert "[ OK ] HTTP to loopback only" in out


def test_verify_http_detection():
    assert doctor.verify_http_config_arg(["{python}", "-m", "fourgate.verify_http", "rb.json"]) == "rb.json"
    assert doctor.verify_http_config_arg(["python3", "-m", "fourgate.verify_http", "a", "b"]) is None
    assert doctor.verify_http_config_arg(["{python}", "-m", "fourgate.verify_http"]) is None
    assert doctor.verify_http_config_arg(["{python}", "-m", "other.module", "rb.json"]) is None
    assert doctor.verify_http_config_arg(["{python}", "fourgate/verify_http.py", "rb.json"]) is None
    assert doctor.invokes_verify_http(["{python}", "-m", "fourgate.verify_http"])
    assert doctor.invokes_verify_http(["python3", "-m", "fourgate.verify_http", "a", "b"])
    assert not doctor.invokes_verify_http(["{python}", "fourgate/verify_http.py", "rb.json"])
    assert not doctor.invokes_verify_http(["{python}", "-m"])


# --- SKIP, usage, output -------------------------------------------------------

def test_without_server_command_mcp_checks_skip(tmp_path, env, capsys):
    rc, out, _ = _doctor(capsys, "--contracts", _setup(tmp_path), "--log", tmp_path / "o.jsonl")
    assert rc == 0, out
    assert "[SKIP] pass the server command after -- to check the handshake and tool discovery" in out
    assert "target: none" in out
    assert FOOTER_NOT_STARTED in out


@pytest.mark.parametrize("args", [
    ["--contracts", DEMO_CONTRACTS, "--bogus"],
    ["--contracts", DEMO_CONTRACTS, "--mode", "block"],
    ["--contracts", DEMO_CONTRACTS, "--server", "a/b"],
    ["--contracts", DEMO_CONTRACTS, "--baseline", DEMO_CONTRACTS],
    ["--mode", "shadow"],
    ["--contracts", DEMO_CONTRACTS, "--"],
], ids=["unknown_flag", "bad_mode", "bad_label", "baseline_not_exposed", "missing_contracts", "empty_target"])
def test_usage_errors_exit_2(capsys, args):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["doctor", *map(str, args)])
    assert excinfo.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert "fourgate doctor: error:" in err


def test_output_is_ascii_even_for_non_ascii_paths(tmp_path, env, capsys):
    folder = tmp_path / "caf\u00e9-\u2713"
    folder.mkdir()
    contracts = _setup(folder)
    rc, out, _ = _doctor(capsys, "--contracts", contracts, "--log", folder / "o.jsonl", "--", *_server())
    assert rc == 0, out
    assert out.isascii()
    rc, out, _ = _doctor(capsys, "--contracts", folder / "missing.json")
    assert rc == 1 and out.isascii()


@pytest.mark.skipif(shutil.which("fourgate") is None, reason="fourgate is not installed on PATH")
def test_installed_entry_point_end_to_end():
    result = subprocess.run([shutil.which("fourgate"), "doctor", "--contracts", str(DEMO_CONTRACTS), "--",
                             sys.executable, str(SERVER)], stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=RUN_TIMEOUT, cwd=ROOT)
    assert result.returncode == 0, result.stdout
    assert b"Verdict: READY FOR SHADOW" in result.stdout
