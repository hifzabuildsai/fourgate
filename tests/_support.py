"""
Shared test scaffolding: a scripted stdio JSON-RPC client used to drive
fixtures/clean_server.py directly and through wrap/wrap.py.

Not a test module itself (no test_ prefix) — imported by test_passthrough.py
and test_failopen.py so the driver logic exists exactly once.
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

    def __init__(self, cmd, env=None):
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env=env,
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


def direct_cmd():
    return [sys.executable, str(CLEAN_SERVER)]


def wrapped_cmd():
    return [sys.executable, str(WRAP), "--", sys.executable, str(CLEAN_SERVER)]


def run_initialize(session):
    """initialize -> notifications/initialized, asserting both succeed.
    Shared prefix every scripted session in these tests starts with."""
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
    return init
