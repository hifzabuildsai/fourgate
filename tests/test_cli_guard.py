"""`fourgate guard`: the installed-CLI entry point for the runtime Outcome Guard.

Startup fails closed (strict contracts, strict argv, target never spawned on
error); per call the existing wrap.py runtime is unchanged and fails open.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from _support import ScriptedSession, run_initialize
from fourgate import cli
from wrap import outcome

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "fixtures" / "outcome_server.py"
VERIFIER = ROOT / "fixtures" / "outcome_verifier.py"
CONTRACTS = ROOT / "fixtures" / "contracts" / "outcome_demo.json"
MARKER = "[FOURGATE]"
RUN_TIMEOUT = 60
SECRET_ENV = "FOURGATE_GUARD_TEST_READ_TOKEN"
SECRET = "guard-secret-sentinel-5d1e"
ARG_SENTINEL = "guard-arg-sentinel-77ab"
UNSET_ENV = "FOURGATE_GUARD_TEST_UNSET_TOKEN"


# --- helpers -----------------------------------------------------------------

def _guard(*options, target):
    return [sys.executable, "-m", "fourgate", "guard", *map(str, options), "--", *map(str, target)]


def _server(*extra):
    return [sys.executable, str(SERVER), *extra]


def _env(store, server_mode="broken", verifier_mode="normal", **extra):
    env = os.environ.copy()
    env.pop(UNSET_ENV, None)
    env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE=server_mode,
               FOURGATE_DEMO_VERIFIER=verifier_mode, **extra)
    return env


class GuardSession(ScriptedSession):
    """ScriptedSession that keeps stderr instead of discarding it."""

    def __init__(self, cmd, env=None):
        self.stderr_bytes = bytearray()
        super().__init__(cmd, env=env)

    def _drain_stderr(self):
        try:
            for line in iter(self.proc.stderr.readline, b""):
                self.stderr_bytes.extend(line)
        except (OSError, ValueError):
            pass

    def close(self):
        captured = super().close()
        self._stderr_drain.join(timeout=5)
        return captured


CREATE = ("create_issue", {"title": "CANARY-TITLE-do-not-log"})
UNCONTRACTED = ("list_issues", {})


def _session(cmd, env, calls=(CREATE,)):
    """initialize, tools/list, then each tools/call. Returns (responses, stdout bytes, stderr text)."""
    s = GuardSession(cmd, env=env)
    try:
        run_initialize(s)
        assert "result" in s.send_request("tools/list", {})
        responses = [s.send_request("tools/call", {"name": name, "arguments": args}) for name, args in calls]
        captured = s.close()
    finally:
        if s.proc.poll() is None:
            s.proc.kill()
    return responses, captured, bytes(s.stderr_bytes).decode("utf-8", "replace")


def _verdict(response):
    text = response["result"]["content"][0]["text"]
    assert text.startswith(MARKER)
    return json.loads(text[len(MARKER):].strip())


def _records(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run(args, env=None, cwd=None, stdin=b""):
    return subprocess.run([sys.executable, "-m", "fourgate", "guard", *map(str, args)], input=stdin,
                          capture_output=True, timeout=RUN_TIMEOUT, env=env, cwd=cwd)


def _marker_target(tmp_path):
    """A target that only proves it ran, by creating a file."""
    marker = tmp_path / "target-ran"
    return [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"], marker


def _contract(**verifier):
    spec = {"command": ["{python}", str(VERIFIER)], "timeout_ms": 1000, **verifier}
    return {"contract_version": 1, "tools": {"create_issue": {
        "extract": {"issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
                    "title": {"source": "arguments", "path": "title"}},
        "verifier": spec,
        "allowed_failure_reasons": ["record_missing", "field_mismatch"],
        "recovery": "stop"}}}


def _write(tmp_path, content, name="contracts.json"):
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    elif content is not None:
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


def _secret_contract(tmp_path, secret_env):
    """Verifier PASSes only when it can read SECRET_ENV's exact value."""
    verifier = tmp_path / "secret_verifier.py"
    verifier.write_text("import json, os\n"
                        f"seen = os.environ.get({SECRET_ENV!r}) == {SECRET!r}\n"
                        "print(json.dumps({'status': 'pass'} if seen else "
                        "{'status': 'fail', 'reason_code': 'record_missing'}))\n", encoding="utf-8")
    data = _contract(command=["{python}", str(verifier)], timeout_ms=2000, secret_env=secret_env)
    return _write(tmp_path, data)


