"""Local stdio workflow tools. Read-only unless an operator opts into execution."""
import argparse
import json
import re
import sys

from . import __version__, scan
from .workflows import WorkflowRegistry

LEGACY = ("2024-11-05", "2025-11-25")
VERSIONS = (*LEGACY, scan.MODERN_PROTOCOL)
MAX_MESSAGE_BYTES = 1024 * 1024
USAGE = "fourgate mcp --registry PATH [--execution-policy PATH] [--prepare-execution-state]"
OUTPUT_SCHEMA = {"type": "object", "properties": {
    "workflow_id": {"type": "string"},
    "readiness": {"type": "string", "enum": ["CONFIG_VALID", "NOT_READY"]},
    "action_status": {"type": "string", "enum": ["NOT_RUN"]},
    "scope": {"type": "string", "enum": ["STATIC_CONFIG_ONLY"]},
    "reason_code": {"type": "string"},
    "planned_cases": {"type": "integer", "minimum": 1},
    "missing_credential_count": {"type": "integer", "minimum": 1}},
    "required": ["readiness", "action_status", "scope", "reason_code"], "additionalProperties": False}
RUN_SCHEMA = {"type": "object", "properties": {
    "report_version": {"type": "integer", "enum": [1]},
    "run_id": {"type": "string"}, "workflow_id": {"type": "string"},
    "new_execution": {"type": "boolean", "description":
        "Whether this request invoked the scanner; false for saved reports/replays. Not proof of persistence."},
    "contract_sha256": {"type": "string"}, "fourgate_version": {"type": "string"},
    "run_state": {"type": "string", "enum": ["NOT_STARTED", "COMPLETED", "UNCERTAIN"]},
    "action_status": {"type": "string", "enum": ["NOT_RUN", "ATTEMPTED", "UNCERTAIN"],
        "description": "Recorded run's write-call status. See new_execution for the current request."},
    "verdict": {"type": "string", "enum": ["PASS", "FAIL", "UNKNOWN"]},
    "reason_code": {"type": "string"},
    "reserved_tool_calls": {"type": "integer", "minimum": 0, "maximum": 20},
    "call_attempts": {"type": "integer", "minimum": 0, "maximum": 20},
    "cases": {"type": "array", "maxItems": 20, "items": {"type": "object", "properties": {
        "case_index": {"type": "integer", "minimum": 1, "maximum": 20},
        "status": {"type": "string", "enum": ["PASS", "FAIL", "UNKNOWN"]},
        "reason_code": {"type": "string"}},
        "required": ["case_index", "status", "reason_code"], "additionalProperties": False}}},
    "required": ["report_version", "run_state", "action_status", "reason_code", "new_execution"],
    "additionalProperties": False}


def error(mid, code, message, data=None):
    value = {"code": code, "message": message}
    if data is not None:
        value["data"] = data
    return {"jsonrpc": "2.0", "id": mid, "error": value}


def tool_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
            "structuredContent": payload, "isError": (payload.get("readiness") != "CONFIG_VALID"
                if "readiness" in payload else payload.get("verdict") != "PASS")}


class Server:
    def __init__(self, registry, runner=None):
        self.registry = registry
        self.runner = runner
        self._legacy_pending = False
        self._legacy_ready = False

    def tools(self):
        tools = [{
            "name": "validate_workflow",
            "description": "Check a registered scan configuration and declared credential presence. "
                           "No server start, verifier, network or write. CONFIG_VALID is readiness; action is NOT_RUN.",
            "inputSchema": {"type": "object", "properties": {"workflow_id": {
                "type": "string", "enum": self.registry.ids}}, "required": ["workflow_id"],
                "additionalProperties": False}, "outputSchema": OUTPUT_SCHEMA,
            "annotations": {"readOnlyHint": True, "destructiveHint": False,
                            "idempotentHint": True, "openWorldHint": False}}]
        if self.runner is not None:
            tools.extend([{
                "name": "run_workflow",
                "description": "Execute a registered disposable workflow under a single-use operator grant. "
                    "May perform consequential writes and network access via trusted configured commands. "
                    "Repeated run IDs return prior state; UNKNOWN is not PASS. No rollback or write retry.",
                "inputSchema": {"type": "object", "properties": {
                    "workflow_id": {"type": "string", "enum": self.registry.ids},
                    "run_id": {"type": "string", "enum": self.runner.ids}},
                    "required": ["workflow_id", "run_id"], "additionalProperties": False},
                "outputSchema": RUN_SCHEMA, "annotations": {"readOnlyHint": False,
                    "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}}, {
                "name": "get_run_report",
                "description": "Read a bounded structural report for an operator-issued run ID. "
                    "No target execution or replay. Process success does not establish an action PASS.",
                "inputSchema": {"type": "object", "properties": {
                    "run_id": {"type": "string", "enum": self.runner.ids}},
                    "required": ["run_id"], "additionalProperties": False},
                "outputSchema": RUN_SCHEMA, "annotations": {"readOnlyHint": True,
                    "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}])
        return tools

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
            return reply({"tools": self.tools()}, True)
        if method == "tools/call":
            if self.runner is not None and params.get("name") in ("run_workflow", "get_run_report"):
                args = params.get("arguments", {})
                required = {"workflow_id", "run_id"} if params["name"] == "run_workflow" else {"run_id"}
                if (not isinstance(args, dict) or set(args) != required
                        or any(not isinstance(v, str) or not 1 <= len(v) <= 64 for v in args.values())):
                    from .execution import not_run
                    return reply(tool_result(not_run("invalid_arguments")))
                payload = (self.runner.run(args["workflow_id"], args["run_id"])
                           if params["name"] == "run_workflow" else self.runner.get_report(args["run_id"]))
                return reply(tool_result(payload))
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
        description="Serve registered workflows over local stdio MCP. Default: read-only validation. "
                    "Execution requires a separate operator policy and prepared single-use state.")
    parser.add_argument("--registry", required=True, help="Operator-maintained local workflow registry JSON")
    parser.add_argument("--execution-policy", help="Operator-controlled single-use run grants; enables write tools")
    parser.add_argument("--prepare-execution-state", action="store_true",
        help="Create new private grant state without running actions; refuses existing state")
    args = parser.parse_args(argv)
    if args.prepare_execution_state and not args.execution_policy:
        parser.error("--prepare-execution-state requires --execution-policy")
    try:
        registry = WorkflowRegistry(args.registry)
        runner = None
        if args.execution_policy:
            from .execution import ExecutionPolicy, ExecutionState, WorkflowRunner
            policy = ExecutionPolicy(args.execution_policy, registry)
            if args.prepare_execution_state:
                ExecutionState.prepare(policy)
                print("fourgate mcp: execution state prepared; actions NOT_RUN", file=sys.stderr)
                return 0
            runner = WorkflowRunner(registry, policy)
        server = Server(registry, runner)
    except Exception:
        print("fourgate mcp: registry configuration or execution state invalid or unavailable", file=sys.stderr)
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
