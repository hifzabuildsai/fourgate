# Fourgate engineering handoff

Status: pre-alpha. Scan PRs #14–#21 are merged, and `v0.1.0` already exists.
The operator reports hosted target validation on a disposable account,
including denied read-back yielding UNKNOWN. Do not call this production-proven.

## Purpose and supported path

Fourgate tests whether an explicitly contracted MCP write that appears to
succeed actually changed an authoritative system of record. The scan runs
**writes on disposable test accounts**, not production. The supported MCP
transport is local command-configured stdio. Remote MCP HTTP is not supported.

The `fourgate scan` package entry point calls `fourgate.cli.main`:

1. `fourgate.scan.load_contract` validates a JSON contract and requires the
   exact `--confirm-test-account` label **before spawning the server**.
2. `StdioClient` starts the configured server in the contract directory,
   initializes MCP, and lists its tools. Only explicit names in `write_tools`
   and `cases` are called; discovery never generates test calls. Read-back
   token env vars are removed from the child server environment; the write
   and read credentials must use distinct env names.
3. The exact contracted `tools/call` arguments are sent once per case. A
   timed-out write ends the scan rather than risking a duplicate side effect.
4. A case selects either the existing bounded command verifier in
   `wrap/outcome.py` or `fourgate/readback.py` for generic HTTP/GitHub Issue GET.
   Read-back retries only GET, within explicit attempt, interval, and total
   timeout limits. PASS needs a matching authoritative response. A confirmed
   mismatch or operator-approved missing status is FAIL. Other uncertainty is
   UNKNOWN. UNKNOWN exits nonzero and is never relabeled PASS.
5. `fourgate.report` includes the failed case's request, tool response,
   read-back evidence and repro steps in opt-in JSON and self-contained HTML.
   Reports and stdout are redacted before rendering. No telemetry is sent.

The prior inline Outcome Guard in `wrap/wrap.py` is retained. `scan` is a
separate active test runner; it does not replace the runtime wrapper or widen
legacy `silent_empty` heuristics.

## Run and test

From a fresh checkout:

```bash
python -m pip install ".[dev]"
python -m pytest -q
python demo_outcome.py
python wrap/wrap.py --selfcheck
```

For the fixture, set `FOURGATE_DEMO_STORE` to a disposable path and
`FOURGATE_DEMO_MODE=broken`, then run:

```bash
fourgate scan fixtures/contracts/scan_demo.json \
  --confirm-test-account disposable-demo --report-dir ./fourgate-output
```

Expected exit 1/FAIL. Change mode to `healthy` with a fresh store path for
exit 0/PASS. Exit 2 means invalid config/report I/O; operational uncertainty
is exit 1/UNKNOWN. Linux/Windows CI is configured in `.github/workflows/ci.yml`;
check the latest run for the current commit. An installed CLI smoke test was
performed from `/tmp` after `pip install .` in a fresh virtual environment.

## Contract and new verifiers

`specs/scan-contract-v1.md` documents the format. The demo contract is
`fixtures/contracts/scan_demo.json`. The GitHub Issue example is a **template**
and must be adapted to the exact MCP server's command, tool name, argument
schema, and result selector before running.

For a new HTTP verifier:

1. Create a disposable test account, a scoped MCP write credential, and a
   separate read credential when possible. Store credentials in environment
   variables, never the contract. Verify the read credential can fetch a
   known record before interpreting a missing result as confirmed absence.
2. Add the exact write name to `write_tools` and one or more explicit `cases`.
   Specify only harmless test arguments. Select required values from the
   request/result with `outcome_contract.extract`.
3. Configure `readback.type=http`, a static-host HTTPS `url_template`,
   `expected_fields`, optional `token_env`, and bounded retry settings.
   Specify `missing_statuses` only when an absent record has an unambiguous
   meaning under that read identity. GitHub's specialized GET uses
   `type=github_issue`, `repository`, `issue_number_field`, and `token_env`;
   its 404 is UNKNOWN unless `missing_is_fail` is explicitly enabled.
4. Add a local HTTP fixture test for delayed visibility, real mismatch,
   missing/read-denied distinction, auth failure, malformed response, and
   token redaction. Run it on both OSes. Review generated reports before
   sending them outside the test environment.

The command verifier path uses the existing `wrap/outcome.py` extraction and
typed stdout protocol. A verifier may return an `evidence` object on FAIL;
that object is available to the local scan report after redaction but never
enters the runtime model-visible verdict or shape-only Outcome Guard logs.

## Shadow mode with a real connector

`python -m fourgate.verify_http <readback.json>` is a runtime Outcome Guard
verifier command. It reads the contract's extracted fields from stdin and runs
the same `fourgate/readback.py` validation, URL construction, and bounded GET
as `fourgate scan`. A confirmed result prints `{"status":"pass"}` or
`{"status":"fail","reason_code":"field_mismatch"|"record_missing",...}` with
structural evidence only (method, status, attempts, response paths). Any
uncertainty (401/403, an unconfigured status, timeout, missing credential,
invalid config or input) prints nothing and exits nonzero, which `wrap.py`
records as UNKNOWN (`verifier_error`). This has been tested against a
loopback server only; it has not yet been run against the hosted connector.

