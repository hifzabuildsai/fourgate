#!/usr/bin/env python3
"""Authoritative deterministic verifier for the demo issue store."""
import json
import os
import sys
import time
from pathlib import Path

mode=os.environ.get("FOURGATE_DEMO_VERIFIER","normal")
if mode=="crash": sys.exit(2)
if mode=="hang": time.sleep(1.0)
if mode=="malformed": print("not-json"); sys.exit(0)
if mode=="unapproved": print(json.dumps({"status":"fail","reason_code":"raw_customer_value_mismatch"})); sys.exit(0)
try: fields=json.loads(sys.stdin.read())
except Exception: sys.exit(2)
try:
    p=Path(os.environ["FOURGATE_DEMO_STORE"])
    rows=json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
except Exception:
    rows=[]
match=next((r for r in rows if r.get("id")==fields.get("issue_id")),None)
if match is None:
    print(json.dumps({"status":"fail","reason_code":"record_missing"})); sys.exit(0)
if match.get("title") != fields.get("title"):
    print(json.dumps({"status":"fail","reason_code":"field_mismatch"})); sys.exit(0)
print(json.dumps({"status":"pass"}))
