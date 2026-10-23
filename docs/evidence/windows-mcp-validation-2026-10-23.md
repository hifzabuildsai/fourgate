# Founder-reported Codex app-server validation — 23 October 2026

## Provenance and tested revision

Source: the founder's pasted Windows acceptance summary for PR #50 at exact
source commit `dde4e1a987235e3d702aa5725cf028efcfa6fd3b`. The local Windows
report, traces and audit setup were **not independently accessed or reviewed**
in this implementation environment. Record this as operator-reported client
evidence, separately from [executed Linux and hosted checks](local-mcp-validation-2026-10-23.md).

The founder reported verification of Git blob hashes for 99 source files,
preservation of the existing checkout and artifacts, and clean Git status.
Later documentation-only commits do not mean that the client acceptance ran
at those later revisions. No new PyPI release is established.

## Reported client result

Client: installed Codex **app-server 0.163.0-alpha.11**, using temporary process
configuration overrides. This is direct app-server discovery/invocation, not
Desktop UI selection or reload acceptance.

| Check | Operator-reported result |
| --- | --- |
| Discovery | connected; only `validate_workflow` exposed |
| Invocation count | Exactly one, workflow ID `local-demo` |
| Typed readiness | CONFIG_VALID / STATIC_CONFIG_ONLY / NOT_RUN |
| Reason / tool error flag | `static_checks_satisfied`; `isError: false` |
| Negotiated protocol | Legacy 2024-11-05 |
| Client process exit | 0; not used as an action PASS |
| Target server / verifier / scan / external workflow executions | Zero |
| Audit denials | Zero reported |
| Target trace and store | Absent |
| Leftover fixture process | None found |
| Persistent client configuration | None; `config.toml` hash unchanged |

Zero audit denials alone do not establish the scope or completeness of the
audit setup. The raw traces were not available here to corroborate the summary.
The typed response is configuration readiness; it is not an outcome verdict or
proof that a consequential write occurred.

The first sandboxed client attempt stopped on SQLite permissions. The founder
reported a subsequent approved normal-user attempt succeeding. No cause beyond
that reported permission issue was independently established; this is not a
confirmed Fourgate outcome-verification defect or a recommendation to disable
sandboxing generally.

Operator artifact reference, local and not accessible from this repository:
`fourgate-output/pr50-validation-695c3e164de2429a8a34ffbdd4cdfc30/acceptance-report.md`.

## What this changes and what remains pending

This adds one founder-controlled observation that the installed app-server can
discover and explicitly invoke the read-only tool. The operator-reported
app-server discovery/call criterion is satisfied. It does not establish:

- Desktop UI tool selection, reload or automatic tool/skill activation: **NOT RUN**.
- Native 2026-07-28 negotiation by this installed client: **NOT RUN**; native
  wire fixtures remain separate evidence.
- Workflow execution or report retrieval through MCP: not implemented by C1.
- Target identity, read visibility, token scope, evidence freshness or business
  outcome: not checked by static validation.
- Customer CI, production reliability, repeated customer use, paid value or a
  naturally occurring read-back-proven silent-success case: unvalidated.

An optional tool call is not a mandatory completion gate. Existing scanner and
runtime PASS/FAIL/UNKNOWN, shadow/enforce behavior and the two-second verifier
cap remain unchanged.
