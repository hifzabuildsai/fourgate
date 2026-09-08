"""
plan.md Step 1 — raw byte proxy.

Runs the identical scripted JSON-RPC session against fixtures/clean_server.py
directly and through wrap/wrap.py, and asserts the raw stdout bytes match.
No classification exists yet at this step, so there is nothing for the wrap
to do except forward bytes unchanged (FR-1).
"""

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLEAN_SERVER = REPO_ROOT / "fixtures" / "clean_server.py"
WRAP = REPO_ROOT / "wrap" / "wrap.py"

TIMEOUT = 5.0


class ScriptedSession:
    """Drives a stdio JSON-RPC server while capturing every raw byte it
    writes to stdout, in order, unmodified."""

    def __init__(self, cmd):
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.captured = bytearray()
        self._queue = queue.Queue()
        self._next_id = 0

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_drain.start()

    def _read_loop(self):
        try:
            for line in iter(self.proc.stdout.readline, b""):
                self.captured.extend(line)
                self._queue.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self._queue.put(None)

    def _drain_stderr(self):
        try:
            for _ in iter(self.proc.stderr.readline, b""):
                pass
        except (OSError, ValueError):
            pass

    def _read_json_line(self, expect_id, timeout=TIMEOUT):
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.05, deadline - time.time())
            try:
                line = self._queue.get(timeout=remaining)
            except queue.Empty:
                return None
            if line is None:
                return None
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if expect_id is not None and obj.get("id") != expect_id:
                continue
            return obj
        return None

    def _write(self, msg):
        data = (json.dumps(msg) + "\n").encode("utf-8")
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def send_request(self, method, params=None):
        self._next_id += 1
        req_id = self._next_id
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        return self._read_json_line(expect_id=req_id)

    def send_notification(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    def close(self):
        """Close stdin (EOF, same as a client disconnecting), wait for the
        process to exit, and return every byte captured from its stdout."""
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
        self._reader.join(timeout=1)
        return bytes(self.captured)


def run_scripted_session(cmd):
    """initialize -> notifications/initialized -> tools/list -> tools/call,
    returning (raw captured stdout bytes, parsed tools/list response)."""
    session = ScriptedSession(cmd)

    init = session.send_request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "fourgate-test", "version": "0.1"},
        },
    )
    assert init is not None and "result" in init, f"bad initialize response: {init}"

    session.send_notification("notifications/initialized")

    tools = session.send_request("tools/list", {})
    assert tools is not None and "result" in tools, f"bad tools/list response: {tools}"

    call = session.send_request(
        "tools/call", {"name": "add_numbers", "arguments": {"a": 2, "b": 3}}
    )
    assert call is not None and "result" in call, f"bad tools/call response: {call}"

    captured = session.close()
    return captured, tools


def _direct_cmd():
    return [sys.executable, str(CLEAN_SERVER)]


def _wrapped_cmd():
    return [sys.executable, str(WRAP), "--", sys.executable, str(CLEAN_SERVER)]


def test_healthy_session_byte_identical():
    direct_bytes, _ = run_scripted_session(_direct_cmd())
    wrapped_bytes, _ = run_scripted_session(_wrapped_cmd())

    assert wrapped_bytes == direct_bytes


def test_tool_list_unchanged():
    _, direct_tools = run_scripted_session(_direct_cmd())
    _, wrapped_tools = run_scripted_session(_wrapped_cmd())

    assert wrapped_tools == direct_tools

    direct_names = [t["name"] for t in direct_tools["result"]["tools"]]
    wrapped_names = [t["name"] for t in wrapped_tools["result"]["tools"]]
    assert wrapped_names == direct_names
    assert wrapped_names == ["add_numbers", "get_greeting", "divide"]
