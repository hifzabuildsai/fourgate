"""Local MCP fixture with a Resend-style text response; sends no email."""
import json
import os
import sys
from pathlib import Path


def reply(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            reply({"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "local-resend-text-fixture", "version": "0.1"}}})
        elif method == "tools/list":
            reply({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [{
                "name": "send_email", "inputSchema": {"type": "object", "properties": {
                    "to": {"type": "string"}}, "required": ["to"]}}]}})
        elif method == "tools/call":
            args = message["params"]["arguments"]
            mode = os.environ.get("FOURGATE_RESEND_MODE", "healthy")
            if mode == "healthy":
                Path(os.environ["FOURGATE_DEMO_STORE"]).write_text(json.dumps({
                    "id": "email_test_001", "to": args["to"]}), encoding="utf-8")
            payload = ('Email sent successfully! {"id":"email_test_001"}'
                       if mode != "no_id" else "Email sent successfully!")
            reply({"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": payload}], "isError": False}})
        elif request_id is not None:
            reply({"jsonrpc": "2.0", "id": request_id, "error": {
                "code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