1. Start from a scan case that already returned PASS on the disposable
   account. Copy its `readback` object unchanged into `readback.json`, except
   set `timeout_ms` to at most 1500. The runtime caps the whole verifier
   process at 2000 ms, `verify_http` rejects a larger read-back budget, and
   interpreter startup needs the remainder. Keep `attempts × interval_ms`
   inside that budget.
2. Write a runtime contract file (`contract_version: 1`). Under `tools`, key
   the exact tool name and copy `extract` from the scan case's
   `outcome_contract`. Set `verifier` to
   `{"command": ["{python}", "-m", "fourgate.verify_http", "readback.json"],
   "cwd": ".", "timeout_ms": 2000}`, `allowed_failure_reasons` to
   `["field_mismatch"]` plus `"record_missing"` only if `missing_statuses` is
   configured, and `recovery` to `"stop"`. `cwd` is relative to the contract
   file. `{python}` is the interpreter running `wrap.py`; install Fourgate in
   it (`pip install .`). `record_id_field` is a scan-only key: at runtime a
   result without the ID fails extraction and is UNKNOWN.
3. Dry-run the verifier without any write, from the contract directory, against
   a record the read credential can already fetch. Expect exit 0 and PASS, then
   change one expected value for exit 0 and `field_mismatch`:

   ```bash
   echo '{"issue_id": "<known test record>", "title": "<persisted value>"}' | python -m fourgate.verify_http readback.json
   ```

   The verifier's stderr names the reason for any nonzero exit, e.g.
   `unknown (readback_unconfirmed, attempts 3, GET status 401)`. `wrap.py`
   discards verifier stderr, so use this dry run to diagnose UNKNOWN.
4. Point the agent client's MCP server entry at the wrapper, always in shadow
   mode:

   ```bash
   python wrap/wrap.py --outcome-contracts runtime-contract.json --outcome-mode shadow --outcome-log outcomes.jsonl --server-label <label> -- <original server command>
   ```

   The read token env var named by `token_env` must be set where the client
   launches the wrapper. Do not use `--outcome-mode enforce`.
5. Drive one agent-initiated protected call on the disposable account. Shadow
   mode leaves the client-visible bytes unchanged. Each protected call
   appends one shape-only line to `outcomes.jsonl`: `status`, `reason_code`,
   and extracted field names, never values. Expected: `pass /
   postcondition_satisfied` for a healthy write. `unknown / verifier_error`
   means the dry run in step 3 will show the cause; `unknown /
   verifier_timeout` means the 2000 ms budget was exceeded;
   `unknown / verifier_malformed` means a reason code is not allowed.
6. Do not retry an ambiguous write. Review `outcomes.jsonl` before sharing,
   and do not commit runtime contracts that contain record IDs or account
   identifiers.

Credential limit: `wrap.py` passes its full environment to the wrapped
connector, so unlike `fourgate scan` the read token is visible to the
connector process. Use a read credential whose exposure to that process is
acceptable.

## Known limits and pending work

- The operator reports a hosted email-sending MCP test on a disposable account:
  an independently verified healthy write returned `PASS / postcondition_satisfied`,
  and a deliberately mismatched postcondition returned `FAIL / field_mismatch`.
  A successful write followed by a deliberately invalid independent read-back
  credential returned `UNKNOWN / readback_unconfirmed` after three GET attempts.
  These are operator-provided validation results, not a naturally occurring
  false-success incident. The GitHub MCP template has not been run end-to-end.
- The `test_account` label is an explicit human attestation, not an account
  sandbox. A wrongly configured server can still mutate a production account.
- Generic HTTP 404 becomes FAIL only with explicit `missing_statuses`;
  GitHub 404 defaults UNKNOWN because a missing permission may look identical.
  Async writes with visibility beyond the configured budget remain UNKNOWN
  or can be misclassified if the operator sets an inadequate missing rule.
- Redaction is best effort for named keys, recognized token patterns, and
  secret-looking environment values. Arbitrary secret text in a free-form
  field cannot be guaranteed removed. Reports need human review before sharing.
- The current CLI handles one stdio server per contract. There is no remote
  MCP transport, dashboard, gateway, catalog, billing, or telemetry.
- One historical `tests/test_observe.py` assertion missed a log record on a
  first full local run, then passed focused and full reruns. That timing path
  predates scan and was not changed here.

## Validation state after v0.1.0

The operator-reported hosted PASS, deliberate mismatch FAIL, and denied
read-back UNKNOWN above complete the three real-target verdict cases. The
UNKNOWN response status was not present in the generated report before this
change; verify that field on a future authorized target run. The tag must not
be moved. No natural false-success incident or sustained production traffic
has been observed. Review local reports before sharing; credentials belong in
local environment variables, not contracts or chat.
