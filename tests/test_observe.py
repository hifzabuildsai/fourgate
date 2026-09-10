"""
--observe PATH — permanent observation mode (new scope beyond plan.md
Steps 1-7; see wrap/observe.py's module docstring).

For every resolved tools/call result, wrap.py appends one shape-only
JSON line to the path given by --observe: timestamp, server label, tool
name, isError, content block count, whether any content text is
non-empty, whether structuredContent is present, total payload size in
bytes, and whether FR-8 (silent_empty) would have fired against the
loaded baseline.

This replaces a temporary debug hook that logged actual field values and
was deleted for exactly that reason. The whole point of this mode is
that it MUST NOT be that hook again: no tool argument value, no result
field value, no file path, no URL, no user content. test_canary_absent_*
below plants a canary in both an argument and a result body (the same
value in both places, via search_tickets' query -> content echo) and a
second canary in a raw result field outside `content`
(fetch_document_with_debug's sibling `debug` field), then asserts
neither appears anywhere in the observe file — not just in one field,
but nowhere in the raw bytes written to it.

Uses fixtures/silent_server.py and tests/fixtures/silent_server_baseline.json,
the same fixtures test_rewrite.py drives, so a captured record's expected
shape can be checked against known tool behavior:
  - fetch_document: always empty content, baseline requires content ->
    fr8_would_fire True.
  - fetch_document_with_debug: same, plus a sibling `debug` field the
    observe record must never surface.
  - search_tickets: well-formed non-empty zero-result payload -> not
    empty per D8, fr8_would_fire False.
"""

import json
import sys
from pathlib import Path

from _support import ScriptedSession, run_initialize

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAP = REPO_ROOT / "wrap" / "wrap.py"
SILENT_SERVER = REPO_ROOT / "fixtures" / "silent_server.py"
BASELINE = REPO_ROOT / "tests" / "fixtures" / "silent_server_baseline.json"

SERVER_LABEL = "silent-demo-server"


def wrapped_cmd(observe_path):
    return [
        sys.executable,
        str(WRAP),
        "--baseline",
        str(BASELINE),
        "--server-label",
        SERVER_LABEL,
        "--observe",
        str(observe_path),
        "--",
        sys.executable,
        str(SILENT_SERVER),
    ]


def _start_session(observe_path):
    session = ScriptedSession(wrapped_cmd(observe_path))
    run_initialize(session)
    tools = session.send_request("tools/list", {})
    assert tools is not None and "result" in tools, f"bad tools/list response: {tools}"
    return session


def _read_records(observe_path):
    if not observe_path.exists():
        return []
    lines = observe_path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line]


def test_observe_records_shape_only_fields(tmp_path):
    """Every field the mode promises is present, and the two known calls
    classify exactly as the fixture/baseline predict."""
    observe_path = tmp_path / "observe.jsonl"
    session = _start_session(observe_path)
    try:
        empty_response = session.send_request(
            "tools/call", {"name": "fetch_document", "arguments": {"doc_id": "doc-1"}}
        )
        search_response = session.send_request(
            "tools/call", {"name": "search_tickets", "arguments": {"query": "q"}}
        )
        session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()

    assert empty_response is not None and "result" in empty_response
    assert search_response is not None and "result" in search_response

    records = _read_records(observe_path)
    assert len(records) == 2, f"expected one record per tools/call result, got: {records}"

    expected_keys = {
        "timestamp",
        "server",
        "tool",
        "is_error",
        "is_protocol_error",
        "content_block_count",
        "content_text_nonempty",
        "structured_content_present",
        "payload_bytes",
        "fr8_would_fire",
    }
    for record in records:
        assert set(record.keys()) == expected_keys, record

    fetch_record, search_record = records

    assert fetch_record["server"] == SERVER_LABEL
    assert fetch_record["tool"] == "fetch_document"
    assert fetch_record["is_error"] is False
    assert fetch_record["is_protocol_error"] is False
    assert fetch_record["content_block_count"] == 0
    assert fetch_record["content_text_nonempty"] is False
    assert fetch_record["structured_content_present"] is False
    assert fetch_record["payload_bytes"] > 0
    assert fetch_record["fr8_would_fire"] is True  # baseline requires content; empty -> fires

    assert search_record["tool"] == "search_tickets"
    assert search_record["is_error"] is False
    assert search_record["is_protocol_error"] is False
    assert search_record["content_block_count"] == 1
    assert search_record["content_text_nonempty"] is True
    assert search_record["fr8_would_fire"] is False  # well-formed zero-result payload, not empty


def test_observe_absent_by_default():
    """No --observe flag -> no file, no behavior change (the mode is
    off-by-default, matching every other flag in this codebase)."""
    session = ScriptedSession(
        [
            sys.executable,
            str(WRAP),
            "--baseline",
            str(BASELINE),
            "--server-label",
            SERVER_LABEL,
            "--",
            sys.executable,
            str(SILENT_SERVER),
        ]
    )
    run_initialize(session)
    try:
        response = session.send_request(
            "tools/call", {"name": "fetch_document", "arguments": {"doc_id": "doc-1"}}
        )
        session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()
    assert response is not None and "result" in response


def test_canary_absent_from_observe_output(tmp_path):
    """The canary test: a value planted as a tool ARGUMENT that the
    fixture server echoes into its RESULT body (search_tickets' `query`
    -> content text), plus a second value planted directly in a raw
    RESULT field outside `content` (fetch_document_with_debug's sibling
    `debug` field), must appear nowhere in the observe file — not in any
    one field, but nowhere in its raw bytes at all.

    Both calls are confirmed to have actually carried their canary into
    the client-visible response first, so this test cannot pass vacuously
    by never having exercised the leak path it's checking.
    """
    canary_query = "CANARY-QUERY-4d81ac"
    canary_debug = "CANARY-DEBUG-b62f0e"

    observe_path = tmp_path / "observe.jsonl"
    session = _start_session(observe_path)
    try:
        search_response = session.send_request(
            "tools/call", {"name": "search_tickets", "arguments": {"query": canary_query}}
        )
        debug_response = session.send_request(
            "tools/call",
            {
                "name": "fetch_document_with_debug",
                "arguments": {"doc_id": "doc-1", "debug_value": canary_debug},
            },
        )
        session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()

    assert search_response is not None and "result" in search_response
    assert debug_response is not None and "result" in debug_response

    # Prove the canaries genuinely reached the client (not vacuous):
    search_text = search_response["result"]["content"][0]["text"]
    assert canary_query in search_text, "fixture stopped echoing the query into content"

    records = _read_records(observe_path)
    assert len(records) == 2

    observe_bytes = observe_path.read_bytes()
    assert canary_query.encode() not in observe_bytes
    assert canary_debug.encode() not in observe_bytes

    # And the records still reflect real, non-vacuous shape decisions —
    # not just "empty because nothing was recorded".
    tools_seen = {r["tool"] for r in records}
    assert tools_seen == {"search_tickets", "fetch_document_with_debug"}
