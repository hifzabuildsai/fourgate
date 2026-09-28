#!/usr/bin/env python3
"""Demo MCP server: create_issue can claim success without persisting it."""
import json
import os
import sys
from pathlib import Path

TOOLS=[{
    "name":"create_issue",
    "description":"Create an issue.",
    "inputSchema":{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]},
}]
ISSUE_ID="ISSUE-001"

def _store_path(): return Path(os.environ["FOURGATE_DEMO_STORE"])
def _read_store():
    p=_store_path()
    if not p.exists(): return []
    try:
        data=json.loads(p.read_text(encoding="utf-8")); return data if isinstance(data,list) else []
    except Exception: return []
def _persist(title):
    rows=_read_store(); rows=[r for r in rows if r.get("id")!=ISSUE_ID]; rows.append({"id":ISSUE_ID,"title":title})
    p=_store_path(); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(rows),encoding="utf-8")
def _write(obj): sys.stdout.write(json.dumps(obj)+"\n"); sys.stdout.flush()
def main():
    mode=os.environ.get("FOURGATE_DEMO_MODE","broken")
    for raw in sys.stdin:
        if not raw.strip(): continue
        try: msg=json.loads(raw)
        except json.JSONDecodeError: continue
        method=msg.get("method"); mid=msg.get("id")
        if method=="initialize":
            _write({"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"outcome-demo-server","version":"0.1"}}})
        elif method=="notifications/initialized": pass
        elif method=="tools/list": _write({"jsonrpc":"2.0","id":mid,"result":{"tools":TOOLS}})
        elif method=="tools/call":
            params=msg.get("params") or {}; name=params.get("name"); args=params.get("arguments") or {}
            if name!="create_issue":
                _write({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":"unknown tool"}],"isError":True}}); continue
            if mode=="healthy": _persist(args.get("title"))
            _write({"jsonrpc":"2.0","id":mid,"result":{
                "content":[{"type":"text","text":f"Created {ISSUE_ID}"}],
                "structuredContent":{} if mode=="no_record_id" else {"issue_id":ISSUE_ID},
                "isError":False
            }})
        elif mid is not None: _write({"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"method not found"}})
if __name__=="__main__": main()
