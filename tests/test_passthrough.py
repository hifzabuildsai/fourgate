"""
plan.md Steps 1-2 — raw byte proxy + on-path proof.

Runs the identical scripted JSON-RPC session against fixtures/clean_server.py
directly and through wrap/wrap.py, and asserts the raw stdout bytes match
(FR-1), plus that killing the wrap mid-call breaks a pending call (also
FR-1 — proving Fourgate sits on the path, not beside it).
"""

import subprocess

from _support import ScriptedSession, direct_cmd, run_initialize, wrapped_cmd


def run_scripted_session(cmd):
    """initialize -> notifications/initialized -> tools/list -> tools/call,
    returning (raw captured stdout bytes, parsed tools/list response)."""
    session = ScriptedSession(cmd)

    run_initialize(session)

    tools = session.send_request("tools/list", {})
    assert tools is not None and "result" in tools, f"bad tools/list response: {tools}"

    call = session.send_request(
        "tools/call", {"name": "add_numbers", "arguments": {"a": 2, "b": 3}}
    )
    assert call is not None and "result" in call, f"bad tools/call response: {call}"

    captured = session.close()
    return captured, tools


def test_healthy_session_byte_identical():
    direct_bytes, _ = run_scripted_session(direct_cmd())
    wrapped_bytes, _ = run_scripted_session(wrapped_cmd())

    assert wrapped_bytes == direct_bytes


def test_tool_list_unchanged():
    _, direct_tools = run_scripted_session(direct_cmd())
    _, wrapped_tools = run_scripted_session(wrapped_cmd())

    assert wrapped_tools == direct_tools

    direct_names = [t["name"] for t in direct_tools["result"]["tools"]]
    wrapped_names = [t["name"] for t in wrapped_tools["result"]["tools"]]
    assert wrapped_names == direct_names
    assert wrapped_names == ["add_numbers", "get_greeting", "divide"]


def test_call_does_not_complete_without_wrap():
    """plan.md Step 2 — on-path proof (FR-1).

    Fourgate must sit *on* the path, not beside it as a passive recorder:
    if killing the wrap process itself still let a pending call complete,
    something else would have to be relaying client<->server traffic and
    the wrap would just be watching. Send a tools/call, kill the wrap with
    no read in between (so the call is genuinely in flight, not already
    answered), and assert the client never sees a response.
    """
    session = ScriptedSession(wrapped_cmd())
    try:
        run_initialize(session)

        tools = session.send_request("tools/list", {})
        assert tools is not None and "result" in tools, f"bad tools/list response: {tools}"

        # Put a call in flight, then kill the wrap immediately — no read
        # in between — before it has any chance to relay a response back.
        req_id = session.write_request(
            "tools/call", {"name": "add_numbers", "arguments": {"a": 2, "b": 3}}
        )
        session.proc.kill()
        session.proc.wait(timeout=3)

        response = session._read_json_line(expect_id=req_id, timeout=1.5)
        assert response is None, (
            f"tools/call completed even though the wrap process was killed "
            f"mid-call: {response}"
        )
    finally:
        if session.proc.poll() is None:
            session.proc.kill()
        try:
            session.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        session._reader.join(timeout=1)
