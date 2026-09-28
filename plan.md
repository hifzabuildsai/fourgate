# plan.md — Outcome Guard MVP

Current implementation plan for the pitch-ready Fourgate wedge. This supersedes the earlier `silent_empty`-only build plan; the old classifier remains supported but is frozen unless field evidence justifies expansion.

## Slice

Build one deterministic protected mutation end to end:

`create_issue(title)` → connector claims `Created ISSUE-…` → approved postcondition reads the authoritative issue store → PASS / FAIL / UNKNOWN.

Reuse the existing stdio wrap, JSON-RPC id correlation, fail-open behavior, and in-band Fourgate attribution. Add only what Outcome Guard needs.

## Changes

1. Add `specs/outcome-guard-mvp.md` as governing behavior.
2. Add `wrap/outcome.py` for contract loading, allowlisted extraction, verifier execution, typed verifier output validation, structural logging, and `outcome_failed` construction.
3. Extend `wrap/wrap.py` with a separate request/result binding for Outcome Guard and flags:
   - `--outcome-contracts PATH`
   - `--outcome-mode shadow|enforce` (default `shadow`)
   - `--outcome-log PATH`
4. Extend `wrap/verdict.py` with an additive prepend path so Outcome Guard preserves connector content and structured data.
5. Add a deterministic `create_issue` demo server with healthy/broken persistence modes, a read-back verifier, and one hand-approved contract.
6. Add focused tests for confirmed failure, healthy control, shadow mode, redaction, fail-open verifier faults, bounded internal faults, and correlation.
7. Add a runnable end-to-end demo.

## Deliberately frozen

- No additional `silent_empty` heuristics.
- No fake-success guessing from tool names or prose.
- No automatic contract generation/approval.
- No dashboard, gateway, registry, identity, or policy platform.
- No retry/compensation engine.
- No remote transport work.

## Done when

The demo visibly proves all three cases in one run:

1. Broken connector without Fourgate: client receives `Created ISSUE-001`; authoritative store is empty.
2. Same broken connector with Fourgate enforce: model receives `outcome_failed` first and original success content second.
3. Healthy connector with Fourgate enforce: persisted record exists and response is unchanged.

Focused tests and legacy self-check must pass. The complete historical suite is run only where its declared `mcp==1.9.4` dependency is available; missing dependencies are reported, never treated as a pass.
