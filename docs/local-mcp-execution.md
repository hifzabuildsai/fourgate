# Local MCP workflow execution — experimental C2

`run_workflow` and `get_run_report` reuse the existing scanner and deterministic
verifier. The default `fourgate mcp --registry PATH` remains
[read-only validation](local-mcp-validation.md). Execution requires a separate
operator policy and explicitly prepared local state. These source features are
not in the existing PyPI 0.3.0 release.

No model key, paid service, hosted database or new pip dependency is needed.
Execution state uses Python's optional standard-library `sqlite3` module; a
Python build without it cannot enable C2. The validation-only path does not
import it. Only local filesystems are supported for grant state.

## Operator preparation

First register and review the exact scan bytes, account label, arguments,
target command, independent verifier and endpoint using the C1 registry.
Then prepare an operator-controlled policy (unconfigured example):

```json
{
  "policy_version": 1,
  "state_file": "execution.sqlite3",
  "grants": {
    "approved-run-001": {
      "workflow_id": "staging-check",
      "contract_sha256": "REPLACE_WITH_THE_REVIEWED_REGISTRY_SHA256",
      "max_tool_calls": 1
    }
  }
}
```

Each run ID is single-use and binds one registered workflow fingerprint.
The policy accepts 1–20 grants and a total declared budget of at most 20
`tools/call` attempts. Each budget is an integer from 1 to 20. All planned
cases must fit the grant before the target starts. A tool call can cause more
than one provider-side effect; this budget does not bound the internals of a
trusted target command or assert a number of persisted records.

Keep the policy and state in a trusted directory. `state_file` is relative to
the policy directory and must resolve inside it, with an existing parent.
Create state once, explicitly, before configuring the serving client command:

```text
python -m fourgate mcp --registry ABS-REGISTRY-JSON --execution-policy ABS-POLICY-JSON --prepare-execution-state
```

Preparation creates a private SQLite file and grant records; no target,
verifier or network request runs. It refuses an existing file. Serving never
creates or repairs missing/corrupt state. Preserve the state for the lifetime
of these grants. Do not delete, restore an older copy, or reinitialize consumed
state to retry an uncertain action. Investigation and a separately reviewed
new grant are required before another execution.

The normal client command omits the preparation flag:

```text
python -m fourgate mcp --registry ABS-REGISTRY-JSON --execution-policy ABS-POLICY-JSON
```

The registry/policy are startup snapshots. Changing a file does not revoke an
already loaded policy; stop the serving process to revoke it. Changed grants
do not match the prepared state's policy fingerprint. An agent can prepare
files for review, but MCP arguments cannot approve a grant or modify its
paths, endpoints, predicates, commands, budget or account.

## Tools and result meaning

With a prepared execution policy, discovery exposes three tools:

| Tool | Exact arguments | Effect |
| --- | --- | --- |
| `validate_workflow` | `workflow_id` | Static readiness; no execution or grant consumption |
| `run_workflow` | `workflow_id`, `run_id` | May start trusted commands, perform writes and run independent verification |
| `get_run_report` | `run_id` | Read an authorized structural report; no target execution |

`run_workflow` is advertised as destructive and not read-only. It is not a
rollback facility. The agent's tool choice remains optional; installing this
adapter does not establish a mandatory protection route.

Result fields distinguish the recorded run from the current request:

- `new_execution: true` means this request invoked the scanner. It is not proof
  that a write reached the provider or persisted. Saved/replayed results set it
  to false, including a saved PASS. They do not perform a fresh read-back.
- `action_status` describes the recorded run's call attempts: NOT_RUN,
  ATTEMPTED or UNCERTAIN. It is not a fresh-write claim on report retrieval.
- `run_state: COMPLETED` means the scanner returned a structural result;
  business checks may still be FAIL or UNKNOWN.
- Each case keeps the existing PASS / FAIL / UNKNOWN. The overall summary is
  UNKNOWN if cases/calls are incomplete or any case is UNKNOWN; otherwise FAIL
  if any case is FAIL; PASS only when every planned call/check is PASS.
- Preflight denial returns NOT_RUN and no outcome verdict. A reserved or
  unavailable historical state returns UNKNOWN / UNCERTAIN, never fresh authority.
- `isError` is true unless the execution/report verdict is PASS. Process exit 0,
  MCP `resultType: complete`, or CONFIG_VALID never establishes an action PASS.

`reserved_tool_calls` reserves the whole planned case count before target
startup. `call_attempts` counts conservatively immediately before sending a
protected request; it is not an independently observed provider mutation count.
It is absent when execution extent is uncertain. Unused reservation is not
refunded. Discovery, trusted command startup and custom-verifier side effects
are not counted as protected write calls and must be reviewed separately.

## Replay, crash and state boundary

SQLite commits a single-use reservation before any target starts. Concurrent
claims share that state. A duplicate or restarted request returns the saved
report or UNKNOWN for a pending reservation; it never resumes the grant.
Timeout/incomplete-result behavior remains the scanner's: no blind write retry
and no later case after an ambiguous call. Failure to save a report leaves
authority consumed. There is no automatic cancellation, compensation or
exactly-once provider guarantee. A client timeout does not undo the action.

The policy, state, registry, code, referenced commands and environment are
trusted operator assets. This is not isolation from an agent or local actor
that can rewrite them, restore a valid old database or erase grant history.
Detectably inconsistent rows and malformed reports fail closed; arbitrary
well-formed tampering is outside this boundary. Test-account labels do not
prove that a provider account is disposable. External targets still need
current, target-specific authorization and independent visibility.

## Evidence and privacy

The MCP payload is bounded to 16 KiB, with at most 20 structural case rows:
run/workflow IDs, contract hash, Fourgate version, state, counters, verdicts,
case indices and allowlisted reason codes. It excludes raw arguments,
responses, URLs, record IDs, paths, credentials and arbitrary verifier evidence.
Custom failure reasons use a generic `contract_failure` in this surface.
Text and structuredContent carry the same typed payload. Saved reports are
validated against this structural shape before retrieval.

Only these structural reports enter the local state database. POSIX preparation
uses 0600; Windows access follows the directory ACL. This is not encryption.
Existing optional CLI JSON/HTML reports keep their documented best-effort
redaction and may contain more detail; they are not automatically generated here.
Declared read-back token/username and custom-verifier secret variables are
removed from the target server's environment. Trusted custom verifiers still
inherit the operator environment.

Local fixture/SDK and installed-wheel checks are distinct from installed Codex
app-server acceptance of C2, Desktop UI reload/selection, customer CI and
production reliability. The C1 founder report does not establish those newer
tools. Fixed local fixture IDs do not prove fresh-write causality or a natural
silent-success incident. Runtime shadow/enforce behavior and its two-second
verification cap are unchanged.

State mechanics reference: [SQLite transactions](https://www.sqlite.org/lang_transaction.html).