# --- fail-closed rejection matrix ----------------------------------------------

_DELETE = object()
_TOOL = ("tools", "create_issue")
_VERIFIER = _TOOL + ("verifier",)
_SELECTOR = _TOOL + ("extract", "issue_id")
_TEXT = {"source": "result", "path": "result.content.0.text"}


def _at(path, value=_DELETE):
    def build():
        data = _contract()
        node = data
        for key in path[:-1]:
            node = node[key]
        if value is _DELETE:
            del node[path[-1]]
        else:
            node[path[-1]] = value
        return data
    return build


CONTRACT_CASES = [pytest.param(build, id=name) for name, build in [
    ("unreadable_file", lambda: None),
    ("invalid_json", lambda: "{not json"),
    ("not_utf8", lambda: b"\xff\xfe{}"),
    ("top_level_list", lambda: "[]"),
    ("version_missing", _at(("contract_version",))),
    ("version_2", _at(("contract_version",), 2)),
    ("version_true", _at(("contract_version",), True)),
    ("version_string", _at(("contract_version",), "1")),
    ("tools_missing", _at(("tools",))),
    ("tools_not_object", _at(("tools",), [])),
    ("tools_empty", _at(("tools",), {})),
    ("tool_name_empty", _at(("tools",), {"": _contract()["tools"]["create_issue"]})),
    ("contract_not_object", _at(_TOOL, "create")),
    ("extract_missing", _at(_TOOL + ("extract",))),
    ("extract_empty", _at(_TOOL + ("extract",), {})),
    ("extract_not_object", _at(_TOOL + ("extract",), [])),
    ("selector_not_object", _at(_SELECTOR, "issue_id")),
    ("selector_bad_source", _at(_SELECTOR + ("source",), "env")),
    ("selector_path_missing", _at(_SELECTOR + ("path",))),
    ("selector_path_not_string", _at(_SELECTOR + ("path",), 3)),
    ("selector_bad_regex", _at(_SELECTOR, {**_TEXT, "parse": "regex", "pattern": "("})),
    ("selector_regex_no_group", _at(_SELECTOR, {**_TEXT, "parse": "regex", "pattern": "ISSUE-1"})),
    ("selector_bad_parse_mode", _at(_SELECTOR, {**_TEXT, "parse": "xml"})),
    ("selector_parse_wrong_path", _at(_SELECTOR, {"source": "arguments", "path": "title", "parse": "regex",
                                                  "pattern": "(.+)"})),
    ("selector_embedded_json_no_field", _at(_SELECTOR, {**_TEXT, "parse": "embedded_json"})),
    ("verifier_missing", _at(_VERIFIER)),
    ("verifier_not_object", _at(_VERIFIER, "python verify.py")),
    ("command_missing", _at(_VERIFIER + ("command",))),
    ("command_empty", _at(_VERIFIER + ("command",), [])),
    ("command_string", _at(_VERIFIER + ("command",), "python")),
    ("command_non_string", _at(_VERIFIER + ("command",), ["python", 1])),
    ("timeout_missing", _at(_VERIFIER + ("timeout_ms",))),
    ("timeout_bool", _at(_VERIFIER + ("timeout_ms",), True)),
    ("timeout_string", _at(_VERIFIER + ("timeout_ms",), "1000")),
    ("timeout_float", _at(_VERIFIER + ("timeout_ms",), 1000.0)),
    ("timeout_zero", _at(_VERIFIER + ("timeout_ms",), 0)),
    ("timeout_over_cap", _at(_VERIFIER + ("timeout_ms",), 2001)),
    ("cwd_not_string", _at(_VERIFIER + ("cwd",), 5)),
    ("cwd_not_a_directory", _at(_VERIFIER + ("cwd",), "no-such-directory")),
    ("secret_env_not_list", _at(_VERIFIER + ("secret_env",), SECRET_ENV)),
    ("secret_env_bad_name", _at(_VERIFIER + ("secret_env",), ["1LEADING_DIGIT"])),
    ("secret_env_null", _at(_VERIFIER + ("secret_env",), None)),
    ("allowed_missing", _at(_TOOL + ("allowed_failure_reasons",))),
    ("allowed_empty", _at(_TOOL + ("allowed_failure_reasons",), [])),
    ("allowed_string", _at(_TOOL + ("allowed_failure_reasons",), "record_missing")),
    ("allowed_blank", _at(_TOOL + ("allowed_failure_reasons",), [""])),
    ("allowed_non_string", _at(_TOOL + ("allowed_failure_reasons",), [1])),
    ("recovery_unknown", _at(_TOOL + ("recovery",), "explode")),
    ("recovery_null", _at(_TOOL + ("recovery",), None)),
    ("recovery_list", _at(_TOOL + ("recovery",), ["stop"])),
]]


