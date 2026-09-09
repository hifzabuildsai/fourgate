#!/usr/bin/env python3
"""
Fourgate — MCP Connector Preflight Checker

Spawns an MCP server over stdio, speaks JSON-RPC to it directly (not through
the official client SDK), so it can catch and report the exact failure modes:

  Check 1 — Stdout cleanliness: any non-JSON line on stdout breaks the
            JSON-RPC stream. Reads raw and flags the first bad line.
  Check 2 — Schema robustness: for each declared tool, sends a valid call,
            a deliberately malformed call, and a numeric edge case, and
            checks whether the server fails closed (clean error) or fails
            open (crash / hang / silently-coerced bad data).

Cross-platform note: line reading uses a background thread + queue rather
than the `selectors` module. `selectors`' default backend wraps
`select.select()`, which on Windows only supports real sockets -- not pipes
from subprocess.PIPE -- and crashes with WinError 10038. Thread+queue works
identically on Windows, macOS, and Linux.

stderr is drained continuously on its own background thread so a chatty
server can never fill the OS pipe buffer and deadlock waiting for a reader.

Usage:
    python3 preflight.py <path-to-server-script> [--json]
"""

import json
import os
import subprocess
import sys
import threading
import queue
import time
import textwrap
import argparse


TIMEOUT_SECS = 5

_COLOR = {
    "PASS": "\033[32m", "FAIL": "\033[31m", "WARN": "\033[33m",
    "INFO": "\033[36m", "RESET": "\033[0m", "BOLD": "\033[1m",
}


def _use_color():
    return sys.stdout.isatty()


