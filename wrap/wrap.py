#!/usr/bin/env python3
"""
Fourgate — runtime wrap (Steps 1-5a: raw byte proxy + call correlation +
fail-open classify gate + real silent_empty classifier)

Spawns a command-configured local stdio MCP server as a child process and
pumps bytes between the real client (this process's own stdin/stdout) and
the child, unchanged, in both directions. Alongside that forwarding, it
tracks which `tools/call` request a later response belongs to, and runs
every resolved `tools/call` result through a bounded classify gate before
forwarding it.

classify.classify() is now real (Step 5a: baseline-gated silent_empty),
but its verdict is still discarded — what reaches the client is always
the original bytes. Wiring a verdict into the forwarded result is Step 6.
See specs/runtime-wrap.md FR-1, FR-2, FR-8, FR-12, FR-22 and plan.md
Step 5 / Step 5a.

Design decisions (plan.md D1-D5, D7):

  D1 - The exact bytes read from one side are the exact bytes written to
       the other. No JSON decode/re-encode touches the forwarded stream,
       so a healthy session stays byte-identical to running the server
       unwrapped. Parsing (below) only ever sees a copy.
  D2 - Both directions move raw bytes: this process's own stdin/stdout via
       `os.read`/`os.write` on the raw file descriptors (bypassing Python's
       TextIOWrapper, which would translate `\n` <-> `\r\n` on Windows),
       and the child's pipes opened with `text=False`.
  D3 - The child's stderr is inherited (not piped), so server logs reach
       the client's log exactly as they would unwrapped, and there is no
       stderr pipe for a chatty server to fill and deadlock on.
  D4 - Two plain reader threads (client->child, child->client) rather than
       `selectors` - `select()` on Windows does not accept subprocess
       pipes (see checker/preflight.py for the same constraint).
  D5 - The 100 ms budget (FR-2) is a real timeout, not an assumption that
       classification is fast. Classify runs on a fresh daemon thread; the
       calling thread waits on a `concurrent.futures.Future` with
       `result(timeout=0.1)`. Timeout, exception, or (later) an
       unparseable result all resolve to `None` — the original bytes are
       what gets forwarded either way. The clock starts when the line is
       fully received, so a slow classifier cannot push added latency past
       the budget. The thread is daemon so a hung classify can never block
       process shutdown.
  D7 - `CallTracker` records `id -> tool name` when a `tools/call` request
       passes client->server, and consumes that entry when the matching
       response passes server->client. A response with no tracked id, or
       whose id resolves but which carries no `result`, resolves to no
       binding — "no result, no verdict; unknown id, no verdict." This is
       what a later classify/verdict gate will use to know which tool a
       result belongs to, without ever needing to trust the payload itself
       for identity.

Usage:
    python wrap/wrap.py [--baseline PATH] -- <command> [args...]
"""

