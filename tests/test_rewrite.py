"""
plan.md Step 6 — in-band verdict rewrite for silent_empty
(D6, FR-3, FR-4, FR-5, FR-13, FR-14, FR-15, FR-16).

Every test here goes through ScriptedSession against the real wrap
subprocess and asserts on the actual bytes the client receives — a unit
test on wrap/verdict.py alone would prove the rewrite function is
correct, not that it's actually reached from the live tools/call path
(the same reasoning FR-18's self-check is built on, applied here one
step early).

fixtures/silent_server.py is a small hand-rolled stdio server (not
FastMCP — see its module docstring for why) with three tools:
  - fetch_document(doc_id) -> always empty content.
  - fetch_document_with_debug(doc_id, debug_value) -> empty content plus
    a sibling `debug` field on the raw result, echoing debug_value.
  - search_tickets(query) -> a well-formed, non-empty zero-result
    payload (not a silent_empty candidate).

tests/fixtures/silent_server_baseline.json declares payload as required
(required_fields: ["content"]) for all three tools.
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
FOURGATE_MARKER = "[FOURGATE]"
VALID_KINDS = {"silent_empty", "fake_success", "auth_expiry", "token_bloat"}
VALID_RECOVERIES = {"stop", "ask_user", "retry_once"}


def wrapped_cmd():
    return [
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


def _start_session(env=None):
    session = ScriptedSession(wrapped_cmd(), env=env)
    run_initialize(session)
    tools = session.send_request("tools/list", {})
    assert tools is not None and "result" in tools, f"bad tools/list response: {tools}"
    return session


def _extract_verdict(response_obj):
    """Pull the embedded verdict JSON out of a tools/call response that
    went through the rewrite: content[0].text is "[FOURGATE] {...}"."""
    content = response_obj["result"]["content"]
    assert len(content) == 1, f"expected exactly one content item, got: {content}"
    text = content[0]["text"]
    assert text.startswith(FOURGATE_MARKER), f"missing attribution marker: {text!r}"
    payload = text[len(FOURGATE_MARKER) :].strip()
    return json.loads(payload)


def test_verdict_reaches_client_bytes():
    """FR-3 — a silent_empty result on a baselined tool must carry a
    verdict object in the actual bytes the client receives, not merely
    in a log/alert side channel (there is no such channel here at all)."""
    session = _start_session()
    try:
        response = session.send_request(
            "tools/call", {"name": "fetch_document", "arguments": {"doc_id": "doc-1"}}
        )
        session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()

    assert response is not None and "result" in response, f"bad response: {response}"
    verdict = _extract_verdict(response)

    assert verdict["kind"] == "silent_empty"
    assert verdict["tool"] == f"{SERVER_LABEL}/fetch_document"
    assert verdict["recovery"] == "stop"


def test_verdict_shape_and_enums():
    """FR-13 — exactly four keys. FR-14 — kind and recovery drawn from
    their closed sets."""
    session = _start_session()
    try:
        response = session.send_request(
            "tools/call", {"name": "fetch_document", "arguments": {"doc_id": "doc-2"}}
        )
        session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()

    verdict = _extract_verdict(response)

    assert set(verdict.keys()) == {"kind", "tool", "evidence", "recovery"}
    assert verdict["kind"] in VALID_KINDS
    assert verdict["recovery"] in VALID_RECOVERIES


def test_evidence_excludes_canary():
    """FR-15 — evidence must contain only computed structural facts:
    no tool argument value, no returned field value, no user content.

    Two canaries, two different leak vectors:
      - CANARY_ARG is a tool argument (fetch_document's doc_id). classify()
        never receives arguments at all, so this is trivially unreachable
        — included as a baseline sanity check, not because it's hard to
        get right.
      - CANARY_DEBUG is a field on the RAW result itself
        (fetch_document_with_debug's `debug` field), sitting alongside
        empty content. Since the response still counts as empty per D8
        (only `content`/`structuredContent`/`isError` are inspected),
        classify() still fires — and wrap/verdict.py's rewrite replaces
        the whole result rather than merging into it (FR-5: silent_empty
        is the degenerate case with no original content to preserve), so
        this field cannot survive into what the client receives either.

    Checked against the full raw byte stream the client received for the
    whole session, not just the parsed verdict — the strongest form of
    "appears nowhere in the client-visible output."
    """
    canary_arg = "CANARY-ARGUMENT-7f3a9c"
    canary_debug = "CANARY-DEBUG-91be2d"

    session = _start_session()
    try:
        arg_response = session.send_request(
            "tools/call",
            {"name": "fetch_document", "arguments": {"doc_id": canary_arg}},
        )
        debug_response = session.send_request(
            "tools/call",
            {
                "name": "fetch_document_with_debug",
                "arguments": {"doc_id": "irrelevant", "debug_value": canary_debug},
            },
        )
        captured = session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()

    assert arg_response is not None and "result" in arg_response
    assert debug_response is not None and "result" in debug_response

    # Both calls must still have matched (verdicts present) — otherwise
    # this test would trivially pass by never exercising the rewrite.
    _extract_verdict(arg_response)
    _extract_verdict(debug_response)

    assert canary_arg.encode() not in captured
    assert canary_debug.encode() not in captured


def test_no_network_no_alerts():
    """FR-20's spirit (alerting must never affect model-visible output)
    combined with FR-3's "in-band, no network required": there is no
    alerting feature in this codebase to disable, so that half is
    trivially satisfied. The teeth of this test are on egress: point
    every proxy env var at an address nothing listens on, and confirm
    the verdict still arrives, within the same tight timing envelope the
    other tests see. classify.py and wrap/verdict.py make zero network
    calls by construction (no socket/urllib/requests import anywhere in
    either), so a broken proxy configuration should have zero effect —
    if it somehow did depend on the network, this call would fail open
    (no verdict at all) or stall well past the 100 ms classify budget
    instead of returning promptly.
    """
    import os

    env = os.environ.copy()
    blackhole = "http://127.0.0.1:1"
    env["HTTP_PROXY"] = blackhole
    env["HTTPS_PROXY"] = blackhole
    env["ALL_PROXY"] = blackhole
    env["NO_PROXY"] = ""

    session = _start_session(env=env)
    try:
        response = session.send_request(
            "tools/call", {"name": "fetch_document", "arguments": {"doc_id": "doc-3"}}
        )
        session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()

    assert response is not None and "result" in response, (
        f"no response arrived with egress blocked (would suggest a hidden "
        f"network dependency causing fail-open pass-through instead of a "
        f"verdict): {response}"
    )
    verdict = _extract_verdict(response)
    assert verdict["kind"] == "silent_empty"


def test_non_matching_result_passes_through_unrewritten():
    """Sanity check, not one of the four named cases: search_tickets'
    well-formed zero-result payload must NOT be rewritten — the client
    sees the tool's own content, with no [FOURGATE] marker at all."""
    session = _start_session()
    try:
        response = session.send_request(
            "tools/call", {"name": "search_tickets", "arguments": {"query": "q"}}
        )
        session.close()
    finally:
        if session.proc.poll() is None:
            session.proc.kill()

    assert response is not None and "result" in response
    content = response["result"]["content"]
    assert len(content) == 1
    assert FOURGATE_MARKER not in content[0]["text"]
    assert json.loads(content[0]["text"]) == {"results": [], "count": 0, "query": "q"}
