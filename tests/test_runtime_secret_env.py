"""verifier.secret_env keeps verifier-only credentials out of the wrapped server."""
import json
import os
import sys
from pathlib import Path

import pytest

from _support import ScriptedSession, run_initialize
from wrap import outcome

ROOT = Path(__file__).resolve().parent.parent
WRAP = ROOT / "wrap" / "wrap.py"
SERVER = ROOT / "fixtures" / "outcome_server.py"
SECRET_ENV = "FOURGATE_RUNTIME_READ_TEST_TOKEN"
SECRET = "local-fake-runtime-read-token-91c4"


def _probe_server(tmp_path):
    """Records which variables the wrapped server inherited, then runs the demo server."""
    marker = tmp_path / "server_env.json"
    probe = tmp_path / "probe_server.py"
    probe.write_text("import json, os, runpy, sys\n"
                     "from pathlib import Path\n"
                     f"Path({str(marker)!r}).write_text(json.dumps({{"
                     f"'secret': {SECRET_ENV!r} in os.environ, "
                     "'store': 'FOURGATE_DEMO_STORE' in os.environ}))\n"
                     f"runpy.run_path({str(SERVER)!r}, run_name='__main__')\n", encoding="utf-8")
    return [sys.executable, str(probe)], marker


def _contracts(tmp_path, secret_env=None):
    # PASS only when the verifier itself can read the secret's exact value.
    verifier = tmp_path / "secret_verifier.py"
    verifier.write_text("import json, os\n"
                        f"seen = os.environ.get({SECRET_ENV!r}) == {SECRET!r}\n"
                        "print(json.dumps({'status': 'pass'} if seen else "
                        "{'status': 'fail', 'reason_code': 'record_missing'}))\n", encoding="utf-8")
    spec = {"command": ["{python}", str(verifier)], "timeout_ms": 2000}
    if secret_env is not None:
        spec["secret_env"] = secret_env
    path = tmp_path / "contracts.json"
    path.write_text(json.dumps({"contract_version": 1, "tools": {"create_issue": {
        "extract": {"issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
                    "title": {"source": "arguments", "path": "title"}},
        "verifier": spec,
        "allowed_failure_reasons": ["record_missing"],
        "recovery": "stop"}}}), encoding="utf-8")
    return path


def _run(cmd, store):
    env = os.environ.copy()
    env.update(FOURGATE_DEMO_STORE=str(store), FOURGATE_DEMO_MODE="broken")
    env[SECRET_ENV] = SECRET
    session = ScriptedSession(cmd, env=env)
    try:
        run_initialize(session)
        assert "result" in session.send_request("tools/list", {})
        response = session.send_request("tools/call", {"name": "create_issue", "arguments": {"title": "t"}})
        captured = session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()
    return response, captured


def _shadow(tmp_path, contracts, server_cmd, log):
    return [sys.executable, str(WRAP), "--outcome-contracts", str(contracts), "--outcome-mode", "shadow",
            "--outcome-log", str(log), "--server-label", "demo", "--"] + server_cmd


def test_listed_secret_is_withheld_from_server_but_reaches_verifier(tmp_path):
    server_cmd, marker = _probe_server(tmp_path)
    log = tmp_path / "outcomes.jsonl"
    direct, direct_bytes = _run(server_cmd, tmp_path / "direct.json")
    marker.unlink()
    shadow, shadow_bytes = _run(_shadow(tmp_path, _contracts(tmp_path, [SECRET_ENV]), server_cmd, log),
                                tmp_path / "shadow.json")
    assert json.loads(marker.read_text()) == {"secret": False, "store": True}
    record = json.loads(log.read_text(encoding="utf-8").strip())
    assert (record["status"], record["reason_code"]) == ("pass", "postcondition_satisfied")
    assert shadow == direct
    assert shadow_bytes == direct_bytes
    assert SECRET not in log.read_text(encoding="utf-8")


def test_without_secret_env_server_environment_is_unchanged(tmp_path):
    server_cmd, marker = _probe_server(tmp_path)
    log = tmp_path / "outcomes.jsonl"
    direct, direct_bytes = _run(server_cmd, tmp_path / "direct.json")
    marker.unlink()
    shadow, shadow_bytes = _run(_shadow(tmp_path, _contracts(tmp_path), server_cmd, log), tmp_path / "shadow.json")
    assert json.loads(marker.read_text()) == {"secret": True, "store": True}
    assert json.loads(log.read_text(encoding="utf-8").strip())["status"] == "pass"
    assert shadow == direct and shadow_bytes == direct_bytes


@pytest.mark.skipif(os.name != "nt", reason="Windows env names are case-insensitive")
def test_secret_env_matches_any_casing_on_windows(tmp_path):
    server_cmd, marker = _probe_server(tmp_path)
    _run(_shadow(tmp_path, _contracts(tmp_path, [SECRET_ENV.lower()]), server_cmd, tmp_path / "log.jsonl"),
         tmp_path / "shadow.json")
    assert json.loads(marker.read_text())["secret"] is False


@pytest.mark.parametrize("secret_env", [SECRET_ENV, ["not-a-name"], ["1LEADING_DIGIT"], [""], [42], None])
def test_invalid_secret_env_rejects_contracts(tmp_path, capsys, secret_env):
    path = _contracts(tmp_path, [SECRET_ENV])
    data = json.loads(path.read_text())
    data["tools"]["create_issue"]["verifier"]["secret_env"] = secret_env
    path.write_text(json.dumps(data), encoding="utf-8")
    assert outcome.load(str(path)) is None
    assert "invalid verifier.secret_env" in capsys.readouterr().err


def test_valid_secret_env_names_are_collected(tmp_path):
    loaded = outcome.load(str(_contracts(tmp_path, [SECRET_ENV, "OTHER_NAME"])))
    assert loaded is not None
    assert outcome.secret_env_names(loaded) == {SECRET_ENV, "OTHER_NAME"}
    assert outcome.secret_env_names(outcome.load(str(_contracts(tmp_path)))) == set()
    assert outcome.secret_env_names(None) == set()