@pytest.mark.parametrize("build", CONTRACT_CASES)
def test_load_strict_rejects(tmp_path, capsys, build):
    path = _write(tmp_path, build())
    with pytest.raises(ValueError):
        outcome.load_strict(str(path))
    assert capsys.readouterr() == ("", "")  # side-effect free: no output


@pytest.mark.parametrize("build", CONTRACT_CASES)
def test_invalid_contract_fails_closed_without_starting_target(tmp_path, build):
    target, marker = _marker_target(tmp_path)
    result = _run(["--contracts", _write(tmp_path, build()), "--", *target])
    assert result.returncode == 2, result.stderr
    assert result.stderr.startswith(b"fourgate guard: contract error: ")
    assert result.stdout == b""
    assert not marker.exists()


USAGE_CASES = [pytest.param(build, id=name) for name, build in [
    ("missing_contracts", lambda c, t: ["--", *t]),
    ("missing_separator", lambda c, t: ["--contracts", c, *t]),
    ("missing_separator_no_target", lambda c, t: ["--contracts", c]),
    ("empty_target", lambda c, t: ["--contracts", c, "--"]),
    ("invalid_mode", lambda c, t: ["--contracts", c, "--mode", "block", "--", *t]),
    ("mode_wrong_case", lambda c, t: ["--contracts", c, "--mode", "Enforce", "--", *t]),
    ("label_with_space", lambda c, t: ["--contracts", c, "--server", "my server", "--", *t]),
    ("label_with_slash", lambda c, t: ["--contracts", c, "--server", "a/b", "--", *t]),
    ("label_too_long", lambda c, t: ["--contracts", c, "--server", "x" * 65, "--", *t]),
    ("label_empty", lambda c, t: ["--contracts", c, "--server", "", "--", *t]),
    ("unknown_flag", lambda c, t: ["--contracts", c, "--bogus", "--", *t]),
    ("baseline_not_exposed", lambda c, t: ["--contracts", c, "--baseline", c, "--", *t]),
    ("observe_not_exposed", lambda c, t: ["--contracts", c, "--observe", "obs.jsonl", "--", *t]),
    ("abbreviated_flag", lambda c, t: ["--contract", c, "--", *t]),
    ("stray_positional", lambda c, t: ["--contracts", c, "extra", "--", *t]),
]]


@pytest.mark.parametrize("build", USAGE_CASES)
def test_usage_errors_fail_closed_without_starting_target(tmp_path, build):
    target, marker = _marker_target(tmp_path)
    result = _run(build(str(CONTRACTS), target))
    assert result.returncode == 2, result.stderr
    assert b"fourgate guard: error:" in result.stderr
    assert result.stdout == b""
    assert not marker.exists()


