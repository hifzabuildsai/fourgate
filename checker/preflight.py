#!/usr/bin/env python3
"""
Fourgate — MCP Connector Preflight Checker (v0 demo)

Spawns an MCP server over stdio, speaks JSON-RPC to it directly (not through
the official client SDK), so we can catch and report the exact failure modes
a working demo needs to show:

  Check 1 — Stdout cleanliness: any non-JSON line on stdout breaks the
            JSON-RPC stream. We read raw and flag the first bad line.
  Check 2 — Schema robustness: for each declared tool, send one valid call
            and one deliberately malformed call (wrong argument type).
            A healthy server returns a clean JSON-RPC error for the bad
            call. A crash, a hang, or a raw traceback is a failure.

Usage:
    python3 preflight.py <path-to-server-script>
"""

import json
import subprocess
import sys
import selectors
import time
import textwrap
import argparse


TIMEOUT_SECS = 5

# Minimal ANSI color codes -- no extra dependency needed for a demo.
_COLOR = {
    "PASS": "\033[32m",   # green
    "FAIL": "\033[31m",   # red
    "WARN": "\033[33m",   # yellow
    "INFO": "\033[36m",   # cyan
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
}


def _use_color():
    return sys.stdout.isatty()


class Fourgate:
    def __init__(self, server_path: str):
        self.server_path = server_path
        self.proc = None
        self.sel = selectors.DefaultSelector()
        self._id = 0
        self.findings = []  # list of dicts: {level, check, message}

    def _next_id(self):
        self._id += 1
        return self._id

    def start(self):
        self.proc = subprocess.Popen(
            [sys.executable, self.server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.sel.register(self.proc.stdout, selectors.EVENT_READ, "stdout")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _send(self, method: str, params: dict = None, notification: bool = False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notification:
            msg["id"] = self._next_id()
        line = json.dumps(msg)
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return msg.get("id")

    def _read_raw_line(self, timeout=TIMEOUT_SECS):
        """Read one line from the server's stdout, raw. Returns None on timeout/EOF."""
        events = self.sel.select(timeout=timeout)
        if not events:
            return None
        line = self.proc.stdout.readline()
        if line == "":
            return None
        return line.rstrip("\n")

    def _read_json_message(self, expect_id=None, timeout=TIMEOUT_SECS):
        """
        Read lines until we get one that parses as JSON (recording any
        non-JSON lines as stdout-pollution findings along the way), or we
        time out / hit EOF.
        """
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
                    "level": "FAIL",
                    "check": "stdout_cleanliness",
                    "message": f"Non-JSON output on stdout broke the JSON-RPC stream: {line!r}",
                })
                continue  # keep reading, the real response may still arrive
            if expect_id is not None and obj.get("id") != expect_id:
                continue
            return obj
        return None

    # ---- protocol handshake ----

    def initialize(self):
        req_id = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "fourgate", "version": "0.1"},
        })
        resp = self._read_json_message(expect_id=req_id)
        if resp is None:
            self.findings.append({
                "level": "FAIL",
                "check": "handshake",
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
                "level": "FAIL",
                "check": "tools_list",
                "message": "tools/list did not return a valid result.",
            })
            return []
        tools = resp["result"].get("tools", [])
        self.findings.append({
            "level": "INFO",
            "check": "tools_list",
            "message": f"Discovered {len(tools)} tool(s): {[t['name'] for t in tools]}",
        })
        return tools

    # ---- per-tool checks ----

    def _sample_valid_args(self, schema: dict) -> dict:
        args = {}
        props = schema.get("properties", {})
        for name, prop in props.items():
            t = prop.get("type")
            if t == "integer" or t == "number":
                args[name] = 1
            elif t == "string":
                args[name] = "test"
            elif t == "boolean":
                args[name] = True
            else:
                args[name] = "test"
        return args

    def _sample_edge_case_args(self, schema: dict) -> dict | None:
        """Zero out numeric args -- a schema-valid but common crash trigger
        (division by zero, index -1, empty-string edge cases, etc)."""
        props = schema.get("properties", {})
        has_numeric = any(p.get("type") in ("integer", "number") for p in props.values())
        if not has_numeric:
            return None
        args = {}
        for name, prop in props.items():
            t = prop.get("type")
            if t in ("integer", "number"):
                args[name] = 0
            elif t == "string":
                args[name] = "test"
            elif t == "boolean":
                args[name] = True
            else:
                args[name] = "test"
        return args

    def _mutate_to_wrong_type(self, args: dict) -> dict:
        """Flip the first arg to an obviously wrong type."""
        mutated = dict(args)
        for k, v in mutated.items():
            if isinstance(v, (int, float)):
                mutated[k] = "not-a-number"
            elif isinstance(v, str):
                mutated[k] = {"unexpected": "object"}
            break
        return mutated

    def call_tool(self, name: str, args: dict, label: str):
        req_id = self._send("tools/call", {"name": name, "arguments": args})
        resp = self._read_json_message(expect_id=req_id)

        if self.proc.poll() is not None:
            self.findings.append({
                "level": "FAIL",
                "check": f"tool_call:{name}:{label}",
                "message": f"Server process CRASHED after this call (exit code {self.proc.returncode}). "
                            f"No fail-closed error was returned to the caller.",
            })
            return

        if resp is None:
            self.findings.append({
                "level": "FAIL",
                "check": f"tool_call:{name}:{label}",
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
                    "level": "WARN",
                    "check": f"tool_call:{name}:{label}",
                    "message": "Malformed call returned a normal result instead of an error — "
                                "the server likely coerced bad input silently instead of validating it.",
                })
            else:
                self.findings.append({
                    "level": "PASS",
                    "check": f"tool_call:{name}:{label}",
                    "message": "Call completed normally.",
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
                break  # already dead, no point sending more

            bad_args = self._mutate_to_wrong_type(valid_args)
            self.call_tool(tool["name"], bad_args, "malformed")

            if self.proc.poll() is None:
                edge_args = self._sample_edge_case_args(tool.get("inputSchema", {}))
                if edge_args is not None:
                    self.call_tool(tool["name"], edge_args, "edge_case")

            if self.proc.poll() is not None:
                self.findings.append({
                    "level": "FAIL",
                    "check": f"crash_recovery:{tool['name']}",
                    "message": "Server did not survive the malformed call — it needs a fresh process for the next check.",
                })
                break

        self.stop()
        return self.findings


def print_report(server_path: str, findings: list):
    color = _use_color()

    def c(level, text):
        if not color:
            return text
        return f"{_COLOR[level]}{text}{_COLOR['RESET']}"

    print()
    title = f"Fourgate Preflight Report — {server_path}"
    print(c("BOLD", title) if color else title)
    print("=" * 60)

    fails = [f for f in findings if f["level"] == "FAIL"]
    warns = [f for f in findings if f["level"] == "WARN"]
    passes = [f for f in findings if f["level"] == "PASS"]

    icons = {"PASS": "✔", "FAIL": "✘", "WARN": "⚠", "INFO": "ℹ"}
    for f in findings:
        icon = icons[f["level"]]
        wrapped = textwrap.fill(f["message"], width=70, subsequent_indent="    ")
        line = f"  {icon} [{f['check']}] {wrapped}"
        print(c(f["level"], line) if f["level"] in _COLOR else line)

    print("-" * 60)
    summary = f"  {len(passes)} passed, {len(fails)} failed, {len(warns)} warnings"
    print(summary)
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


def print_json_report(server_path: str, findings: list):
    fails = [f for f in findings if f["level"] == "FAIL"]
    warns = [f for f in findings if f["level"] == "WARN"]
    passes = [f for f in findings if f["level"] == "PASS"]
    result = "not_safe_to_ship" if fails else ("review_warnings" if warns else "all_clear")
    payload = {
        "server": server_path,
        "result": result,
        "counts": {"passed": len(passes), "failed": len(fails), "warnings": len(warns)},
        "findings": findings,
    }
    print(json.dumps(payload, indent=2))
    return 1 if fails else 0


def main():
    parser = argparse.ArgumentParser(
        prog="fourgate",
        description="Fourgate — checks whether your MCP connector actually "
                     "protects identity and fails closed, before a user finds out it doesn't.",
    )
    parser.add_argument("server_path", help="Path to the MCP server script to check")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of a human report")
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
