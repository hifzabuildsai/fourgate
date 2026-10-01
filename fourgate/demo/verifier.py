#!/usr/bin/env python3
"""Authoritative deterministic verifier for the demo issue store."""
import json
import os
import sys
import time
from pathlib import Path

def main():
    mode=os.environ.get("FOURGATE_DEMO_VERIFIER","normal")
    if mode=="crash": return 2
    if mode=="hang": time.sleep(1.0)
    if mode=="malformed": print("not-json"); return 0
    if mode=="unapproved": print(json.dumps({"status":"fail","reason_code":"raw_customer_value_mismatch"})); return 0
    try: fields=json.loads(sys.stdin.read())
    except Exception: return 2
    try:
        p=Path(os.environ["FOURGATE_DEMO_STORE"])
        rows=json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        if not isinstance(rows,list): raise ValueError("store is not a list")
    except Exception:
        # An unreadable or malformed authority cannot confirm record absence.
        return 2
    match=next((r for r in rows if r.get("id")==fields.get("issue_id")),None)
    evidence={"lookup":{"issue_id":fields.get("issue_id"),"record":match}}
    if match is None:
        print(json.dumps({"status":"fail","reason_code":"record_missing","evidence":evidence})); return 0
    if match.get("title") != fields.get("title"):
        print(json.dumps({"status":"fail","reason_code":"field_mismatch","evidence":evidence})); return 0
    print(json.dumps({"status":"pass"}))
    return 0

if __name__=="__main__": raise SystemExit(main())