def test_valid_contract_starts_target(tmp_path):
    # Control for the matrices above: the marker target does run when nothing is wrong.
    target, marker = _marker_target(tmp_path)
    result = _run(["--contracts", CONTRACTS, "--", *target])
    assert result.returncode == 0, result.stderr
    assert marker.exists()


# --- load_strict unit tests ----------------------------------------------------

def test_load_strict_accepts_demo_contract_with_same_shape_as_load():
    strict = outcome.load_strict(str(CONTRACTS))
    assert strict == outcome.load(str(CONTRACTS))
    assert strict["_contract_dir"] == os.path.dirname(os.path.abspath(CONTRACTS))


@pytest.mark.parametrize("timeout_ms,ok", [(True, False), ("1000", False), (0, False), (1, True),
                                           (2000, True), (2001, False)])
def test_load_strict_timeout_bounds(tmp_path, timeout_ms, ok):
    path = _write(tmp_path, _contract(timeout_ms=timeout_ms))
    if ok:
        assert outcome.load_strict(str(path))["tools"]["create_issue"]["verifier"]["timeout_ms"] == timeout_ms
    else:
        with pytest.raises(ValueError, match="timeout_ms"):
            outcome.load_strict(str(path))


def test_load_strict_ignores_keys_evaluate_ignores(tmp_path):
    data = _contract(notes="reviewed", secret_env=[SECRET_ENV])
    data["description"] = "runtime contracts"
    data["tools"]["create_issue"]["description"] = "approved by ops"
    del data["tools"]["create_issue"]["recovery"]  # evaluate defaults to stop
    assert outcome.load_strict(str(_write(tmp_path, data)))["tools"]["create_issue"]["verifier"]["notes"] == "reviewed"


def test_load_strict_resolves_cwd_relative_to_contract_file(tmp_path):
    (tmp_path / "verifiers").mkdir()
    nested = tmp_path / "config"
    nested.mkdir()
    assert outcome.load_strict(str(_write(nested, _contract(cwd="../verifiers"))))
    with pytest.raises(ValueError, match="cwd"):
        outcome.load_strict(str(_write(nested, _contract(cwd="verifiers"))))


def test_load_strict_names_tool_and_field_without_echoing_values(tmp_path):
    data = _contract(timeout_ms="VALUE-SENTINEL-3f9")
    data["tools"]["send-email"] = data["tools"].pop("create_issue")
    with pytest.raises(ValueError) as excinfo:
        outcome.load_strict(str(_write(tmp_path, data)))
    message = str(excinfo.value)
    assert 'tools["send-email"].verifier.timeout_ms' in message
    assert "VALUE-SENTINEL-3f9" not in message

    data = _contract()
    data["tools"]["create_issue"]["extract"]["issue_id"]["source"] = "SOURCE-SENTINEL-8c2"
    with pytest.raises(ValueError) as excinfo:
        outcome.load_strict(str(_write(tmp_path, data)))
    assert 'tools["create_issue"].extract["issue_id"].source' in str(excinfo.value)
    assert "SOURCE-SENTINEL-8c2" not in str(excinfo.value)


# --- runtime behavior through guard --------------------------------------------

def test_default_mode_is_shadow_and_byte_identical(tmp_path):
    log = tmp_path / "outcomes.jsonl"
    direct, direct_bytes, _ = _session(_server(), _env(tmp_path / "direct.json"))
    guarded, guarded_bytes, err = _session(
        _guard("--contracts", CONTRACTS, "--server", "demo", "--log", log, target=_server()),
        _env(tmp_path / "guarded.json"))
    assert guarded == direct
    assert guarded_bytes == direct_bytes
    assert MARKER not in guarded[0]["result"]["content"][0]["text"]
    [record] = _records(log)
    assert (record["mode"], record["status"], record["reason_code"]) == ("shadow", "fail", "record_missing")
    assert (record["server"], record["tool"]) == ("demo", "create_issue")
    assert "mode: shadow" in err