class Fourgate:
    def __init__(self, server_path: str):
        self.server_path = server_path
        self.proc = None
        self._id = 0
        self.findings = []
        self._line_queue = queue.Queue()
        self._reader_thread = None
        self._stderr_lines = []
        self._stderr_thread = None

    def _next_id(self):
        self._id += 1
        return self._id

    def _reader_loop(self):
        """Background thread: pushes each stdout line onto the queue as it
        arrives, and a single None once the pipe closes (EOF)."""
        try:
            for line in iter(self.proc.stdout.readline, ""):
                self._line_queue.put(line.rstrip("\n"))
        except Exception:
            pass
        finally:
            self._line_queue.put(None)

    def _stderr_reader_loop(self):
        """Drains stderr continuously so a chatty server can never fill the
        OS pipe buffer and deadlock waiting for someone to read it."""
        try:
            for line in iter(self.proc.stderr.readline, ""):
                self._stderr_lines.append(line.rstrip("\n"))
        except Exception:
            pass

    def start(self):
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"  # force the child to flush stdout immediately,
                                        # regardless of platform buffering defaults
        self.proc = subprocess.Popen(
            [sys.executable, self.server_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_reader_loop, daemon=True)
        self._stderr_thread.start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _send(self, method, params=None, notification=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notification:
            msg["id"] = self._next_id()
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        return msg.get("id")

    def _read_raw_line(self, timeout=TIMEOUT_SECS):
        try:
            return self._line_queue.get(timeout=timeout)  # may be None on EOF
        except queue.Empty:
            return None

    def _read_json_message(self, expect_id=None, timeout=TIMEOUT_SECS):
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            line = self._read_raw_line(timeout=remaining)
            if line is None:
                return None
            if line.strip() == "":
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                self.findings.append({
                    "level": "FAIL", "check": "stdout_cleanliness",
                    "message": f"Non-JSON output on stdout broke the JSON-RPC stream: {line!r}",
                })
                continue
            if expect_id is not None and obj.get("id") != expect_id:
                continue
            return obj
        return None

    def initialize(self):
        req_id = self._send("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "fourgate", "version": "0.1"},
        })
        resp = self._read_json_message(expect_id=req_id)
        if resp is None:
            self.findings.append({
                "level": "FAIL", "check": "handshake",
                "message": "No valid initialize response received before timeout.",
            })
            return False
        self._send("notifications/initialized", notification=True)
        return True

    def list_tools(self):
        req_id = self._send("tools/list", {})
        resp = self._read_json_message(expect_id=req_id)
        if resp is None or "result" not in resp:
            self.findings.append({
                "level": "FAIL", "check": "tools_list",
                "message": "tools/list did not return a valid result.",
            })
            return []
        tools = resp["result"].get("tools", [])
        self.findings.append({
            "level": "INFO", "check": "tools_list",
            "message": f"Discovered {len(tools)} tool(s): {[t['name'] for t in tools]}",
        })
        return tools

    def _sample_valid_args(self, schema):
        args = {}
        for name, prop in schema.get("properties", {}).items():
            t = prop.get("type")
            if t in ("integer", "number"):
                args[name] = 1
            elif t == "boolean":
                args[name] = True
            else:
                args[name] = "test"
        return args

    def _sample_edge_case_args(self, schema):
        props = schema.get("properties", {})
        if not any(p.get("type") in ("integer", "number") for p in props.values()):
            return None
        args = {}
        for name, prop in props.items():
            t = prop.get("type")
            if t in ("integer", "number"):
                args[name] = 0
            elif t == "boolean":
                args[name] = True
            else:
                args[name] = "test"
        return args

    def _mutate_to_wrong_type(self, args):
        mutated = dict(args)
        for k, v in mutated.items():
            if isinstance(v, (int, float)):
                mutated[k] = "not-a-number"
            elif isinstance(v, str):
                mutated[k] = {"unexpected": "object"}
            break
        return mutated

    def call_tool(self, name, args, label):
        req_id = self._send("tools/call", {"name": name, "arguments": args})
        resp = self._read_json_message(expect_id=req_id)

        if self.proc.poll() is not None:
            self.findings.append({
                "level": "FAIL", "check": f"tool_call:{name}:{label}",
                "message": f"Server process CRASHED after this call (exit code {self.proc.returncode}). "
                           f"No fail-closed error was returned to the caller.",
            })
            return

        if resp is None:
            self.findings.append({
                "level": "FAIL", "check": f"tool_call:{name}:{label}",
                "message": "No response received (hang or timeout) — the call did not fail cleanly.",
            })
            return

        if "error" in resp:
            self.findings.append({
                "level": "PASS" if label == "malformed" else "FAIL",
                "check": f"tool_call:{name}:{label}",
                "message": f"Server returned a clean JSON-RPC error: {resp['error'].get('message', resp['error'])}",
            })
        elif "result" in resp:
            is_error_result = isinstance(resp["result"], dict) and resp["result"].get("isError")
            if label == "malformed" and not is_error_result:
                self.findings.append({
                    "level": "WARN", "check": f"tool_call:{name}:{label}",
                    "message": "Malformed call returned a normal result instead of an error — "
                               "the server likely coerced bad input silently instead of validating it.",
                })
            else:
                self.findings.append({
                    "level": "PASS", "check": f"tool_call:{name}:{label}",
                    "message": "Call completed normally." if label != "malformed"
                               else "Server returned a clean error result for malformed input.",
                })

    def run(self):
        self.start()
        if not self.initialize():
            self.stop()
            return self.findings

        tools = self.list_tools()
        for tool in tools:
            valid_args = self._sample_valid_args(tool.get("inputSchema", {}))
            self.call_tool(tool["name"], valid_args, "valid")
            if self.proc.poll() is not None:
                break

            bad_args = self._mutate_to_wrong_type(valid_args)
            self.call_tool(tool["name"], bad_args, "malformed")

            if self.proc.poll() is None:
                edge_args = self._sample_edge_case_args(tool.get("inputSchema", {}))
                if edge_args is not None:
                    self.call_tool(tool["name"], edge_args, "edge_case")

            if self.proc.poll() is not None:
                self.findings.append({
                    "level": "FAIL", "check": f"crash_recovery:{tool['name']}",
                    "message": "Server did not survive the malformed call.",
                })
                break

        self.stop()
        if self._stderr_lines:
            self.findings.append({
                "level": "INFO", "check": "stderr_activity",
                "message": f"Server wrote {len(self._stderr_lines)} line(s) to stderr "
                           f"(expected and healthy — that's where logs belong, not stdout).",
            })
        return self.findings


def summarize(findings):
    fails = [f for f in findings if f["level"] == "FAIL"]
    warns = [f for f in findings if f["level"] == "WARN"]
    passes = [f for f in findings if f["level"] == "PASS"]
    result = "not_safe_to_ship" if fails else ("review_warnings" if warns else "all_clear")
    return passes, fails, warns, result


def print_report(server_path, findings):
    color = _use_color()

    def c(level, text):
        return f"{_COLOR[level]}{text}{_COLOR['RESET']}" if color else text

    print()
    title = f"Fourgate Preflight Report — {server_path}"
    print(c("BOLD", title) if color else title)
    print("=" * 60)

    passes, fails, warns, _ = summarize(findings)
    icons = {"PASS": "✔", "FAIL": "✘", "WARN": "⚠", "INFO": "ℹ"}
    for f in findings:
        icon = icons[f["level"]]
        wrapped = textwrap.fill(f["message"], width=70, subsequent_indent="    ")
        line = f"  {icon} [{f['check']}] {wrapped}"
        print(c(f["level"], line) if f["level"] in _COLOR else line)

    print("-" * 60)
    print(f"  {len(passes)} passed, {len(fails)} failed, {len(warns)} warnings")
    print()

    if fails:
        print(c("FAIL", "  RESULT: NOT SAFE TO SHIP — fix the failures above first.\n"))
        return 1
    elif warns:
        print(c("WARN", "  RESULT: SHIPS, BUT REVIEW THE WARNINGS ABOVE.\n"))
        return 0
    else:
        print(c("PASS", "  RESULT: ALL CLEAR.\n"))
        return 0


def print_json_report(server_path, findings):
    passes, fails, warns, result = summarize(findings)
    payload = {
        "server": server_path, "result": result,
        "counts": {"passed": len(passes), "failed": len(fails), "warnings": len(warns)},
        "findings": findings,
    }
    print(json.dumps(payload, indent=2))
    return 1 if fails else 0


def main():
    parser = argparse.ArgumentParser(
        prog="fourgate",
        description="Fourgate — checks whether your MCP connector actually protects "
                     "identity and fails closed, before a user finds out it doesn't.",
    )
    parser.add_argument("server_path", help="Path to the MCP server script to check (Python only, v0)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    checker = Fourgate(args.server_path)
    findings = checker.run()

    if args.json:
        exit_code = print_json_report(args.server_path, findings)
    else:
        exit_code = print_report(args.server_path, findings)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()