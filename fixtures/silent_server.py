#!/usr/bin/env python3
"""
fixtures/silent_server.py — minimal hand-rolled stdio MCP server for
Fourgate's Step 6 rewrite tests.

Not built on FastMCP (unlike fixtures/clean_server.py and
fixtures/broken_server.py): those tests need exact, fully-controlled
response shapes — including a result carrying a sibling field alongside
empty content — that FastMCP's automatic content-wrapping doesn't expose
a way to produce. checker/preflight.py already speaks raw JSON-RPC
directly for the same kind of reason (precise control over the exact
message shape under test), so this follows that precedent.

Tools:
  fetch_document(doc_id)
      Always returns empty content — a silent_empty candidate. `doc_id`
      is never echoed into the response, so a value placed there (e.g. a
      test canary) can never appear in any response this server sends.

  fetch_document_with_debug(doc_id, debug_value)
      Same empty content, but the raw result also carries a sibling
      `debug` field echoing `debug_value` verbatim — simulating a tool
      whose "empty" result still carries unrelated internal metadata.
      Exists to prove Fourgate's silent_empty rewrite does not carry
      that metadata forward to the client (wrap/verdict.py replaces the
      whole result rather than merging into it).

  search_tickets(query)
      Returns a well-formed, non-empty zero-result payload — not empty
      per D8 (structural presence, not semantic emptiness) — used to
      confirm classify() does NOT fire and the response passes through
      byte-identical.
"""

import json
import sys

TOOLS = [
    {
        "name": "fetch_document",
        "description": "Fetch a document by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
    },
    {
        "name": "fetch_document_with_debug",
        "description": "Fetch a document by id, echoing a debug value into internal result metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "debug_value": {"type": "string"},
            },
            "required": ["doc_id", "debug_value"],
        },
    },
    {
        "name": "search_tickets",
        "description": "Search tickets matching a query.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _handle_call(name, arguments):
    if name == "fetch_document":
        return {"content": [], "isError": False}
    if name == "fetch_document_with_debug":
        return {
            "content": [],
            "isError": False,
            "debug": {"echoed": arguments.get("debug_value")},
        }
    if name == "search_tickets":
        payload = json.dumps(
            {"results": [], "count": 0, "query": arguments.get("query")}
        )
        return {"content": [{"type": "text", "text": payload}], "isError": False}
    return {
        "content": [{"type": "text", "text": f"unknown tool: {name}"}],
        "isError": True,
    }


def _write(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "silent-demo-server", "version": "0.1"},
                    },
                }
            )
        elif method == "notifications/initialized":
            pass  # notifications get no response
        elif method == "tools/list":
            _write({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _handle_call(name, arguments),
                }
            )
        elif msg_id is not None:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )


if __name__ == "__main__":
    main()
