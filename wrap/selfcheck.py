#!/usr/bin/env python3
"""
Fourgate — self-check (plan.md Step 7, FR-18)

Proves Fourgate is actually on the path without waiting for a real
failure. Per FR-18: "The self-check MUST exercise the same live
intercept-and-rewrite path used for real tools/call responses... Printing
a standalone sample object, log entry, or dashboard preview does not
satisfy this requirement." And D6: "The self-check does not call it
[classify+rewrite] directly at all — it drives a real wrapped server over
real stdio."

So this module does not import classify.classify()/verdict.attach() and
construct a printed sample. It spawns a SEPARATE, real `wrap.py`
subprocess — the exact command a client config produces per FR-17 —
wrapping the real fixtures/silent_server.py with a real baseline, speaks
actual JSON-RPC to it over its actual stdin/stdout, and reads the verdict
back from the literal bytes that subprocess wrote to its stdout. If the
wrap were removed from between this script and the fixture server (see
`FOURGATE_SELFCHECK_BYPASS`, test-only), the [FOURGATE] marker this looks
for would never appear, and the self-check reports failure — the same
way it would if Fourgate genuinely weren't wired in.

The JSON-RPC client below duplicates ~40 lines already present in
checker/preflight.py and tests/_support.py (background reader thread +
queue, since select() doesn't accept subprocess pipes on Windows).
Refactoring it out of the shipped free preflight tool for one more
caller isn't worth the coupling (plan.md R3) — this module has to keep
working standalone, without depending on tests/.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAP = Path(__file__).resolve().parent / "wrap.py"
SILENT_SERVER = REPO_ROOT / "fixtures" / "silent_server.py"
BASELINE = REPO_ROOT / "tests" / "fixtures" / "silent_server_baseline.json"

TIMEOUT_SECS = 5.0
FOURGATE_MARKER = "[FOURGATE]"


class _JsonRpcClient:
    """Minimal stdio JSON-RPC client, Windows-safe line reading via a
    background thread + queue."""

    def __init__(self, cmd):
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._queue = queue.Queue()
        self._next_id = 0
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_drain.start()

    def _read_loop(self):
        try:
            for line in iter(self.proc.stdout.readline, b""):
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

    def _read_json_line(self, expect_id, timeout=TIMEOUT_SECS):
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
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass


def _default_wrap_cmd():
    """The real wrap.py, wrapping the real fixtures/silent_server.py,
    with a real baseline — exactly the shape FR-17's config edit
    produces. This is a client's-eye view of Fourgate, not a printed
    sample.

    FOURGATE_SELFCHECK_BYPASS is a test-only hook (never read anywhere
    else) that swaps this for the raw fixture server with no wrap in
    front of it at all, so tests/test_selfcheck.py can prove the
    self-check reports failure — not success — when Fourgate genuinely
    isn't on the path.
    """
    if os.environ.get("FOURGATE_SELFCHECK_BYPASS"):
        return [sys.executable, str(SILENT_SERVER)]
    return [
        sys.executable,
        str(WRAP),
        "--baseline",
        str(BASELINE),
        "--server-label",
        "selfcheck",
        "--",
        sys.executable,
        str(SILENT_SERVER),
    ]


def get_verdict(wrap_cmd=None):
    """Drive initialize -> tools/list -> tools/call(fetch_document)
    through a real subprocess over its real stdio, and return the
    verdict dict embedded in the response — the same [FOURGATE]-prefixed
    text content item a real MCP client would receive — or `None` if no
    verdict arrived.
    """
    cmd = wrap_cmd if wrap_cmd is not None else _default_wrap_cmd()
    client = _JsonRpcClient(cmd)
    try:
        init = client.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fourgate-selfcheck", "version": "0.1"},
            },
        )
        if init is None or "result" not in init:
            return None

        client.send_notification("notifications/initialized")

        tools = client.send_request("tools/list", {})
        if tools is None or "result" not in tools:
            return None

        response = client.send_request(
            "tools/call",
            {"name": "fetch_document", "arguments": {"doc_id": "selfcheck"}},
        )
        if response is None or "result" not in response:
            return None

        content = response["result"].get("content") or []
        if len(content) != 1:
            return None  # not the rewrite's single-item shape (FR-5)
        text = content[0].get("text", "")
        if not text.startswith(FOURGATE_MARKER):
            return None  # no attribution marker -> not a Fourgate verdict

        try:
            return json.loads(text[len(FOURGATE_MARKER) :].strip())
        except json.JSONDecodeError:
            return None
    finally:
        client.close()


def run(wrap_cmd=None):
    """Entry point for `wrap.py --selfcheck`. Prints the verdict and
    returns 0 on success; prints a diagnostic to stderr and returns 1 if
    none arrived.
    """
    verdict = get_verdict(wrap_cmd)
    if verdict is None:
        # Printed to stdout, not stderr: this line is this tool's report,
        # the same way the success line below is — a caller scripting
        # around --selfcheck should be able to capture either outcome
        # from one stream, keying off the exit code for pass/fail.
        print(
            "fourgate selfcheck: FAILED — no verdict arrived through the "
            "live intercept path."
        )
        return 1
    print("fourgate selfcheck: OK — verdict received through the live intercept path:")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(run())
