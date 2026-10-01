# Fourgate Outcome Guard MVP

Version: v1. Status: implementation spec.

## Goal

Fourgate verifies an explicitly protected state-changing MCP tool after the connector reports success. The verifier checks an authoritative system of record using a human-approved postcondition contract. A model never makes the runtime PASS/FAIL decision.

The MVP proves one end-to-end failure class:

`create_issue` reports `Created ISSUE-…`, but the issue was not persisted.

Without Fourgate, the client accepts the connector's protocol-valid success. With Fourgate in enforce mode, an independent deterministic verifier reads the issue store and, on confirmed mismatch, Fourgate places an attributed `outcome_failed` verdict before the original connector content.

## Non-goals

- No generic gateway, registry, secrets vault, policy engine, dashboard, or broad security scanner.
- No LLM judge in the blocking path.
- No inferred postconditions or automatic contract approval.
- No baseline generation.
- No automatic retry or compensation in this slice.
- No remote HTTP MCP transport in this slice; the existing stdio interception path is reused.

## Contract

Outcome Guard is enabled only for tools explicitly present in a contract file.

```json
{
  "contract_version": 1,
  "tools": {
    "create_issue": {
      "extract": {
        "issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
        "title": {"source": "arguments", "path": "title"}
      },
      "verifier": {
        "command": ["{python}", "fixtures/outcome_verifier.py"],
        "cwd": "../..",
        "timeout_ms": 1000
      },
      "allowed_failure_reasons": ["record_missing", "field_mismatch"],
      "recovery": "stop"
    }
  }
}
```

Rules:

1. `extract` is an allowlist. Only named fields required by the verifier may leave the intercepted call/result.
2. Each selector names `arguments` or `result` plus a dot path. A missing required selector makes the evaluation `unknown`; it never creates a failure verdict.
3. The verifier receives only the extracted JSON object on stdin and returns exactly one typed JSON object on stdout: `{"status":"pass"}` or `{"status":"fail","reason_code":"..."}`.
4. `reason_code` must be pre-approved in `allowed_failure_reasons`. Any other verifier output is `unknown` and fails open.
5. `timeout_ms` is mandatory, per contract, and capped by Fourgate. Outcome verification is I/O and does not inherit the legacy 100 ms pure-classifier budget. The legacy `silent_empty` classifier keeps its existing 100 ms budget.
6. Contract files are trusted operator configuration. An LLM may draft them, but a human must approve them before runtime use.
7. Optional `verifier.secret_env` lists environment variable names for verifier-only credentials. The wrapper removes them (case-insensitively on Windows) from the wrapped server's environment; the verifier still receives them. Any entry that is not a valid env var name rejects the contract file.

## Runtime behavior

### Correlation

For every `tools/call`, Fourgate stores the JSON-RPC id, tool name, and arguments. When the matching result arrives, Outcome Guard receives the correlated arguments and result. Interleaved/out-of-order calls must never cross-bind.

### Shadow mode

`--outcome-mode shadow` is the default.

- Run the approved verifier.
- Record only structural evaluation metadata.
- Never change the client/model-visible connector response.

### Enforce mode

`--outcome-mode enforce` changes the client-visible response only for a confirmed deterministic postcondition failure.

Healthy PASS: forward the connector result unchanged.

Operational UNKNOWN (verifier timeout, crash, malformed output, missing selector, internal error): forward the connector result unchanged.

Confirmed FAIL: prepend exactly one Fourgate verdict before the connector's original content and preserve all useful original result fields.

Example:

```json
{
  "kind": "outcome_failed",
  "tool": "demo/create_issue",
  "evidence": {
    "reason_code": "record_missing",
    "checked_fields": ["issue_id", "title"]
  },
  "recovery": "stop"
}
```

The outcome verdict has exactly four top-level keys: `kind`, `tool`, `evidence`, `recovery`. Evidence is structural only: no argument values, issue ids, customer data, credentials, raw verifier output, or raw connector payload.

## Functional requirements

**OG-1 — Inline correlation.** Tool name, arguments, and result are correlated by JSON-RPC id on the existing live stdio path.

**OG-2 — Explicit protection.** A tool without an approved postcondition contract receives no outcome verification and no outcome verdict.

**OG-3 — Minimum extraction.** The verifier receives only fields explicitly named in the contract.

**OG-4 — Authoritative deterministic verifier.** Runtime PASS/FAIL comes only from the configured verifier command and its typed result. No model inference is permitted.

**OG-5 — Healthy pass-through.** A verified PASS reaches the client unchanged.

**OG-6 — Confirmed failure verdict.** A verified FAIL in enforce mode prepends one attributed `outcome_failed` verdict with `recovery` from the approved contract.

**OG-7 — Preserve connector evidence.** On a failure verdict, original `content`, `structuredContent`, and other useful connector result fields remain behind the verdict.

**OG-8 — Fail open on uncertainty.** Verifier crash, timeout, non-zero exit, malformed output, unapproved reason code, selector failure, or Fourgate internal error never creates `outcome_failed` and never blocks the original result.

**OG-9 — Shadow first.** Shadow mode runs verification and records the structural result without changing model-visible bytes.

**OG-10 — Structural evidence only.** Verdicts and outcome logs contain reason codes and field names, never field values or raw payload data.

**OG-11 — Explicit latency budget.** Every verifier contract declares `timeout_ms`; Fourgate enforces it and has a bounded outer guard. The MVP cap is 2000 ms. This is intentionally separate from the legacy 100 ms classifier budget because authoritative read-back is I/O.

**OG-12 — Legacy compatibility.** Existing `silent_empty` behavior, self-check, and byte-faithful pass-through remain available. Outcome Guard does not expand silent-empty heuristics.

## Acceptance tests

1. Broken `create_issue` returns protocol-valid `Created ISSUE-001` without persisting. Direct client sees and accepts that success.
2. Same broken call through Fourgate enforce yields `outcome_failed`, `record_missing`, `stop`, and fully qualified `demo/create_issue`.
3. Connector's original `Created ISSUE-001` content remains immediately after the Fourgate verdict; `structuredContent.issue_id` also remains.
4. Healthy mode persists the issue and the wrapped response equals the direct response with no Fourgate marker.
5. Shadow mode on the broken call records `fail/record_missing` but client-visible response equals the direct response.
6. Shadow log contains field names but not the issue id, title, arguments, or raw payload values.
7. Verifier crash, timeout, and malformed output each fail open with the original response unchanged.
8. An internal Outcome Guard hang is bounded by the contract's outer safety guard and fails open.
9. Interleaved calls bind the correct arguments/result to the correct request id.
10. A runnable demo shows: direct false success → Fourgate catches it → healthy control passes unchanged.