import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Sibling modules (flat scripts, no packaging — matching checker/'s
# convention). Running this file directly already puts its own directory
# first on sys.path, but a test loading it via importlib doesn't, so make
# that explicit rather than depend on how this module gets imported.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import baseline  # noqa: E402
import classify  # noqa: E402

CHUNK_SIZE = 65536
CLASSIFY_BUDGET_SECS = 0.1  # FR-2 / D5 — 100 ms wall-clock per result


def _parse_argv(argv):
    """Split `[wrap options...] -- <command> [args...]` into wrap-side
    options and the command half.

    Step 5a adds `--baseline PATH`; later steps add --server-label/
    --selfcheck here without changing how the command half is found.

    Returns `(baseline_path_or_None, target_cmd)`.
    """
    if "--" in argv:
        idx = argv.index("--")
        wrap_args, target_cmd = argv[:idx], argv[idx + 1 :]
    else:
        wrap_args, target_cmd = [], argv

    baseline_path = None
    i = 0
    while i < len(wrap_args):
        if wrap_args[i] == "--baseline" and i + 1 < len(wrap_args):
            baseline_path = wrap_args[i + 1]
            i += 2
        else:
            i += 1

    return baseline_path, target_cmd


def _pump(read_fd, write_target, on_eof=None, on_line=None):
    """Copy raw bytes from `read_fd` to `write_target` until EOF or error.

    `write_target` is either a raw fd (int) or a file object with .write()
    (used for the child's stdin pipe). Each read is a single `os.read`
    call, so a small message is forwarded as soon as it arrives instead of
    waiting for a full CHUNK_SIZE buffer to accumulate. Forwarding happens
    first and unconditionally; `on_line` (if given) then gets a *copy* of
    each complete newline-delimited line assembled from the same bytes —
    it can never affect what was already written downstream (D1).
    """
    line_buf = bytearray() if on_line is not None else None
    try:
        while True:
            try:
                data = os.read(read_fd, CHUNK_SIZE)
            except OSError:
                break
            if not data:
                break
            try:
                if isinstance(write_target, int):
                    os.write(write_target, data)
                else:
                    write_target.write(data)
                    write_target.flush()
            except (BrokenPipeError, OSError, ValueError):
                break
            if on_line is not None:
                line_buf.extend(data)
                while True:
                    idx = line_buf.find(b"\n")
                    if idx == -1:
                        break
                    line = bytes(line_buf[:idx])
                    del line_buf[: idx + 1]
                    on_line(line)
    finally:
        if on_eof is not None:
            on_eof()


def _close_quietly(closeable):
    try:
        closeable.close()
    except OSError:
        pass


def _try_parse_json_object(line_bytes):
    """Best-effort JSON-RPC line parse for inspection only. Never raises;
    anything that isn't a decodable JSON object is simply not tracked."""
    try:
        text = line_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


class CallTracker(object):
    """Binds a `tools/call` response back to the tool it was a call to
    (D7), from a copy of the traffic only — it never influences what gets
    forwarded.

    `resolve_response` answers "which tool, if any, is this result for" so
    a later classify/verdict gate can act on it. It answers `None` (no
    binding) for exactly the D7 cases: an id that was never tracked, or a
    tracked id whose response carries no `result` (e.g. a JSON-RPC error).
    Either way the entry is consumed — a second response for the same id
    resolves to nothing, matching FR-24's "bind only to the originating
    call" for the non-cancellation case this step covers.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}  # request id -> tool name

    def track_request(self, line_bytes):
        obj = _try_parse_json_object(line_bytes)
        if obj is None or obj.get("method") != "tools/call":
            return
        req_id = obj.get("id")
        if req_id is None:
            return  # a notification has no id and can never be resolved
        params = obj.get("params") or {}
        tool_name = params.get("name")
        with self._lock:
            self._pending[req_id] = tool_name

    def resolve_response(self, line_bytes):
        obj = _try_parse_json_object(line_bytes)
        if obj is None:
            return None
        resp_id = obj.get("id")
        if resp_id is None:
            return None
        with self._lock:
            tool_name = self._pending.pop(resp_id, None)
        if tool_name is None:
            return None  # unknown id -> no verdict
        if "result" not in obj:
            return None  # no result -> no verdict
        return tool_name


def _run_classify_gate(result_obj, tool_name, contract):
    """Run `classify.classify()` under the FR-2 / D5 budget and return its
    verdict, or `None` on timeout, exception, or any other internal
    failure. Never raises, never blocks past `CLASSIFY_BUDGET_SECS`.

    Uses a bare `Future` plus a daemon thread (rather than a persistent
    executor) so a hung classifier can never delay this process's
    shutdown: daemon threads are dropped, not joined, at interpreter exit.

    `FOURGATE_FAULT` is a test-only hook (never read outside this
    function, and never seen by classify.py itself) that lets tests
    inject the two failure modes FR-2 has to survive:
      - "raise": an internal error during classification.
      - "hang":  classification that never returns on its own.
    """
    future = concurrent.futures.Future()

    def _worker():
        try:
            fault = os.environ.get("FOURGATE_FAULT")
            if fault == "raise":
                raise RuntimeError("FOURGATE_FAULT=raise")
            if fault == "hang":
                time.sleep(5)  # far past the budget — must never be waited on
            result = classify.classify(result_obj, tool_name, contract)
        except Exception as exc:
            future.set_exception(exc)
        else:
            future.set_result(result)

    threading.Thread(target=_worker, daemon=True).start()

    try:
        return future.result(timeout=CLASSIFY_BUDGET_SECS)
    except Exception:
        return None


def _forward_response_line(line, write_fd, tracker, loaded_baseline):
    """Handle one complete server->client line: gate it through classify
    if (and only if) it's the result of a tracked `tools/call`, then
    forward it. The verdict is still discarded here — the bytes written
    are always the line's original bytes; wiring a verdict into the
    forwarded result is Step 6.
    """
    tool_name = tracker.resolve_response(line)
    if tool_name is not None:
        result_obj = _try_parse_json_object(line)
        contract = baseline.lookup(loaded_baseline, tool_name)
        _run_classify_gate(result_obj, tool_name, contract)  # verdict discarded (Step 5a)
    try:
        os.write(write_fd, line + b"\n")
    except OSError:
        pass


def _pump_responses(read_fd, write_fd, tracker, loaded_baseline, on_eof=None):
    """Server->client direction only. Unlike `_pump`, this forwards at
    line granularity rather than per-raw-chunk: a `tools/call` result has
    to be gated through classify (bounded, D5) before it can be forwarded,
    so we cannot write bytes downstream until we know whether the line
    they belong to needs that gate. Every other line — the majority of
    traffic: initialize/tools-list responses, notifications, errors — is
    forwarded immediately once complete, with no gate (FR-1's ungated,
    byte-identical pass-through for non-tools/call traffic).

    This still satisfies D1: what's written is exactly the bytes received,
    just reassembled at newline boundaries instead of read()-call
    boundaries — the forwarded byte *content* is unaffected.
    """
    buf = bytearray()
    try:
        while True:
            try:
                data = os.read(read_fd, CHUNK_SIZE)
            except OSError:
                break
            if not data:
                break
            buf.extend(data)
            while True:
                idx = buf.find(b"\n")
                if idx == -1:
                    break
                line = bytes(buf[:idx])
                del buf[: idx + 1]
                _forward_response_line(line, write_fd, tracker, loaded_baseline)
        if buf:
            # A trailing chunk with no terminating newline (e.g. the child
            # exited mid-write). Nothing to classify — forward as-is.
            try:
                os.write(write_fd, bytes(buf))
            except OSError:
                pass
    finally:
        if on_eof is not None:
            on_eof()


def run_proxy(target_cmd, loaded_baseline=None):
    """Spawn `target_cmd` and proxy stdio bytes until it exits.

    Returns the child's exit code.
    """
    proc = subprocess.Popen(
        target_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,  # inherited — D3
        bufsize=0,
    )

    tracker = CallTracker()

    stdin_to_child = threading.Thread(
        target=_pump,
        args=(0, proc.stdin),
        kwargs={
            "on_eof": lambda: _close_quietly(proc.stdin),
            "on_line": tracker.track_request,
        },
        daemon=True,
    )
    child_to_stdout = threading.Thread(
        target=_pump_responses,
        args=(proc.stdout.fileno(), 1, tracker, loaded_baseline),
        daemon=True,
    )

    stdin_to_child.start()
    child_to_stdout.start()

    returncode = proc.wait()
    # Let any output already in flight reach our stdout before we exit.
    child_to_stdout.join(timeout=2)

    return returncode


def main():
    baseline_path, target_cmd = _parse_argv(sys.argv[1:])
    if not target_cmd:
        print(
            "usage: wrap.py [--baseline PATH] -- <command> [args...]",
            file=sys.stderr,
        )
        sys.exit(2)

    loaded_baseline = baseline.load(baseline_path)

    try:
        returncode = run_proxy(target_cmd, loaded_baseline)
    except FileNotFoundError as exc:
        print(f"fourgate: failed to start wrapped server: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(returncode if returncode is not None else 1)


if __name__ == "__main__":
    main()
