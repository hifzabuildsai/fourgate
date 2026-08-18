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

Results print locally AND (unless --no-upload is passed) get pushed to a
shared Supabase table, so every run — yours or a student's — lands in the
same place instead of staying stuck on one laptop.

Usage:
    python3 preflight.py <path-to-server-script> [--json] [--no-upload] [--checked-by "name"]
"""

import json
import subprocess
import sys
import selectors
import time
import textwrap
import argparse
import urllib.request
import urllib.error


TIMEOUT_SECS = 5

# Public, insert-only Supabase project for the Fourgate v0 shared eval log.
# The key below is a publishable/anon key restricted by RLS to insert+select
# only (no update, no delete) -- safe to ship in this open-source script.
# Override with env vars if you want your own project instead.
import os
SUPABASE_URL = os.environ.get("FOURGATE_SUPABASE_URL", "https://qkuvvlzeqosvfcherlyp.supabase.co")
SUPABASE_KEY = os.environ.get(
    "FOURGATE_SUPABASE_KEY",
    "sb_publishable_B9fM7-VOLy1TT7yEY0C1cA_aHNGfsBh",
)

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
        self.sel = selectors.DefaultSelector()
        self._id = 0
        self.findings = []

    def _next_id(self):
        self._id += 1
        return self._id

    def start(self):
        self.proc = subprocess.Popen(
            [sys.executable, self.server_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.sel.register(self.proc.stdout, selectors.EVENT_READ, "stdout")

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
        events = self.sel.select(timeout=timeout)
        if not events:
            return None
        line = self.proc.stdout.readline()
        return None if line == "" else line.rstrip("\n")

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
        return self.findings


def summarize(findings):
    fails = [f for f in findings if f["level"] == "FAIL"]
    warns = [f for f in findings if f["level"] == "WARN"]
    passes = [f for f in findings if f["level"] == "PASS"]
    result = "not_safe_to_ship" if fails else ("review_warnings" if warns else "all_clear")
    return passes, fails, warns, result


def upload_to_supabase(server_path, findings, checked_by):
    """Push this run + its findings to the shared Supabase log. Never raises --
    a failed upload should never break the local report."""
    passes, fails, warns, result = summarize(findings)
    try:
        run_payload = json.dumps({
            "connector_name": server_path,
            "language": "python",
            "checked_by": checked_by or "anonymous",
            "total_checks": len(findings),
            "passed": len(passes),
            "failed": len(fails),
            "warnings": len(warns),
            "overall_result": result,
        }).encode()

        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/runs",
            data=run_payload,
            method="POST",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            run_row = json.loads(resp.read())[0]
        run_id = run_row["id"]

        findings_payload = json.dumps([
            {"run_id": run_id, "level": f["level"], "check_type": f["check"], "message": f["message"]}
            for f in findings
        ]).encode()
        req2 = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/findings",
            data=findings_payload,
            method="POST",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
        )
        urllib.request.urlopen(req2, timeout=5)
        return True, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, IndexError) as e:
        return False, str(e)


def print_report(server_path, findings, uploaded, upload_error):
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
    if uploaded:
        print(c("INFO" if color else "", "  ↑ synced to shared log"))
    elif upload_error is not None:
        print(f"  (not synced: {upload_error})")
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


def print_json_report(server_path, findings, uploaded, upload_error):
    passes, fails, warns, result = summarize(findings)
    payload = {
        "server": server_path, "result": result,
        "counts": {"passed": len(passes), "failed": len(fails), "warnings": len(warns)},
        "findings": findings, "synced": uploaded, "sync_error": upload_error,
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
    parser.add_argument("--no-upload", action="store_true", help="Skip syncing this run to the shared log")
    parser.add_argument("--checked-by", default=None, help="Your name — tags this run in the shared log")
    args = parser.parse_args()

    checker = Fourgate(args.server_path)
    findings = checker.run()

    uploaded, upload_error = (False, None)
    if not args.no_upload:
        uploaded, upload_error = upload_to_supabase(args.server_path, findings, args.checked_by)

    if args.json:
        exit_code = print_json_report(args.server_path, findings, uploaded, upload_error)
    else:
        exit_code = print_report(args.server_path, findings, uploaded, upload_error)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
