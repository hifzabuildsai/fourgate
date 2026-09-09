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

    def write_request(self, method, params=None):
        """Write a request and return its id without reading a response —
        used to put a call "in flight" so the process can be killed before
        it completes."""
        self._next_id += 1
        req_id = self._next_id
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        return req_id

    def send_request(self, method, params=None):
        req_id = self.write_request(method, params)
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


def test_call_does_not_complete_without_wrap():
    """plan.md Step 2 — on-path proof (FR-1).

    Fourgate must sit *on* the path, not beside it as a passive recorder:
    if killing the wrap process itself still let a pending call complete,
    something else would have to be relaying client<->server traffic and
    the wrap would just be watching. Send a tools/call, kill the wrap with
    no read in between (so the call is genuinely in flight, not already
    answered), and assert the client never sees a response.
    """
    session = ScriptedSession(_wrapped_cmd())
    try:
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

        # Put a call in flight, then kill the wrap immediately — no read
        # in between — before it has any chance to relay a response back.
        req_id = session.write_request(
            "tools/call", {"name": "add_numbers", "arguments": {"a": 2, "b": 3}}
        )
        session.proc.kill()
        session.proc.wait(timeout=3)

        response = session._read_json_line(expect_id=req_id, timeout=1.5)
        assert response is None, (
            f"tools/call completed even though the wrap process was killed "
            f"mid-call: {response}"
        )
    finally:
        if session.proc.poll() is None:
            session.proc.kill()
        try:
            session.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        session._reader.join(timeout=1)