def test_enforce_prepends_verdict_on_broken_write(tmp_path):
    [response], _, err = _session(
        _guard("--contracts", CONTRACTS, "--mode", "enforce", "--server", "demo", target=_server()),
        _env(tmp_path / "issues.json"))
    assert _verdict(response) == {
        "kind": "outcome_failed",
        "tool": "demo/create_issue",
        "evidence": {"reason_code": "record_missing", "checked_fields": ["issue_id", "title"]},
        "recovery": "stop",
    }
    assert response["result"]["content"][1]["text"] == "Created ISSUE-001"
    assert response["result"]["structuredContent"] == {"issue_id": "ISSUE-001"}
    assert "mode: enforce" in err


def test_enforce_leaves_healthy_write_unchanged(tmp_path):
    direct, direct_bytes, _ = _session(_server(), _env(tmp_path / "direct.json", "healthy"))
    guarded, guarded_bytes, _ = _session(
        _guard("--contracts", CONTRACTS, "--mode", "enforce", target=_server()),
        _env(tmp_path / "guarded.json", "healthy"))
    assert guarded == direct
    assert guarded_bytes == direct_bytes


def test_full_session_is_byte_identical_including_uncontracted_tool(tmp_path):
    calls = (CREATE, UNCONTRACTED, CREATE)
    direct, direct_bytes, _ = _session(_server(), _env(tmp_path / "direct.json"), calls)
    guarded, guarded_bytes, _ = _session(
        _guard("--contracts", CONTRACTS, "--log", tmp_path / "log.jsonl", target=_server()),
        _env(tmp_path / "guarded.json"), calls)
    assert guarded[1]["result"]["isError"] is True
    assert guarded == direct
    assert guarded_bytes == direct_bytes
    assert len(_records(tmp_path / "log.jsonl")) == 2  # only the contracted tool is recorded


def test_stdout_carries_only_server_traffic(tmp_path):
    _, captured, err = _session(_guard("--contracts", CONTRACTS, target=_server()), _env(tmp_path / "s.json"))
    first = captured.split(b"\n", 1)[0]
    assert first.startswith(b"{")
    assert json.loads(first)["result"]["serverInfo"]["name"] == "outcome-demo-server"
    for line in captured.splitlines():
        assert "jsonrpc" in json.loads(line)
    assert b"fourgate guard" not in captured and b"FOURGATE_OUTCOME" not in captured
    assert err.startswith("fourgate guard ")
    assert "[FOURGATE_OUTCOME]" in err  # no --log: records go to stderr, as with wrap.py


def test_target_argv_is_passed_verbatim(tmp_path):
    echo = tmp_path / "echo_argv.py"
    echo.write_text("import json, sys\nopen(sys.argv[1], 'w').write(json.dumps(sys.argv[2:]))\n", encoding="utf-8")
    out = tmp_path / "argv.json"
    passed = ["--mode", "enforce", "--contracts", "x", "--", "y"]
    result = _run(["--contracts", CONTRACTS, "--", sys.executable, echo, out, *passed])
    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text()) == passed
    stderr = result.stderr.decode()
    assert "mode: shadow" in stderr
    assert f"target: {os.path.basename(sys.executable)} (+8 args)" in stderr


def test_no_secret_or_target_argument_leaks(tmp_path):
    contracts = _secret_contract(tmp_path, [SECRET_ENV])
    [response], captured, err = _session(
        _guard("--contracts", contracts, "--mode", "enforce", target=_server(ARG_SENTINEL)),
        _env(tmp_path / "issues.json", **{SECRET_ENV: SECRET}))
    assert MARKER not in response["result"]["content"][0]["text"]  # verifier saw the secret: PASS
    assert f"{SECRET_ENV} (set)" in err
    for stream in (captured.decode("utf-8", "replace"), err):
        assert SECRET not in stream
        assert ARG_SENTINEL not in stream


