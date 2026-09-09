"""
plan.md Step 4 — fail-open gate (FR-2, D5).

The classify gate inserted in this step is a no-op — it never produces a
verdict — but the gate's *mechanism* (a bounded wait on a worker thread,
fail-open on timeout or exception) is real, and is what a real classifier
will run inside from Step 5 on. FOURGATE_FAULT is a test-only environment
hook wrap/wrap.py reads to make classify raise or hang deterministically,
without needing a real classifier to exist yet.

Latency is asserted as a *delta* — wrapped tools/call time minus the same
call's unwrapped time — rather than an absolute bound. The wrapped path
inherently costs a little more than the direct path regardless of any
fault (two extra pipe hops: client<->wrap and wrap<->child, versus
client<->child directly); subtracting the unwrapped baseline isolates the
latency actually attributable to the gate, which is what FR-2's 100 ms
budget is a claim about.
"""

import os
import time

from _support import ScriptedSession, direct_cmd, run_initialize, wrapped_cmd

BUDGET_SECS = 0.1  # FR-2 / D5
# The gate's own timeout is exactly BUDGET_SECS; this is slack for the
# scheduling/timer-resolution overshoot inherent in waiting on any
# real-world timeout, not slack in the budget itself.
DELTA_ASSERTION_SECS = BUDGET_SECS + 0.1


def _time_tools_call(session):
    start = time.monotonic()
    call = session.send_request(
        "tools/call", {"name": "add_numbers", "arguments": {"a": 2, "b": 3}}
    )
    elapsed = time.monotonic() - start
    assert call is not None and "result" in call, f"bad tools/call response: {call}"
    return elapsed


def _run_direct_session():
    session = ScriptedSession(direct_cmd())
    run_initialize(session)
    tools = session.send_request("tools/list", {})
    assert tools is not None and "result" in tools, f"bad tools/list response: {tools}"
    elapsed = _time_tools_call(session)
    captured = session.close()
    return captured, elapsed


def _run_wrapped_session_with_fault(fault):
    env = os.environ.copy()
    env["FOURGATE_FAULT"] = fault
    session = ScriptedSession(wrapped_cmd(), env=env)
    run_initialize(session)
    tools = session.send_request("tools/list", {})
    assert tools is not None and "result" in tools, f"bad tools/list response: {tools}"
    elapsed = _time_tools_call(session)
    captured = session.close()
    return captured, elapsed


def test_raise_passes_through():
    """An internal error during classification must not touch the result
    the client receives, and must not add meaningful latency — the gate
    fails open essentially immediately on an exception (FR-2)."""
    direct_bytes, direct_elapsed = _run_direct_session()
    wrapped_bytes, wrapped_elapsed = _run_wrapped_session_with_fault("raise")

    assert wrapped_bytes == direct_bytes, (
        "classify raising must not alter the forwarded result"
    )

    delta = wrapped_elapsed - direct_elapsed
    assert delta < DELTA_ASSERTION_SECS, (
        f"tools/call added {delta * 1000:.1f}ms over the unwrapped baseline "
        f"with FOURGATE_FAULT=raise — an internal classify error must not "
        f"add meaningful latency"
    )


def test_hang_passes_through_within_budget():
    """A classifier that never returns on its own must still deliver the
    original result, failing open at the 100 ms budget rather than waiting
    for the (5 s) hang (FR-2)."""
    direct_bytes, direct_elapsed = _run_direct_session()
    wrapped_bytes, wrapped_elapsed = _run_wrapped_session_with_fault("hang")

    assert wrapped_bytes == direct_bytes, (
        "a hung classify must still deliver the original result"
    )

    delta = wrapped_elapsed - direct_elapsed
    assert delta < DELTA_ASSERTION_SECS, (
        f"tools/call added {delta * 1000:.1f}ms over the unwrapped baseline "
        f"with FOURGATE_FAULT=hang — the gate must fail open at the "
        f"{BUDGET_SECS * 1000:.0f}ms budget, not wait for the 5s hang"
    )
