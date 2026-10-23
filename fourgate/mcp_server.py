"""Experimental local stdio MCP configuration validation. Never executes writes.

Only validate_workflow is exposed. All target commands, verifiers and endpoints
remain inert. This is an explicit legacy/current tools subset, not a gateway.
"""
import argparse
import json
import re
import sys

from . import __version__, scan
from .workflows import WorkflowRegistry

LEGACY = ("2024-11-05", "2025-11-25")
VERSIONS = (*LEGACY, scan.MODERN_PROTOCOL)
MAX_MESSAGE_BYTES = 1024 * 1024
USAGE = "fourgate mcp --registry PATH"
OUTPUT_SCHEMA = {"type": "object", "properties": {
    "workflow_id": {"type": "string"},
    "readiness": {"type": "string", "enum": ["CONFIG_VALID", "NOT_READY"]},
    "action_status": {"type": "string", "enum": ["NOT_RUN"]},
    "scope": {"type": "string", "enum": ["STATIC_CONFIG_ONLY"]},
    "reason_code": {"type": "string"},
    "planned_cases": {"type": "integer", "minimum": 1},
    "missing_credential_count": {"type": "integer", "minimum": 1}},
    "required": ["readiness", "action_status", "scope", "reason_code"], "additionalProperties": False}


def error(mid, code, message, data=None):
    value = {"code": code, "message": message}
    if data is not None:
        value["data"] = data
    return {"jsonrpc": "2.0", "id": mid, "error": value}


def tool_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
            "structuredContent": payload, "isError": payload.get("readiness") != "CONFIG_VALID"}


class Server:
    def __init__(self, registry):
        self.registry = registry
        self._legacy_pending = False
        self._legacy_ready = False

    def dispatch(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return error(None, -32600, "Invalid request")
        method, mid = message.get("method"), message.get("id")
        if not isinstance(method, str):
            return error(None, -32600, "Invalid request")
        if "id" not in message:
            if method == "notifications/initialized" and self._legacy_pending:
                self._legacy_ready = True
            # Requests without an ID must never trigger tool execution.
            return None
        if type(mid) not in (str, int):
            return error(None, -32600, "Invalid request ID")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return error(mid, -32602, "Invalid params")
        meta = params.get("_meta", {})
        if not isinstance(meta, dict):
            return error(mid, -32602, "Invalid metadata")
        version = meta.get(scan.VERSION_META)
        modern = scan.VERSION_META in meta or scan.CAPABILITIES_META in meta
        if modern:
            if not isinstance(version, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", version):
                return error(mid, -32602, "Protocol version required in date format")
            if version != scan.MODERN_PROTOCOL:
                return error(mid, -32022, "Unsupported protocol version", {"supported": list(VERSIONS),
                                                                          "requested": version})
            if not isinstance(meta.get(scan.CAPABILITIES_META), dict):
                return error(mid, -32602, "Client capabilities required")

        def reply(result, cacheable=False):
            if modern:
                result = {**result, "resultType": "complete"}
                if cacheable:
                    result.update(ttlMs=0, cacheScope="private")
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        if method == "initialize" and not modern:
            version = params.get("protocolVersion")
            if not isinstance(version, str) or not isinstance(params.get("capabilities"), dict):
                return error(mid, -32602, "Invalid initialize params")
            self._legacy_pending = True
            return reply({"protocolVersion": version if version in LEGACY else LEGACY[0],
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "fourgate-validation", "version": __version__}})
        if method == "ping":
            return reply({})
        if method == "server/discover":
            if not modern:
                return error(mid, -32601, "Method not found")
            return reply({"supportedVersions": list(VERSIONS), "capabilities": {"tools": {}}}, True)
        if not modern and not self._legacy_ready:
            return error(mid, -32002, "Initialize required")
        if method == "tools/list":
            return reply({"tools": [{
                "name": "validate_workflow",
                "description": "Check a registered Fourgate scan configuration and declared credential presence. "
                               "No server start, verifier, network or write. CONFIG_VALID is readiness; action is NOT_RUN.",
                "inputSchema": {"type": "object", "properties": {"workflow_id": {
                    "type": "string", "enum": self.registry.ids}},
                    "required": ["workflow_id"], "additionalProperties": False},
                "outputSchema": OUTPUT_SCHEMA,
                "annotations": {"readOnlyHint": True, "destructiveHint": False,
                                "idempotentHint": True, "openWorldHint": False},
            }]}, True)
        if method == "tools/call":
            if params.get("name") != "validate_workflow":
                return error(mid, -32602, "Unknown tool")
            args = params.get("arguments", {})
            if (not isinstance(args, dict) or set(args) != {"workflow_id"}
                    or not isinstance(args["workflow_id"], str) or len(args["workflow_id"]) > 64):
                return reply(tool_result({"readiness": "NOT_READY", "action_status": "NOT_RUN",
                                          "scope": "STATIC_CONFIG_ONLY", "reason_code": "invalid_arguments"}))
            return reply(tool_result(self.registry.validate(args["workflow_id"])))
        return error(mid, -32601, "Method not found")


def main(argv):
    parser = argparse.ArgumentParser(prog="fourgate mcp", usage=USAGE,
        description="Serve read-only registered workflow validation over local stdio MCP. No action execution.")
    parser.add_argument("--registry", required=True, help="Operator-maintained local workflow registry JSON")
    args = parser.parse_args(argv)
    try:
        server = Server(WorkflowRegistry(args.registry))
    except (OSError, ValueError, RecursionError, RuntimeError):
        print("fourgate mcp: registry configuration invalid or unavailable", file=sys.stderr)
        return 2
    while True:
        raw = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
        if not raw:
            return 0
        if len(raw) > MAX_MESSAGE_BYTES:
            print(json.dumps(error(None, -32600, "Request exceeds 1 MiB")), flush=True)
            return 1
        try:
            message = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            response = error(None, -32700, "Parse error")
        else:
            try:
                response = server.dispatch(message)
            except Exception:
                # Preserve correlation; never expose a path, credential or traceback.
                mid = message.get("id") if isinstance(message, dict) else None
                response = error(mid if type(mid) in (str, int) else None, -32603, "Internal validation error")
        if response is not None:
            print(json.dumps(response, ensure_ascii=True), flush=True)
