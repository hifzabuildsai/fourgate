"""Read-only MCP acceptance: configuration readiness never executes an action."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026-07-28"
META = {"io.modelcontextprotocol/protocolVersion": VERSION,
        "io.modelcontextprotocol/clientCapabilities": {}}


def registry(tmp_path, *, missing_credential=False):
    marker = tmp_path / "MUST-NOT-RUN"
    program = tmp_path / "marker.py"
    program.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
    data = json.loads((ROOT / "fixtures/contracts/scan_demo.json").read_text(encoding="utf-8"))
    data["server"]["command"] = [sys.executable, str(program)]
    verifier = data["cases"][0]["outcome_contract"]["verifier"]
    verifier["command"] = [sys.executable, str(program)]
    verifier.pop("cwd")
    if missing_credential:
        verifier["secret_env"] = ["FOURGATE_MCP_MISSING_READ_CREDENTIAL"]
    contract = tmp_path / "scan.json"
    contract.write_text(json.dumps(data), encoding="utf-8")
    config = {"registry_version": 1, "workflows": {"local-demo": {
        "contract": "scan.json", "sha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
        "test_account": "disposable-demo"}}}
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path, contract, marker


def request(mid, method, params=None, modern=True):
    params = dict(params or {})
    if modern:
        params["_meta"] = META
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}


def run(path, messages):
    env = os.environ.copy()
    env.pop("FOURGATE_MCP_MISSING_READ_CREDENTIAL", None)
    return subprocess.run([sys.executable, "-m", "fourgate", "mcp", "--registry", str(path)],
                          input="".join(json.dumps(msg) + "\n" for msg in messages),
                          text=True, capture_output=True, cwd=ROOT, env=env, timeout=12)


def responses(result):
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]


@pytest.mark.parametrize("modern", [False, True])
def test_discovery_and_validation_are_read_only(tmp_path, modern):
    path, _, marker = registry(tmp_path)
    original = {p: p.read_bytes() for p in tmp_path.iterdir()}
    startup = [request(1, "server/discover")] if modern else [
        request(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "acceptance", "version": "1"}}, False),
        {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    result = responses(run(path, [*startup, request(2, "tools/list", modern=modern),
                                  request(3, "tools/call", {"name": "validate_workflow",
                                          "arguments": {"workflow_id": "local-demo"}}, modern)]))
    assert [r["id"] for r in result] == [1, 2, 3]
    tools = result[1]["result"]["tools"]
    assert [t["name"] for t in tools] == ["validate_workflow"]
    assert tools[0]["annotations"]["readOnlyHint"] is True
    check = result[2]["result"]["structuredContent"]
    assert check["readiness"] == "CONFIG_VALID"
    assert check["action_status"] == "NOT_RUN"
    assert check["planned_cases"] == 1
    assert "PASS" not in result[2]["result"]["content"][0]["text"]
    if modern:
        assert all(r["result"]["resultType"] == "complete" for r in result)
        assert result[0]["result"]["ttlMs"] == result[1]["result"]["ttlMs"] == 0
        assert result[0]["result"]["cacheScope"] == "private"
    assert not marker.exists()
    assert {p: p.read_bytes() for p in tmp_path.iterdir()} == original


@pytest.mark.parametrize("kind,reason", [("changed", "contract_changed"),
                                       ("malformed", "contract_invalid"),
                                       ("missing", "contract_unavailable"),
                                       ("credential", "credential_missing")])
def test_unready_configuration_never_becomes_an_action_verdict(tmp_path, kind, reason):
    path, contract, marker = registry(tmp_path, missing_credential=kind == "credential")
    if kind in ("changed", "malformed"):
        contract.write_text("not json", encoding="utf-8")
        if kind == "malformed":
            config = json.loads(path.read_text())
            config["workflows"]["local-demo"]["sha256"] = hashlib.sha256(contract.read_bytes()).hexdigest()
            path.write_text(json.dumps(config), encoding="utf-8")
    elif kind == "missing":
        contract.unlink()
    output = responses(run(path, [request(1, "tools/call", {"name": "validate_workflow",
                       "arguments": {"workflow_id": "local-demo"}})]))[0]["result"]
    assert output["isError"] is True
    assert output["structuredContent"]["readiness"] == "NOT_READY"
    assert output["structuredContent"]["action_status"] == "NOT_RUN"
    assert output["structuredContent"]["reason_code"] == reason
    assert not marker.exists()


@pytest.mark.parametrize("arguments", [{"workflow_id": "../scan.json"},
    {"workflow_id": "local-demo", "approved": True}, {"workflow_id": "local-demo", "command": ["whoami"]},
    {"workflow_id": "local-demo", "url": "https://unapproved.test"}, {"workflow_id": 42}, {}])
def test_tool_arguments_cannot_supply_paths_commands_endpoints_or_approval(tmp_path, arguments):
    path, _, marker = registry(tmp_path)
    output = responses(run(path, [request(1, "tools/call", {"name": "validate_workflow",
                                                          "arguments": arguments})]))[0]
    assert output["result"]["isError"] is True
    assert output["result"]["structuredContent"]["action_status"] == "NOT_RUN"
    assert not marker.exists()


def test_write_tool_is_not_exposed_or_callable(tmp_path):
    path, _, marker = registry(tmp_path)
    output = responses(run(path, [request(1, "tools/call", {"name": "run_workflow",
                            "arguments": {"workflow_id": "local-demo", "approved": True}})]))[0]
    assert "error" in output
    assert not marker.exists()


def test_unknown_modern_version_does_not_initialize(tmp_path):
    path, _, marker = registry(tmp_path)
    msg = request(1, "server/discover")
    msg["params"]["_meta"] = {**META, "io.modelcontextprotocol/protocolVersion": "2099-01-01"}
    output = responses(run(path, [msg]))[0]
    assert output["error"]["code"] == -32022
    assert VERSION in output["error"]["data"]["supported"]
    assert not marker.exists()


def test_invalid_registry_refuses_startup_without_echoing_contents(tmp_path):
    path, _, marker = registry(tmp_path)
    path.write_text('{"SENSITIVE_PRIVATE_VALUE":true}', encoding="utf-8")
    result = run(path, [])
    assert result.returncode == 2
    assert "fourgate mcp: registry configuration" in result.stderr
    assert not result.stdout
    assert "SENSITIVE_PRIVATE_VALUE" not in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("target", ["../outside.json", "/outside.json"])
def test_registry_contract_path_escape_is_rejected_before_read(tmp_path, target):
    path, _, marker = registry(tmp_path)
    config = json.loads(path.read_text())
    config["workflows"]["local-demo"]["contract"] = target
    path.write_text(json.dumps(config), encoding="utf-8")
    result = run(path, [])
    assert result.returncode == 2
    assert not result.stdout and not marker.exists()


def test_unknown_workflow_and_invalid_metadata_do_not_echo_private_values(tmp_path):
    path, _, _ = registry(tmp_path)
    secret = "PRIVATE-INPUT-SENTINEL"
    call = request(1, "tools/call", {"name": "validate_workflow", "arguments": {"workflow_id": secret}})
    bad_meta = request(2, "server/discover")
    bad_meta["params"]["_meta"] = {**META, "io.modelcontextprotocol/protocolVersion": {"secret": secret}}
    result = run(path, [call, bad_meta])
    assert result.returncode == 0
    assert secret not in result.stdout + result.stderr
    assert responses(result)[1]["error"]["code"] == -32602


def test_readiness_under_audit_denial_of_execution_network_and_writes(tmp_path):
    path, contract, _ = registry(tmp_path)
    data = json.loads(contract.read_text())
    data["cases"][0]["readback"] = {"type": "http", "url_template": "https://unapproved.test/{issue_id}",
                                    "expected_fields": {"title": "title"}, "timeout_ms": 100}
    contract.write_text(json.dumps(data), encoding="utf-8")
    config = json.loads(path.read_text())
    config["workflows"]["local-demo"]["sha256"] = hashlib.sha256(contract.read_bytes()).hexdigest()
    path.write_text(json.dumps(config), encoding="utf-8")
    # The hook lives in the actual MCP subprocess, covering the full wire path.
    program = (
        "import os,runpy,sys\n"
        "def deny(event,args):\n"
        "    if event in ('subprocess.Popen','os.system','socket.connect','socket.bind','os.mkdir','os.remove','os.rename'):\n"
        "        raise RuntimeError('forbidden side effect')\n"
        "    if event == 'open' and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT):\n"
        "        raise RuntimeError('forbidden file write')\n"
        "sys.addaudithook(deny)\n"
        "sys.argv=['fourgate','mcp','--registry',sys.argv[1]]\n"
        "runpy.run_module('fourgate',run_name='__main__')\n"
    )
    call = request(1, "tools/call", {"name": "validate_workflow", "arguments": {"workflow_id": "local-demo"}})
    result = subprocess.run([sys.executable, "-B", "-c", program, str(path)], input=json.dumps(call)+"\n",
                            cwd=ROOT, text=True, capture_output=True, timeout=12)
    payload = responses(result)[0]["result"]["structuredContent"]
    assert payload["readiness"] == "CONFIG_VALID" and payload["action_status"] == "NOT_RUN"


def test_registry_is_a_startup_snapshot_and_contract_is_rechecked(tmp_path):
    from fourgate.workflows import WorkflowRegistry

    path, contract, marker = registry(tmp_path)
    configured = WorkflowRegistry(path)
    assert configured.validate("local-demo")["readiness"] == "CONFIG_VALID"
    config = json.loads(path.read_text())
    config["workflows"]["unreviewed"] = config["workflows"]["local-demo"]
    path.write_text(json.dumps(config), encoding="utf-8")
    assert configured.ids == ["local-demo"]
    assert configured.validate("unreviewed")["reason_code"] == "workflow_not_registered"
    contract.write_text(contract.read_text() + "\n", encoding="utf-8")
    assert configured.validate("local-demo")["reason_code"] == "contract_changed"
    assert not marker.exists()


def test_duplicate_registry_fields_are_rejected(tmp_path):
    path, _, _ = registry(tmp_path)
    raw = path.read_text().replace('"registry_version": 1', '"registry_version": 1, "registry_version": 1')
    path.write_text(raw, encoding="utf-8")
    assert run(path, []).returncode == 2


def test_missing_modern_metadata_and_uninitialized_legacy_are_rejected(tmp_path):
    path, _, marker = registry(tmp_path)
    missing_version = request(1, "tools/list")
    missing_version["params"]["_meta"] = {"io.modelcontextprotocol/clientCapabilities": {}}
    output = responses(run(path, [missing_version, request(2, "tools/list", modern=False)]))
    assert [r["error"]["code"] for r in output] == [-32602, -32002]
    assert not marker.exists()


def test_malformed_wire_message_does_not_pollute_following_reply(tmp_path):
    path, _, _ = registry(tmp_path)
    following = request(2, "server/discover")
    result = subprocess.run([sys.executable, "-m", "fourgate", "mcp", "--registry", str(path)],
                            input="not json\n"+json.dumps(following)+"\n", cwd=ROOT,
                            text=True, capture_output=True, timeout=12)
    output = responses(result)
    assert output[0]["error"]["code"] == -32700
    assert output[1]["id"] == 2 and output[1]["result"]["resultType"] == "complete"


def test_oversized_wire_request_stops_with_protocol_error(tmp_path):
    path, _, _ = registry(tmp_path)
    result = subprocess.run([sys.executable, "-m", "fourgate", "mcp", "--registry", str(path)],
                            input="x" * (1024 * 1024 + 1) + "\n", cwd=ROOT,
                            text=True, capture_output=True, timeout=12)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == -32600


def test_malformed_readback_shape_is_typed_not_ready_with_original_id(tmp_path):
    path, contract, marker = registry(tmp_path)
    data = json.loads(contract.read_text())
    data["cases"][0]["readback"] = {"type": "github_issue", "repository": "owner/repo",
        "issue_number_field": [], "token_env": "NOT_PRESENT_TEST_TOKEN", "expected_fields": {"title": "title"}}
    contract.write_text(json.dumps(data), encoding="utf-8")
    config = json.loads(path.read_text())
    config["workflows"]["local-demo"]["sha256"] = hashlib.sha256(contract.read_bytes()).hexdigest()
    path.write_text(json.dumps(config), encoding="utf-8")
    msg = request(71, "tools/call", {"name": "validate_workflow", "arguments": {"workflow_id": "local-demo"}})
    output = responses(run(path, [msg]))[0]
    assert output["id"] == 71
    assert output["result"]["structuredContent"]["reason_code"] == "contract_invalid"
    assert output["result"]["structuredContent"]["action_status"] == "NOT_RUN"
    assert not marker.exists()


def test_file_swap_after_path_check_is_rejected_before_acceptance(tmp_path, monkeypatch):
    from fourgate import scan
    from fourgate.workflows import WorkflowRegistry

    path, contract, marker = registry(tmp_path)
    configured = WorkflowRegistry(path)
    outside = tmp_path.parent / (tmp_path.name + "-outside.json")
    outside.write_bytes(contract.read_bytes())  # same fingerprint, different file identity
    original = scan.load_contract

    def swap_before_open(*args, **kwargs):
        contract.unlink()
        try:
            contract.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(scan, "load_contract", swap_before_open)
    assert configured.validate("local-demo")["reason_code"] == "contract_changed"
    assert not marker.exists()


def test_looped_contract_symlink_refuses_startup_without_traceback(tmp_path):
    path, contract, _ = registry(tmp_path)
    contract.unlink()
    try:
        contract.symlink_to(contract)
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = run(path, [])
    assert result.returncode == 2
    assert "registry configuration" in result.stderr
    assert "Traceback" not in result.stderr and not result.stdout


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO fixture")
def test_fifo_swap_after_path_check_does_not_block_validation(tmp_path):
    path, contract, _ = registry(tmp_path)
    program = (
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "from fourgate import scan\n"
        "from fourgate.workflows import WorkflowRegistry\n"
        "registry=WorkflowRegistry(sys.argv[1])\n"
        "original=scan.load_contract\n"
        "def swap(*args,**kwargs):\n"
        "    target=Path(sys.argv[2]); target.unlink(); os.mkfifo(target)\n"
        "    return original(*args,**kwargs)\n"
        "scan.load_contract=swap\n"
        "print(json.dumps(registry.validate('local-demo')))\n"
    )
    result = subprocess.run([sys.executable, "-c", program, str(path), str(contract)], cwd=ROOT,
                            text=True, capture_output=True, timeout=5)
    assert result.returncode == 0
    assert json.loads(result.stdout)["reason_code"] == "contract_changed"


def test_installed_legacy_sdk_discovers_and_invokes_read_only_tool(tmp_path):
    mcp = pytest.importorskip("mcp")
    anyio = pytest.importorskip("anyio")
    from mcp.client.stdio import stdio_client

    path, contract, marker = registry(tmp_path)

    async def exercise():
        params = mcp.StdioServerParameters(command=sys.executable,
            args=["-m", "fourgate", "mcp", "--registry", str(path)], cwd=str(ROOT))
        async with stdio_client(params) as (read, write):
            async with mcp.ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.protocolVersion == "2024-11-05"
                tools = await session.list_tools()
                assert [t.name for t in tools.tools] == ["validate_workflow"]
                result = await session.call_tool("validate_workflow", {"workflow_id": "local-demo"})
                payload = result.model_dump()["structuredContent"]
                assert payload["readiness"] == "CONFIG_VALID" and payload["action_status"] == "NOT_RUN"
                assert json.loads(result.content[0].text) == payload
                contract.write_text(contract.read_text()+"\n", encoding="utf-8")
                changed = await session.call_tool("validate_workflow", {"workflow_id": "local-demo"})
                assert changed.model_dump()["structuredContent"]["reason_code"] == "contract_changed"

    anyio.run(exercise)
    assert not marker.exists()
