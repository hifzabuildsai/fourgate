#!/usr/bin/env python3
"""Runnable Fourgate Outcome Guard proof: false success -> catch -> healthy control."""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WRAP = ROOT / "wrap" / "wrap.py"
SERVER = ROOT / "fixtures" / "outcome_server.py"
CONTRACTS = ROOT / "fixtures" / "contracts" / "outcome_demo.json"
MARKER = "[FOURGATE]"


class Client:
    def __init__(self, cmd, env):
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=ROOT, bufsize=0)
        self.q = queue.Queue(); self.i = 0
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain, daemon=True).start()
    def _read(self):
        for line in iter(self.proc.stdout.readline, b""): self.q.put(line)
        self.q.put(None)
    def _drain(self):
        for _ in iter(self.proc.stderr.readline, b""): pass
    def request(self, method, params=None):
        self.i += 1; msg={"jsonrpc":"2.0","id":self.i,"method":method}
        if params is not None: msg["params"]=params
        self.proc.stdin.write((json.dumps(msg)+"\n").encode()); self.proc.stdin.flush()
        while True:
            line=self.q.get(timeout=5)
            if line is None: return None
            obj=json.loads(line)
            if obj.get("id")==self.i: return obj
    def notify(self, method):
        self.proc.stdin.write((json.dumps({"jsonrpc":"2.0","method":method})+"\n").encode()); self.proc.stdin.flush()
    def close(self):
        try: self.proc.stdin.close()
        except OSError: pass
        try: self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(timeout=3)


def run(cmd, store, mode):
    env=os.environ.copy(); env["FOURGATE_DEMO_STORE"]=str(store); env["FOURGATE_DEMO_MODE"]=mode
    c=Client(cmd,env)
    try:
        assert "result" in c.request("initialize", {"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"fourgate-demo","version":"0.1"}})
        c.notify("notifications/initialized")
        assert "result" in c.request("tools/list", {})
        return c.request("tools/call", {"name":"create_issue","arguments":{"title":"Outcome Guard demo"}})
    finally: c.close()


def persisted(store):
    if not store.exists(): return []
    return json.loads(store.read_text(encoding="utf-8"))


def first_text(resp): return resp["result"]["content"][0]["text"]


def main():
    with tempfile.TemporaryDirectory(prefix="fourgate-outcome-") as td:
        d=Path(td)
        direct_store=d/"direct.json"
        broken=run([sys.executable,str(SERVER)],direct_store,"broken")
        print("1) WITHOUT FOURGATE")
        print("   connector ->", first_text(broken))
        print("   system of record ->", persisted(direct_store))
        assert first_text(broken)=="Created ISSUE-001" and persisted(direct_store)==[]

        guarded_store=d/"guarded.json"
        guarded_cmd=[sys.executable,str(WRAP),"--outcome-contracts",str(CONTRACTS),"--outcome-mode","enforce","--server-label","demo","--",sys.executable,str(SERVER)]
        caught=run(guarded_cmd,guarded_store,"broken")
        print("\n2) WITH FOURGATE — BROKEN WRITE")
        print("   first content ->", caught["result"]["content"][0]["text"])
        print("   original content preserved ->", caught["result"]["content"][1]["text"])
        assert first_text(caught).startswith(MARKER)
        verdict=json.loads(first_text(caught)[len(MARKER):].strip())
        assert verdict["kind"]=="outcome_failed" and verdict["evidence"]["reason_code"]=="record_missing"
        assert caught["result"]["content"][1]["text"]=="Created ISSUE-001"

        healthy_store=d/"healthy.json"
        healthy=run(guarded_cmd,healthy_store,"healthy")
        print("\n3) WITH FOURGATE — HEALTHY CONTROL")
        print("   connector ->", first_text(healthy))
        print("   system of record ->", persisted(healthy_store))
        assert first_text(healthy)=="Created ISSUE-001" and len(persisted(healthy_store))==1
        assert MARKER not in first_text(healthy)

        print("\nDEMO PASS: false success caught; original content preserved; healthy write unchanged.")
        return 0


if __name__ == "__main__": raise SystemExit(main())
