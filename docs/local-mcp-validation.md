# Local MCP workflow validation — experimental C1

An agent can call `validate_workflow` with an operator-registered ID and receive
typed static configuration readiness. This reuses the scanner's contract loader;
it does not start the target server, run a verifier, contact a system of record
or execute a write. It does not verify an action outcome.

This source change is not in the existing PyPI 0.3.0 release. There are no new
runtime dependencies or model API requirements. The existing CLI remains the
execution path for approved regression checks.

## Register a reviewed configuration

Keep a registry and its scan contracts in an operator-controlled local directory.
Example shape (the fingerprint is an unconfigured placeholder):

```json
{
  "registry_version": 1,
  "workflows": {
    "staging-check": {
      "contract": "scan.json",
      "sha256": "REPLACE_WITH_SHA256_OF_REVIEWED_LOCAL_FILE_BYTES",
      "test_account": "approved-disposable-label"
    }
  }
}
```

Use SHA-256 of the actual reviewed file bytes, including local line endings.
Do not copy a Git blob hash or another checkout's fingerprint. A coding agent
can prepare the registry; the operator reviews its IDs, paths, exact predicates
and account labels. The fingerprint pins bytes, **not human approval or write
authority**. A registry cannot grant execution in C1.

Limits: 1–20 workflow IDs (`A–Z`, `a–z`, digits, `_`, `-`, up to 64 characters),
1 MiB registry and registered contract reads, relative contract paths resolving
inside the registry directory. Contract contents are validated with
`scan.load_contract`. Existing CLI loads without registered fingerprints retain
their current behavior.

IDs, paths, file identities and fingerprints are captured at server startup.
After an atomic file replacement or a missing file being created, restart the
server. Changed bytes need a new operator-reviewed fingerprint. Do not silently
refresh a pin to make a failing check green.

## Start and call

Use the selected interpreter and source revision:

```text
python -m fourgate mcp --registry ABS-REGISTRY-JSON
```

The process speaks newline-delimited JSON-RPC on stdio. Explicit legacy
2024-11-05 / 2025-11-25 and modern 2026-07-28 discovery/tools subsets are
implemented. Unknown legacy initialize versions negotiate 2024-11-05; modern
requests require per-request version and client capabilities. This is not a
universal MCP conformance claim. No remote transport or runtime interception
route is introduced.

Only one tool is exposed:

```json
{"name":"validate_workflow","arguments":{"workflow_id":"staging-check"}}
```

Arguments cannot override the registry, contract, command, URL, expectations or
approval. `run_workflow` and `get_run_report` are **not implemented** in C1.

A valid result has this meaning:

```json
{
  "workflow_id": "staging-check",
  "scope": "STATIC_CONFIG_ONLY",
  "readiness": "CONFIG_VALID",
  "action_status": "NOT_RUN",
  "reason_code": "static_checks_satisfied",
  "planned_cases": 1
}
```

CONFIG_VALID confirms the pinned scan schema and presence of declared credential
variables. It does **not** confirm executable availability, custom-verifier
behavior, read visibility, token permissions, identity, freshness, correctness
of human intent or business completion. Undeclared custom prerequisites cannot
be inferred. Credential values are never returned. Invalid/missing/changed
configuration returns typed NOT_READY / NOT_RUN; it is not a business FAIL or
UNKNOWN. Errors use `isError`; both text and structuredContent carry the typed
result. Process success or MCP resultType complete is not an action PASS.

## Client acceptance and remaining phases

Prepare a narrow local stdio client entry around the command above, preserving
other settings. Set the working directory to the intended source checkout or
use an interpreter containing its built package. No existing target-server
entry needs to be wrapped or replaced for this validation tool. Apply client
configuration only within its authorized scope.

Tests include a real installed MCP Python SDK 1.9.4 client and raw modern
request/response checks. Codex Desktop discovery/invocation of this new tool
still needs actual client acceptance; the earlier skill/CLI exercises do not
establish it. A model can omit an optional tool call. This interface is not a
mandatory completion gate and does not fix automatic skill selection.

Next execution/report tools require separately tested operator write grants,
mutation budgets, replay/restart behavior and bounded structural reports. C1
does not claim the full Phase C adapter or the commercial beta is complete.

## Filesystem and evidence boundary

The registry root must be stable and protected during startup. Registered reads
check the opened regular file's device/inode before reading; the same bounded
bytes are hashed and parsed. POSIX nonblocking open rejects the tested FIFO
replacement; symlink loops and unavailable files fail readiness. A filesystem
without usable file identity cannot establish CONFIG_VALID for that entry.

This is not a sandbox against a same-host actor who can rewrite the registry,
code, environment or startup directory. Referenced commands and verifier configs
are not executed or recursively audited. No reports or logs are written by the
tool; Python's normal import/cache behavior is separate. Existing shadow/enforce
semantics, verifier cap, report privacy and PASS/FAIL/UNKNOWN remain unchanged.

Protocol references: [MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools),
[stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio).
