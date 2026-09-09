"""
plan.md Step 3 — request/response correlation (D7).

Unit tests against wrap.CallTracker directly: this step forwards bytes
exactly as Steps 1-2 already do (verified by tests/test_passthrough.py),
so there is nothing new visible on the wire to assert on. What's new is
internal bookkeeping — id -> tool binding — that a later classify/verdict
gate will consume. No classify, verdict, or self-check exists yet.
"""

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_wrap_module():
    spec = importlib.util.spec_from_file_location(
        "fourgate_wrap", REPO_ROOT / "wrap" / "wrap.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wrap = _load_wrap_module()


def _line(obj):
    return json.dumps(obj).encode("utf-8")


def _call_request(req_id, tool_name, arguments=None):
    return _line(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        }
    )


def _result_response(req_id, result=None):
    return _line({"jsonrpc": "2.0", "id": req_id, "result": result or {}})


def _error_response(req_id, message="boom"):
    return _line(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": message}}
    )


def test_interleaved_ids_bind_to_correct_tool():
    tracker = wrap.CallTracker()

    # Two calls issued back-to-back, interleaved on the wire, before either
    # response comes back — exactly what concurrent tools/call traffic
    # looks like.
    tracker.track_request(_call_request(1, "add_numbers", {"a": 2, "b": 3}))
    tracker.track_request(_call_request(2, "get_greeting", {"name": "Hifza"}))

    # Responses arrive out of order (id 2 first). Each must resolve to the
    # tool it was actually a call to, not to send order or id order.
    assert tracker.resolve_response(_result_response(2, "Hello, Hifza!")) == (
        "get_greeting"
    )
    assert tracker.resolve_response(_result_response(1, 5)) == "add_numbers"

    # A third, non-interleaved call resolves correctly too.
    tracker.track_request(_call_request(3, "divide", {"a": 6, "b": 2}))
    assert tracker.resolve_response(_result_response(3, 3.0)) == "divide"

    # Each id is consumed exactly once — a duplicate/replayed response for
    # an id already resolved binds to nothing.
    assert tracker.resolve_response(_result_response(1, 5)) is None


def test_no_verdict_for_call_with_no_result():
    tracker = wrap.CallTracker()

    # Tracked id, but the response is a JSON-RPC error (no `result` key):
    # D7 — "no result, no verdict."
    tracker.track_request(_call_request(10, "divide", {"a": 1, "b": 0}))
    assert tracker.resolve_response(_error_response(10, "division by zero")) is None

    # An id that was never tracked (e.g. a tools/list response, or a
    # response for a call this tracker never saw) binds to nothing even
    # though it carries a `result`: D7 — "unknown id, no verdict."
    assert tracker.resolve_response(_result_response(999, {"tools": []})) is None

    # A response with no id at all (malformed, or a notification-shaped
    # line) is never a verdict candidate.
    assert tracker.resolve_response(_line({"jsonrpc": "2.0", "result": {}})) is None

    # Consuming the "no result" case above must not leave the entry
    # claimable by a later, better-formed response for the same id.
    assert tracker.resolve_response(_result_response(10, 3.0)) is None
