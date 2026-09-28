"""Explicit, test-account-only stdio MCP scan. No arbitrary tool probing.

The scanner calls only names in the validated contract. Discovery checks
availability; the server's advertised list is never used to select calls.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from wrap import outcome

MAX_CALL_TIMEOUT_MS = 10000
MAX_STDOUT_LINE = 2 * 1024 * 1024


def _positive_ms(value, ceiling):
    return type(value) is int and 0 < value <= ceiling


def load_contract(path, confirmation):
    """Validate the entire contract before launching a server or any write."""
    file_path = Path(path).resolve()
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("scan_version") != 1:
        raise ValueError("scan_version must be 1")
    server = data.get("server")
    if not isinstance(server, dict) or server.get("transport") != "stdio":
        raise ValueError("only stdio is supported by the tested scanner")
    account = server.get("test_account")
    if not isinstance(account, str) or not account.strip() or account != confirmation:
        raise ValueError("--confirm-test-account must exactly match the nonempty contract test_account")
    command = server.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
        raise ValueError("server.command must be a nonempty string array")
    protocol = server.get("protocol_version", "2024-11-05")
    if protocol not in ("2024-11-05", "2025-11-25"):
        raise ValueError("unsupported stdio protocol_version")
    timeout = server.get("call_timeout_ms", 5000)
    if not _positive_ms(timeout, MAX_CALL_TIMEOUT_MS):
        raise ValueError("call_timeout_ms must be within 1..10000")
    allowed = data.get("write_tools")
    if not isinstance(allowed, list) or not allowed or any(not isinstance(t, str) or not t for t in allowed):
        raise ValueError("write_tools must be a unique, nonempty list of tool names")
    if len(allowed) != len(set(allowed)):
        raise ValueError("write_tools must be a unique, nonempty list of tool names")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    for case in cases:
        if not isinstance(case, dict) or case.get("tool") not in allowed or not isinstance(case.get("arguments"), dict):
            raise ValueError("each case needs an allowed write tool and explicit arguments object")
        check = case.get("outcome_contract")
        if not isinstance(check, dict) or not isinstance(check.get("extract"), dict) or not check["extract"]:
            raise ValueError("every case needs an outcome_contract with extract selectors")
        verifier = check.get("verifier")
        if not isinstance(verifier, dict) or not outcome._expand_command(verifier.get("command")) or not _positive_ms(
            verifier.get("timeout_ms"), outcome.MAX_VERIFIER_TIMEOUT_MS
        ):
            raise ValueError("every case needs a bounded verifier command")
        if not isinstance(check.get("allowed_failure_reasons"), list):
            raise ValueError("allowed_failure_reasons must be a list")
        check["_contract_dir"] = str(file_path.parent)
    server["command"] = [sys.executable if s == "{python}" else s for s in command]
    server["_contract_dir"] = str(file_path.parent)
    return data


class StdioClient:
    def __init__(self, command, cwd):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, bufsize=0, env=os.environ.copy(), cwd=cwd)
        self._queue = queue.Queue()
        self._id = 0
        threading.Thread(target=self._read_lines, daemon=True).start()

    def _read_lines(self):
        try:
            for line in iter(self.proc.stdout.readline, b""):
                self._queue.put(line if len(line) <= MAX_STDOUT_LINE else b"")
        finally:
            self._queue.put(None)

    def request(self, method, params, timeout_ms):
        self._id += 1
        request = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        self._send(request)
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method} timed out")
            try:
                raw = self._queue.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(f"{method} timed out") from None
            if raw is None:
                raise RuntimeError("server closed stdout")
            try:
                response = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("invalid server stdout") from exc
            if not isinstance(response, dict):
                raise RuntimeError("non-object server response")
            if response.get("id") == self._id:
                return request, response

    def _send(self, message):
        self.proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def initialize(self, protocol):
        _, response = self.request("initialize", {
            "protocolVersion": protocol, "capabilities": {},
            "clientInfo": {"name": "fourgate-scan", "version": "0.1.0"},
        }, 5000)
        if "error" in response or not isinstance(response.get("result"), dict):
            raise RuntimeError("initialize failed")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        _, response = self.request("tools/list", {}, 5000)
        tools = response.get("result", {}).get("tools") if isinstance(response.get("result"), dict) else None
        if not isinstance(tools, list):
            raise RuntimeError("tools/list failed")
        return {tool.get("name") for tool in tools if isinstance(tool, dict)}

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        self.proc.stdout.close()
        self.proc.stdin.close()


def scan(path, confirmation):
    data = load_contract(path, confirmation)
    server = data["server"]
    rows = []
    client = StdioClient(server["command"], server["_contract_dir"])
    try:
        discovered = client.initialize(server.get("protocol_version", "2024-11-05"))
        for case in data["cases"]:
            name = case["tool"]
            if name not in discovered:
                rows.append({"tool": name, "status": "UNKNOWN", "reason_code": "tool_not_discovered"})
                continue
            try:
                _, response = client.request("tools/call", {"name": name, "arguments": case["arguments"]},
                                             server.get("call_timeout_ms", 5000))
            except (TimeoutError, OSError, RuntimeError) as exc:
                rows.append({"tool": name, "status": "UNKNOWN", "reason_code": type(exc).__name__})
                # A timed-out call may still mutate state, so never issue more writes.
                break
            evaluation = outcome.evaluate(response, case["arguments"], f"{server['test_account']}/{name}",
                                          case["outcome_contract"])
            rows.append({"tool": name, "status": evaluation["status"].upper(),
                         "reason_code": evaluation["reason_code"]})
    except (TimeoutError, OSError, RuntimeError) as exc:
        rows.append({"tool": None, "status": "UNKNOWN", "reason_code": type(exc).__name__})
    finally:
        client.close()
    return {"scan_version": 1, "test_account": server["test_account"], "cases": rows}
