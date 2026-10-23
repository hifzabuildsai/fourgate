"""Isolated stdio protocol fixture, not a production server or SDK conformance test.

Subset pinned to modelcontextprotocol/modelcontextprotocol commit
80041ab0a139a8f4fb3adbc99f7ae9113ea59671, schema/2026-07-28/schema.ts,
and the dated 2024-11-05 / 2025-11-25 lifecycle specifications.
Only temporary local files are touched. No credentials or network are used.
"""
import argparse
import json
import sys
from pathlib import Path

MODERN = "2026-07-28"
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--era", choices=("legacy", "native", "compat"), required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--control", choices=("healthy", "missing", "input_required", "unknown_type",
                                            "unsupported_version", "discovery_input_required", "missing_result_type",
                                            "discovery_missing_type", "list_missing_type", "wrong_versions"), default="healthy")
    args = parser.parse_args()
    legacy_version = None
    for raw in sys.stdin:
        message = json.loads(raw)
        with args.trace.open("a", encoding="utf-8") as trace:
            trace.write(json.dumps(message) + "\n")
        method = message["method"]
        if "id" not in message:
            continue
        params = message.get("params", {})
        meta = params.get("_meta", {})
        version = meta.get(VERSION_KEY)
        modern = version is not None
        error, result = None, None
        if method == "initialize" and args.era != "native":
            requested = params["protocolVersion"]
            legacy_version = requested if requested in ("2024-11-05", "2025-11-25") else "2025-11-25"
            result = {"protocolVersion": legacy_version, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "fourgate-protocol-fixture", "version": "1"}}
        elif modern and args.era != "legacy":
            if version != MODERN or args.control == "unsupported_version":
                error = {"code": -32022, "message": "Unsupported protocol version",
                         "data": {"supported": ["2099-01-01"], "requested": version}}
            elif meta.get(CAPABILITIES_KEY) != {}:
                error = {"code": -32602, "message": "Missing client capabilities"}
            elif method == "server/discover":
                result = {"resultType": "complete", "supportedVersions": [MODERN],
                          "capabilities": {"tools": {}}}
                if args.control == "discovery_input_required":
                    result = {"resultType": "input_required", "requestState": "fixture-only"}
                elif args.control == "wrong_versions":
                    result["supportedVersions"] = ["2099-01-01"]
        elif not legacy_version or args.era == "native":
            error = {"code": -32601, "message": "Method not available in this lifecycle"}

        if error is None and result is None:
            if method == "tools/list":
                result = {"tools": [{"name": "create_issue", "inputSchema": {
                    "type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}]}
            elif method == "tools/call" and params.get("name") == "create_issue":
                if args.control == "input_required":
                    result = {"resultType": "input_required", "requestState": "fixture-only"}
                elif args.control == "unknown_type":
                    result = {"resultType": "future-fixture-result"}
                else:
                    if args.control in ("healthy", "missing_result_type"):
                        args.store.write_text(json.dumps([{"id": "ISSUE-001", "title": params[
                            "arguments"]["title"]}]), encoding="utf-8")
                    result = {"content": [{"type": "text", "text": "Created ISSUE-001"}],
                              "structuredContent": {"issue_id": "ISSUE-001"}, "isError": False}
            else:
                error = {"code": -32601, "message": "Method not found"}
        if result is not None:
            if modern:
                result.setdefault("resultType", "complete")
                if method in ("server/discover", "tools/list") and result["resultType"] == "complete":
                    result.update(ttlMs=0, cacheScope="private")
                if (args.control == "missing_result_type" and method == "tools/call"
                        or args.control == "discovery_missing_type" and method == "server/discover"
                        or args.control == "list_missing_type" and method == "tools/list"):
                    del result["resultType"]  # explicitly induced invalid-protocol controls
            response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        else:
            response = {"jsonrpc": "2.0", "id": message["id"], "error": error}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
