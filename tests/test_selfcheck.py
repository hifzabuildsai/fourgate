"""
plan.md Step 7 — self-check (FR-18).

FR-18: "The self-check MUST exercise the same live intercept-and-rewrite
path used for real tools/call responses and surface the resulting
verdict at the client/model boundary. Printing a standalone sample
object, log entry, or dashboard preview does not satisfy this
requirement."

Both tests here run `python wrap/wrap.py --selfcheck` as a real
subprocess via ScriptedSession and inspect the actual bytes it wrote to
its own stdout — the same "assert on the real bytes" discipline used
throughout this suite (test_rewrite.py in particular). Neither test
imports wrap.selfcheck and calls its functions directly: that would
prove the self-check's own logic is correct, not that the *CLI a real
user runs* actually drives the live path.
"""

import json
import os
import sys
from pathlib import Path

from _support import ScriptedSession

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAP = REPO_ROOT / "wrap" / "wrap.py"

FOURGATE_MARKER = "[FOURGATE]"


def _run_selfcheck(env=None):
    """Run `wrap.py --selfcheck` to completion and return
    (returncode, captured_stdout_text)."""
    session = ScriptedSession([sys.executable, str(WRAP), "--selfcheck"], env=env)
    captured = session.close()
    return session.proc.returncode, captured.decode("utf-8", errors="replace")


def test_selfcheck_exercises_real_path():
    """The verdict the self-check prints must be the one the real
    intercept-and-rewrite path produced — not a constructed sample.

    Proof, in two parts:
      1. The exit code is 0 and a verdict is present at all.
      2. The verdict's `tool` field is "selfcheck/fetch_document" — the
         `<server_label>/<tool_name>` string wrap.py's live gate computes
         at runtime from --server-label and the tracked tools/call
         (D7/FR-16). A hardcoded printed sample would have to
         independently reimplement that exact qualification logic to
         match; the self-check doesn't reimplement it; it's what the
         real wrap subprocess it spawned actually wrote.

    Combined with test_selfcheck_fails_when_wrap_absent below (same CLI
    entry point, wrap bypassed -> no verdict), this pair is what proves
    realness: a hardcoded sample could pass this test alone, but could
    never be made to fail by removing the wrap the way that test does.
    """
    returncode, output = _run_selfcheck()

    assert returncode == 0, f"selfcheck exited {returncode}, output:\n{output}"

    marker_idx = output.find(FOURGATE_MARKER)
    # The CLI prints "OK — ...:\n{json verdict}", not an inline marker —
    # confirm the human-readable success line is there, then parse the
    # verdict JSON that follows it.
    assert "OK" in output, f"selfcheck did not report success:\n{output}"

    brace_idx = output.find("{")
    assert brace_idx != -1, f"no verdict JSON found in output:\n{output}"
    verdict = json.loads(output[brace_idx:])

    assert set(verdict.keys()) == {"kind", "tool", "evidence", "recovery"}
    assert verdict["kind"] == "silent_empty"
    assert verdict["tool"] == "selfcheck/fetch_document"
    assert verdict["recovery"] == "stop"


def test_selfcheck_fails_when_wrap_absent():
    """With the wrap bypassed (FOURGATE_SELFCHECK_BYPASS — a test-only
    hook that makes the self-check drive fixtures/silent_server.py
    directly, with no wrap process in between), the raw server's empty
    `content: []` response carries no [FOURGATE] marker at all. The
    self-check MUST report failure, not success: if it could still print
    something that looks like a verdict here, it would mean the "verdict"
    was constructed independently of whatever the wrapped path actually
    produced — exactly the failure mode FR-18 rules out.
    """
    env = os.environ.copy()
    env["FOURGATE_SELFCHECK_BYPASS"] = "1"

    returncode, output = _run_selfcheck(env=env)

    assert returncode != 0, (
        f"selfcheck reported success with the wrap bypassed — it must not "
        f"be possible for a verdict to appear with no wrap on the path:\n{output}"
    )
    assert FOURGATE_MARKER not in output
    assert "FAILED" in output
