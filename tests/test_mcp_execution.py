"""Opt-in execution controls using real, isolated local MCP fixtures."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}}


def setup(tmp_path, *, control="healthy", cases=1, budget=1, credential=False):
    store, trace = tmp_path / "authority.json", tmp_path / "target.jsonl"
    data = json.loads((ROOT / "fixtures/contracts/scan_demo.json").read_text(encoding="utf-8"))
    data["server"].update(command=[sys.executable, str(ROOT / "fixtures/protocol_server.py"),
        "--era", "native", "--control", control, "--store", str(store), "--trace", str(trace)],
        protocol_version="2026-07-28", call_timeout_ms=300)
    case = data["cases"][0]
    case["arguments"]["title"] = "PRIVATE-ARGUMENT-SENTINEL"
    case["outcome_contract"]["verifier"] = {
        "command": [sys.executable, str(ROOT / "fixtures/outcome_verifier.py")], "timeout_ms": 500}
    if credential:
        case["outcome_contract"]["verifier"]["secret_env"] = ["FOURGATE_C2_READ_SECRET"]
    data["cases"] = [copy.deepcopy(case) for _ in range(cases)]
    contract = tmp_path / "scan.json"
    contract.write_text(json.dumps(data), encoding="utf-8")
    digest = hashlib.sha256(contract.read_bytes()).hexdigest()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"registry_version": 1, "workflows": {"local-demo": {
        "contract": "scan.json", "sha256": digest, "test_account": "disposable-demo"}}}), encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"policy_version": 1, "state_file": "execution.sqlite3", "grants": {
        "approved-run": {"workflow_id": "local-demo", "contract_sha256": digest,
                         "max_tool_calls": budget}}}), encoding="utf-8")
    env = {**os.environ, "FOURGATE_DEMO_STORE": str(store)}
    env.pop("FOURGATE_C2_READ_SECRET", None)
    return registry, policy, contract, store, trace, env


def command(registry, policy=None):
    result = [sys.executable, "-m", "fourgate", "mcp", "--registry", str(registry)]
    return result + ["--execution-policy", str(policy)] if policy else result


def prepare(registry, policy, env):
    __tracebackhide__ = True
    result = subprocess.run([*command(registry, policy), "--prepare-execution-state"],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=12)
    assert result.returncode == 0, result.stderr
    return result


def call(mid=1, name="run_workflow", arguments=None, modern=True):
    return {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {
        **({"_meta": META} if modern else {}), "name": name,
        "arguments": {"workflow_id": "local-demo", "run_id": "approved-run"}
        if arguments is None else arguments}}


def run(registry, policy, env, messages):
    __tracebackhide__ = True
    result = subprocess.run(command(registry, policy), cwd=ROOT, env=env,
        input="".join(json.dumps(m)+"\n" for m in messages), text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]


def writes(trace):
    return [m for m in (json.loads(x) for x in trace.read_text(encoding="utf-8").splitlines())
            if m["method"] == "tools/call"] if trace.exists() else []


@pytest.mark.parametrize("modern", [False, True])
def test_opt_in_client_executes_once_and_returns_structural_report(tmp_path, modern):
    registry, policy, _, store, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    assert not trace.exists() and not store.exists()
    startup = [] if modern else [
        {"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    messages = [*startup, {"jsonrpc": "2.0", "id": 11, "method": "tools/list",
        "params": {"_meta": META} if modern else {}}, call(modern=modern),
        call(2, "get_run_report", {"run_id": "approved-run"}, modern)]
    output = run(registry, policy, env, messages)
    tools = next(x["result"]["tools"] for x in output if x["id"] == 11)
    assert [t["name"] for t in tools] == ["validate_workflow", "run_workflow", "get_run_report"]
    assert tools[1]["annotations"]["readOnlyHint"] is False
    assert tools[1]["annotations"]["destructiveHint"] is True
    assert tools[2]["annotations"]["readOnlyHint"] is True
    payload = next(x["result"]["structuredContent"] for x in output if x["id"] == 1)
    assert (payload["run_state"], payload["verdict"], payload["call_attempts"]) == ("COMPLETED", "PASS", 1)
    assert payload["action_status"] == "ATTEMPTED"
    assert payload["new_execution"] is True
    assert output[-1]["result"]["structuredContent"] == {**payload, "new_execution": False}
    assert not output[-1]["result"]["isError"]
    assert len(writes(trace)) == 1
    assert json.loads(store.read_text())[0]["title"] == "PRIVATE-ARGUMENT-SENTINEL"
    wire = json.dumps(output)
    assert "PRIVATE-ARGUMENT-SENTINEL" not in wire
    assert str(tmp_path) not in wire and "ISSUE-001" not in wire
    assert len(wire.encode()) < 16384


@pytest.mark.parametrize("control,malformed,verdict,reason", [
    ("missing", False, "FAIL", "record_missing"),
    ("healthy", True, "UNKNOWN", "verifier_error")])
def test_induced_controls_preserve_verdicts_despite_successful_process(tmp_path, control, malformed, verdict, reason):
    registry, policy, _, store, trace, env = setup(tmp_path, control=control)
    if malformed:
        env["FOURGATE_DEMO_VERIFIER"] = "crash"
    prepare(registry, policy, env)
    payload = run(registry, policy, env, [call()])[0]["result"]
    assert payload["isError"] is True
    assert payload["structuredContent"]["verdict"] == verdict
    assert payload["structuredContent"]["cases"][0]["reason_code"] == reason
    assert len(writes(trace)) == 1


def test_default_interface_never_exposes_execution(tmp_path):
    registry, _, _, store, trace, env = setup(tmp_path)
    result = run(registry, None, env, [call()])[0]
    assert "error" in result
    assert not trace.exists() and not store.exists()


@pytest.mark.parametrize("extra", [{"approved": True}, {"command": ["whoami"]},
    {"contract": "elsewhere.json"}, {"max_tool_calls": 999}, {"url": "https://unapproved.test"}])
def test_agent_cannot_override_execution_authority(tmp_path, extra):
    registry, policy, _, store, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    result = run(registry, policy, env, [call(arguments={
        "workflow_id": "local-demo", "run_id": "approved-run", **extra})])[0]["result"]["structuredContent"]
    assert result["action_status"] == "NOT_RUN" and "verdict" not in result
    assert not trace.exists() and not store.exists()


@pytest.mark.parametrize("problem,reason", [("budget", "budget_exceeded"),
    ("credential", "credential_missing"), ("changed", "contract_changed"),
    ("unknown", "grant_not_registered")])
def test_preflight_rejects_without_starting_target(tmp_path, problem, reason):
    registry, policy, contract, store, trace, env = setup(tmp_path,
        cases=2 if problem == "budget" else 1, credential=problem == "credential")
    prepare(registry, policy, env)
    if problem == "changed":
        contract.write_text(contract.read_text()+"\n", encoding="utf-8")
    args = {"workflow_id": "local-demo", "run_id": "unapproved" if problem == "unknown" else "approved-run"}
    output = run(registry, policy, env, [call(arguments=args)])[0]["result"]["structuredContent"]
    assert (output["action_status"], output["reason_code"]) == ("NOT_RUN", reason)
    assert "verdict" not in output and not trace.exists() and not store.exists()


def test_repeated_and_restarted_requests_return_saved_report_without_replay(tmp_path):
    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    first = run(registry, policy, env, [call(), call(2)])
    assert first[0]["result"]["structuredContent"]["new_execution"] is True
    assert first[1]["result"]["structuredContent"] == {
        **first[0]["result"]["structuredContent"], "new_execution": False}
    second = run(registry, policy, env, [call()])
    assert second[0]["result"] == first[1]["result"]
    assert len(writes(trace)) == 1


@pytest.mark.parametrize("problem", ["missing", "corrupt"])
def test_missing_or_corrupt_prepared_state_never_recreates_authority(tmp_path, problem):
    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    state = tmp_path / "execution.sqlite3"
    if problem == "missing":
        state.unlink()
    else:
        state.write_bytes(b"not a database")
    result = subprocess.run(command(registry, policy), input="", cwd=ROOT, env=env,
        text=True, capture_output=True, timeout=12)
    assert result.returncode == 2 and not result.stdout and "Traceback" not in result.stderr
    assert not trace.exists()
    assert (state.exists() if problem == "corrupt" else not state.exists())


def test_preparation_refuses_to_reset_existing_state(tmp_path):
    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    run(registry, policy, env, [call()])
    result = subprocess.run([*command(registry, policy), "--prepare-execution-state"],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=12)
    assert result.returncode == 2
    run(registry, policy, env, [call()])
    assert len(writes(trace)) == 1


def repin(registry, policy, contract):
    digest = hashlib.sha256(contract.read_bytes()).hexdigest()
    config = json.loads(registry.read_text())
    config["workflows"]["local-demo"]["sha256"] = digest
    registry.write_text(json.dumps(config), encoding="utf-8")
    grants = json.loads(policy.read_text())
    grants["grants"]["approved-run"]["contract_sha256"] = digest
    policy.write_text(json.dumps(grants), encoding="utf-8")


def test_timeout_after_persistence_stops_remaining_cases_and_never_replays(tmp_path):
    registry, policy, _, store, trace, env = setup(tmp_path, control="persist_timeout", cases=2, budget=2)
    prepare(registry, policy, env)
    output = run(registry, policy, env, [call(), call(2)])
    assert output[1]["result"]["structuredContent"] == {
        **output[0]["result"]["structuredContent"], "new_execution": False}
    result = output[0]["result"]["structuredContent"]
    assert result["verdict"] == "UNKNOWN" and result["call_attempts"] == 1
    assert result["reserved_tool_calls"] == 2
    assert len(result["cases"]) == 1 and result["cases"][0]["reason_code"] == "TimeoutError"
    assert store.exists() and len(writes(trace)) == 1
    run(registry, policy, env, [call()])
    assert len(writes(trace)) == 1


def test_killed_adapter_leaves_uncertain_reservation_without_restart_write(tmp_path):
    registry, policy, contract, store, trace, env = setup(tmp_path, control="persist_timeout")
    data = json.loads(contract.read_text())
    data["server"]["call_timeout_ms"] = 10000
    contract.write_text(json.dumps(data), encoding="utf-8")
    repin(registry, policy, contract)
    prepare(registry, policy, env)
    process = subprocess.Popen(command(registry, policy), cwd=ROOT, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps(call())+"\n")
        process.stdin.flush()
        deadline = time.monotonic()+8
        while not store.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.02)
        assert store.exists() and len(writes(trace)) == 1
        process.kill()
        process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
    result = run(registry, policy, env, [call(), call(2, "get_run_report", {"run_id": "approved-run"})])
    assert all(r["result"]["structuredContent"]["verdict"] == "UNKNOWN" for r in result)
    assert all(r["result"]["structuredContent"]["action_status"] == "UNCERTAIN" for r in result)
    assert len(writes(trace)) == 1


def test_simultaneous_processes_share_one_claim(tmp_path):
    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    wrapper = tmp_path / "barrier.py"
    wrapper.write_text(
        "import runpy,sys,time\nfrom pathlib import Path\n"
        "from fourgate.execution import ExecutionState\n"
        "ready,other=map(Path,sys.argv[1:3]); original=ExecutionState.claim\n"
        "def claim(self,*args):\n"
        "    ready.touch(); deadline=time.monotonic()+6\n"
        "    while not other.exists() and time.monotonic()<deadline: time.sleep(0.01)\n"
        "    assert other.exists()\n"
        "    return original(self,*args)\n"
        "ExecutionState.claim=claim\n"
        "sys.argv=['fourgate','mcp',*sys.argv[3:]]\n"
        "runpy.run_module('fourgate',run_name='__main__')\n", encoding="utf-8")
    processes = []
    for own, other in [("a", "b"), ("b", "a")]:
        # Source import remains explicit when the temporary script is outside ROOT.
        process = subprocess.Popen([sys.executable, str(wrapper), str(tmp_path/own), str(tmp_path/other),
            *command(registry, policy)[4:]], cwd=ROOT, env={**env, "PYTHONPATH": str(ROOT)},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        process.stdin.write(json.dumps(call())+"\n")
        process.stdin.flush()
        processes.append(process)
    try:
        outputs = [p.communicate(timeout=12) for p in processes]
        assert all(p.returncode == 0 for p in processes), outputs
        assert all(json.loads(out.splitlines()[0])["result"]["structuredContent"]["run_state"]
                   in ("COMPLETED", "UNCERTAIN") for out, _ in outputs)
        assert len(writes(trace)) == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


def test_saved_report_with_extra_private_data_is_not_returned(tmp_path):
    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    run(registry, policy, env, [call()])
    with sqlite3.connect(tmp_path / "execution.sqlite3") as db:
        payload = json.loads(db.execute("SELECT report FROM runs").fetchone()[0])
        payload["evidence"] = "PRIVATE-STORED-REPORT-SENTINEL"
        db.execute("UPDATE runs SET report=?", (json.dumps(payload),))
    output = run(registry, policy, env, [call(2, "get_run_report", {"run_id": "approved-run"}), call()])
    assert all(r["result"]["structuredContent"]["verdict"] == "UNKNOWN" for r in output)
    assert "PRIVATE-STORED-REPORT-SENTINEL" not in json.dumps(output)
    assert len(writes(trace)) == 1


def test_inconsistent_available_row_cannot_reset_spent_grant(tmp_path):
    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    run(registry, policy, env, [call()])
    with sqlite3.connect(tmp_path / "execution.sqlite3") as db:
        db.execute("UPDATE runs SET state='AVAILABLE'")
    result = subprocess.run(command(registry, policy), input=json.dumps(call())+"\n",
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=12)
    assert result.returncode == 2 and not result.stdout
    assert len(writes(trace)) == 1


def test_execution_uses_pinned_loaded_bytes_without_reopening_contract(tmp_path, monkeypatch):
    from fourgate.execution import ExecutionPolicy, ExecutionState, WorkflowRunner
    from fourgate.workflows import WorkflowRegistry
    from fourgate import scan

    registry, policy, contract, _, trace, env = setup(tmp_path)
    configured = WorkflowRegistry(registry)
    grant = ExecutionPolicy(policy, configured)
    ExecutionState.prepare(grant)
    runner = WorkflowRunner(configured, grant)
    original = scan._scan_loaded_contract

    def replace_after_load(data, **kwargs):
        contract.write_text('{"unapproved":"replacement"}', encoding="utf-8")
        return original(data, **kwargs)

    monkeypatch.setattr(scan, "_scan_loaded_contract", replace_after_load)
    monkeypatch.setenv("FOURGATE_DEMO_STORE", env["FOURGATE_DEMO_STORE"])
    assert runner.run("local-demo", "approved-run")["verdict"] == "PASS"
    assert len(writes(trace)) == 1


def test_report_write_error_does_not_release_consumed_grant(tmp_path, monkeypatch):
    from fourgate.execution import ExecutionPolicy, ExecutionState, WorkflowRunner
    from fourgate.workflows import WorkflowRegistry

    registry, policy, _, _, trace, env = setup(tmp_path)
    configured = WorkflowRegistry(registry)
    grant = ExecutionPolicy(policy, configured)
    ExecutionState.prepare(grant)
    runner = WorkflowRunner(configured, grant)
    monkeypatch.setenv("FOURGATE_DEMO_STORE", env["FOURGATE_DEMO_STORE"])

    def disk_error(*args):
        raise OSError("PRIVATE-DISK-ERROR-SENTINEL")

    monkeypatch.setattr(runner.state, "finish", disk_error)
    first = runner.run("local-demo", "approved-run")
    assert first["verdict"] == "UNKNOWN" and first["reason_code"] == "report_persistence_error"
    assert runner.run("local-demo", "approved-run")["verdict"] == "UNKNOWN"
    assert len(writes(trace)) == 1 and "PRIVATE-DISK-ERROR-SENTINEL" not in json.dumps(first)


@pytest.mark.parametrize("field", ["report_version", "reserved_tool_calls"])
def test_saved_boolean_cannot_masquerade_as_integer(tmp_path, field):
    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    run(registry, policy, env, [call()])
    with sqlite3.connect(tmp_path / "execution.sqlite3") as db:
        payload = json.loads(db.execute("SELECT report FROM runs").fetchone()[0])
        payload[field] = True
        db.execute("UPDATE runs SET report=?", (json.dumps(payload),))
    output = run(registry, policy, env, [call(2, "get_run_report", {"run_id": "approved-run"})])
    assert output[0]["result"]["structuredContent"]["verdict"] == "UNKNOWN"
    assert len(writes(trace)) == 1


def test_validation_and_unstarted_report_do_not_consume_or_mutate_grant(tmp_path):
    registry, policy, _, store, trace, env = setup(tmp_path)
    prepare(registry, policy, env)
    state = tmp_path / "execution.sqlite3"
    before = state.read_bytes()
    output = run(registry, policy, env, [call(1, "validate_workflow", {"workflow_id": "local-demo"}),
        call(2, "get_run_report", {"run_id": "approved-run"})])
    assert output[0]["result"]["structuredContent"]["readiness"] == "CONFIG_VALID"
    assert output[1]["result"]["structuredContent"]["action_status"] == "NOT_RUN"
    assert output[1]["result"]["structuredContent"]["new_execution"] is False
    assert before == state.read_bytes() and not trace.exists() and not store.exists()


@pytest.mark.parametrize("problem", ["budget_bool", "budget_total", "pin", "path_escape", "policy_changed"])
def test_invalid_or_changed_operator_policy_refuses_execution(tmp_path, problem):
    registry, policy, _, store, trace, env = setup(tmp_path)
    if problem == "policy_changed":
        prepare(registry, policy, env)
    data = json.loads(policy.read_text())
    if problem == "budget_bool":
        data["grants"]["approved-run"]["max_tool_calls"] = True
    elif problem == "budget_total":
        data["grants"]["approved-run"]["max_tool_calls"] = 20
        data["grants"]["second-run"] = {**data["grants"]["approved-run"], "max_tool_calls": 1}
    elif problem == "pin":
        data["grants"]["approved-run"]["contract_sha256"] = "0"*64
    elif problem == "path_escape":
        data["state_file"] = f"../{tmp_path.name}-unapproved.sqlite3"
    else:
        data["grants"]["approved-run"]["max_tool_calls"] = 2
    policy.write_text(json.dumps(data), encoding="utf-8")
    argv = command(registry, policy) + ([] if problem == "policy_changed" else ["--prepare-execution-state"])
    result = subprocess.run(argv, input=json.dumps(call())+"\n", cwd=ROOT, env=env,
        text=True, capture_output=True, timeout=12)
    assert result.returncode == 2 and not result.stdout and "Traceback" not in result.stderr
    assert not trace.exists() and not store.exists()
    if problem != "policy_changed":
        assert not (tmp_path / "execution.sqlite3").exists()


def test_verifier_only_custom_credential_reaches_verifier_but_not_target(tmp_path):
    registry, policy, contract, _, trace, env = setup(tmp_path, credential=True)
    original = json.loads(contract.read_text())
    marker, probe = tmp_path / "env.json", tmp_path / "probe.py"
    probe.write_text("import json,os,runpy,sys\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(json.dumps({{'read': 'FOURGATE_C2_READ_SECRET' in os.environ, "
        "'write': 'FOURGATE_C2_WRITE_TOKEN' in os.environ}))\n"
        f"sys.argv={original['server']['command'][1:]!r}\n"
        "runpy.run_path(sys.argv[0],run_name='__main__')\n", encoding="utf-8")
    original["server"]["command"] = [sys.executable, str(probe)]
    verifier = tmp_path / "verify_secret.py"
    verifier.write_text("import os,runpy\n"
        "assert os.environ.get('FOURGATE_C2_READ_SECRET') == 'local-fake-read-value'\n"
        f"runpy.run_path({str(ROOT/'fixtures/outcome_verifier.py')!r},run_name='__main__')\n", encoding="utf-8")
    original["cases"][0]["outcome_contract"]["verifier"]["command"] = [sys.executable, str(verifier)]
    contract.write_text(json.dumps(original), encoding="utf-8")
    repin(registry, policy, contract)
    env.update(FOURGATE_C2_READ_SECRET="local-fake-read-value", FOURGATE_C2_WRITE_TOKEN="local-fake-write-value")
    prepare(registry, policy, env)
    output = run(registry, policy, env, [call()])
    assert output[0]["result"]["structuredContent"]["verdict"] == "PASS"
    assert json.loads(marker.read_text()) == {"read": False, "write": True}
    assert "local-fake" not in json.dumps(output) and len(writes(trace)) == 1


def test_basic_readback_username_and_token_do_not_reach_target(tmp_path):
    registry, policy, contract, _, trace, env = setup(tmp_path, control="wrong_versions")
    data = json.loads(contract.read_text())
    marker, probe = tmp_path / "env.json", tmp_path / "probe.py"
    probe.write_text("import json,os,runpy,sys\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(json.dumps([name in os.environ for name in "
        "['FOURGATE_C2_READ_USER','FOURGATE_C2_READ_TOKEN']]))\n"
        f"sys.argv={data['server']['command'][1:]!r}\n"
        "runpy.run_path(sys.argv[0],run_name='__main__')\n", encoding="utf-8")
    data["server"]["command"] = [sys.executable, str(probe)]
    data["cases"][0]["readback"] = {"type": "http", "url_template": "https://unapproved.test/{issue_id}",
        "expected_fields": {"title": "title"}, "token_env": "FOURGATE_C2_READ_TOKEN",
        "auth": {"scheme": "basic", "username_env": "FOURGATE_C2_READ_USER"}}
    contract.write_text(json.dumps(data), encoding="utf-8")
    repin(registry, policy, contract)
    env.update(FOURGATE_C2_READ_USER="local-fake-user", FOURGATE_C2_READ_TOKEN="local-fake-token")
    prepare(registry, policy, env)
    output = run(registry, policy, env, [call()])
    assert output[0]["result"]["structuredContent"]["verdict"] == "UNKNOWN"
    assert json.loads(marker.read_text()) == [False, False] and not writes(trace)
    # Deliberate discovery failure happens before tools/call or any HTTP verifier.


def test_installed_sdk_discovers_execution_and_reads_cached_report(tmp_path):
    mcp = pytest.importorskip("mcp")
    anyio = pytest.importorskip("anyio")
    from mcp.client.stdio import stdio_client

    registry, policy, _, _, trace, env = setup(tmp_path)
    prepare(registry, policy, env)

    async def exercise():
        params = mcp.StdioServerParameters(command=sys.executable,
            args=command(registry, policy)[1:], cwd=str(ROOT), env=env)
        async with stdio_client(params) as (read, write):
            async with mcp.ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.protocolVersion == "2024-11-05"
                tools = await session.list_tools()
                assert [t.name for t in tools.tools] == ["validate_workflow", "run_workflow", "get_run_report"]
                result = await session.call_tool("run_workflow", {"workflow_id": "local-demo", "run_id": "approved-run"})
                first = result.model_dump()["structuredContent"]
                assert first["verdict"] == "PASS" and first["new_execution"] is True
                cached = await session.call_tool("get_run_report", {"run_id": "approved-run"})
                assert cached.model_dump()["structuredContent"] == {**first, "new_execution": False}

    anyio.run(exercise)
    assert len(writes(trace)) == 1