def test_secret_env_withheld_from_server_but_reaches_verifier(tmp_path):
    marker = tmp_path / "server_env.json"
    probe = tmp_path / "probe_server.py"
    probe.write_text("import json, os, runpy\n"
                     "from pathlib import Path\n"
                     f"Path({str(marker)!r}).write_text(json.dumps({{"
                     f"'secret': {SECRET_ENV!r} in os.environ, "
                     "'store': 'FOURGATE_DEMO_STORE' in os.environ}))\n"
                     f"runpy.run_path({str(SERVER)!r}, run_name='__main__')\n", encoding="utf-8")
    log = tmp_path / "outcomes.jsonl"
    _session(_guard("--contracts", _secret_contract(tmp_path, [SECRET_ENV]), "--log", log,
                    target=[sys.executable, probe]),
             _env(tmp_path / "issues.json", **{SECRET_ENV: SECRET}))
    assert json.loads(marker.read_text()) == {"secret": False, "store": True}
    [record] = _records(log)
    assert (record["status"], record["reason_code"]) == ("pass", "postcondition_satisfied")


def test_missing_secret_env_warns_and_still_launches(tmp_path):
    target, marker = _marker_target(tmp_path)
    result = _run(["--contracts", _secret_contract(tmp_path, [UNSET_ENV]), "--", *target],
                  env=_env(tmp_path / "issues.json"))
    assert result.returncode == 0, result.stderr
    assert marker.exists()
    stderr = result.stderr.decode()
    assert f"{UNSET_ENV} (NOT SET" in stderr
    assert f"WARNING: {UNSET_ENV} is not set" in stderr


@pytest.mark.parametrize("verifier_mode,reason", [("crash", "verifier_error"), ("hang", "verifier_timeout"),
                                                  ("malformed", "verifier_malformed")])
def test_enforce_fails_open_on_verifier_faults(tmp_path, verifier_mode, reason):
    log = tmp_path / "outcomes.jsonl"
    direct, direct_bytes, _ = _session(_server(), _env(tmp_path / "direct.json"))
    guarded, guarded_bytes, _ = _session(
        _guard("--contracts", CONTRACTS, "--mode", "enforce", "--log", log, target=_server()),
        _env(tmp_path / "guarded.json", verifier_mode=verifier_mode))
    assert guarded == direct
    assert guarded_bytes == direct_bytes
    [record] = _records(log)
    assert (record["mode"], record["status"], record["reason_code"]) == ("enforce", "unknown", reason)


def test_relative_log_is_resolved_and_accepted_by_summary(tmp_path, capsys):
    requests = b"".join(json.dumps(msg).encode() + b"\n" for msg in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "create_issue", "arguments": {"title": "t"}}},
    ])
    env = _env(tmp_path / "issues.json", PYTHONPATH=str(ROOT))
    result = _run(["--contracts", CONTRACTS, "--server", "demo", "--log", "outcomes.jsonl", "--",
                   sys.executable, SERVER], env=env, cwd=tmp_path, stdin=requests)
    assert result.returncode == 0, result.stderr
    log = tmp_path / "outcomes.jsonl"
    [banner_path] = [line.split("outcome log: ", 1)[1].strip()
                     for line in result.stderr.decode().splitlines() if "outcome log: " in line]
    assert Path(banner_path).is_absolute() and Path(banner_path).samefile(log)

    out = tmp_path / "summary.html"
    assert cli.main(["summary", str(log), "--out", str(out), "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["calls"] == 1 and summary["totals"]["fail"] == 1
    assert summary["servers"] == ["demo"] and summary["modes"] == ["shadow"]
    assert out.exists()


@pytest.mark.skipif(shutil.which("fourgate") is None, reason="fourgate is not installed on PATH")
def test_installed_entry_point_end_to_end(tmp_path):
    cmd = [shutil.which("fourgate"), "guard", "--contracts", str(CONTRACTS), "--mode", "enforce",
           "--server", "demo", "--", sys.executable, str(SERVER)]
    [response], _, _ = _session(cmd, _env(tmp_path / "issues.json"))
    assert _verdict(response)["kind"] == "outcome_failed"
    assert response["result"]["content"][1]["text"] == "Created ISSUE-001"
