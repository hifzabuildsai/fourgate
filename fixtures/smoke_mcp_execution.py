"""Exercise an installed wheel outside the checkout; local simulation only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, help="Interpreter with the candidate Fourgate wheel installed")
    # Preserve a venv's executable path: resolving its symlink selects base Python.
    python = str(Path(parser.parse_args().python).absolute())
    with tempfile.TemporaryDirectory(prefix="fg-c2-") as temporary:
        root = Path(temporary)
        trace, store = root / "target.txt", root / "authority.json"
        target = root / "target.py"
        target.write_text(
            "import json,runpy,sys\nfrom pathlib import Path\n"
            f"trace=Path({str(trace)!r})\n"
            "with trace.open('a') as f: f.write('START\\n')\n"
            "original=sys.stdin\n"
            "class Input:\n"
            "    def __iter__(self): return self\n"
            "    def __next__(self):\n"
            "        raw=next(original)\n"
            "        if json.loads(raw).get('method')=='tools/call':\n"
            "            with trace.open('a') as f: f.write('CALL\\n')\n"
            "        return raw\n"
            "sys.stdin=Input()\nrunpy.run_module('fourgate.demo.server',run_name='__main__')\n", encoding="utf-8")
        contract = root / "scan.json"
        contract.write_text(json.dumps({"scan_version": 1, "server": {"transport": "stdio",
            "command": [python, str(target)], "test_account": "disposable-demo"},
            "write_tools": ["create_issue"], "cases": [{"tool": "create_issue",
                "arguments": {"title": "LOCAL-WHEEL-SIMULATION"}, "outcome_contract": {
                    "record_id_field": "issue_id", "extract": {
                        "issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
                        "title": {"source": "arguments", "path": "title"}},
                    "verifier": {"command": [python, "-m", "fourgate.demo.verifier"], "timeout_ms": 2000},
                    "allowed_failure_reasons": ["record_missing", "field_mismatch"]}}]}), encoding="utf-8")
        digest = hashlib.sha256(contract.read_bytes()).hexdigest()
        registry, policy = root / "registry.json", root / "policy.json"
        registry.write_text(json.dumps({"registry_version": 1, "workflows": {"demo": {
            "contract": "scan.json", "sha256": digest, "test_account": "disposable-demo"}}}), encoding="utf-8")
        policy.write_text(json.dumps({"policy_version": 1, "state_file": "runs.sqlite3", "grants": {
            "once": {"workflow_id": "demo", "contract_sha256": digest, "max_tool_calls": 1}}}), encoding="utf-8")
        env = {**os.environ, "FOURGATE_DEMO_STORE": str(store), "FOURGATE_DEMO_MODE": "healthy"}
        env.pop("PYTHONPATH", None)
        env.pop("FOURGATE_DEMO_VERIFIER", None)

        def run(argv, messages=None):
            result = subprocess.run(argv, cwd=root, env=env, text=True, capture_output=True,
                input="".join(json.dumps(m)+"\n" for m in messages) if messages else "", timeout=20)
            assert result.returncode == 0, result.stderr
            return result.stdout

        module = run([python, "-c", "import fourgate; print(fourgate.__file__)"]).strip()
        assert "site-packages" in Path(module).parts, module
        argv = [python, "-m", "fourgate", "mcp", "--registry", str(registry), "--execution-policy", str(policy)]
        run([*argv, "--prepare-execution-state"])
        assert not trace.exists() and not store.exists()
        startup = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "wheel", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]
        execute = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "run_workflow", "arguments": {"workflow_id": "demo", "run_id": "once"}}}
        report = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "get_run_report", "arguments": {"run_id": "once"}}}
        replies = [json.loads(line) for line in run(argv, [*startup, execute, report]).splitlines()]
        fresh, saved = [r["result"]["structuredContent"] for r in replies[1:]]
        assert fresh["verdict"] == "PASS" and fresh["new_execution"] is True
        assert saved == {**fresh, "new_execution": False}
        replay = [json.loads(line) for line in run(argv, [*startup, execute]).splitlines()][1]["result"]["structuredContent"]
        assert replay == saved
        assert trace.read_text().splitlines() == ["START", "CALL"]
        assert json.loads(store.read_text())[0]["title"] == "LOCAL-WHEEL-SIMULATION"
        print(json.dumps({"scope": "installed-wheel local simulation", "installed_module": module,
            "verdict": fresh["verdict"], "call_attempts": fresh["call_attempts"],
            "target_starts": 1, "target_calls": 1, "restart_new_execution": replay["new_execution"]}))


if __name__ == "__main__":
    main()
