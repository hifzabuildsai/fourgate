# Fourgate engineering handoff

Status: pre-alpha. Scan PRs #14–#21 are merged into `main`, and the `v0.1.0`
tag already exists on `main`. One hosted target was tested by the operator on
a disposable account; verifier-unavailable/unauthorized acceptance on a real
target remains open. Do not call this production-proven.

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

## Known limits and pending work

- The operator reports one real hosted email-sending MCP write on a disposable
  account. A separate read-back credential and authoritative HTTPS GET produced
  `PASS / postcondition_satisfied`; an intentionally mismatched postcondition
  produced `FAIL / field_mismatch` with read-back evidence. A manual search of
  generated reports found neither tested API credential. This is operator
  validation evidence, not an inference from repository fixtures. No natural
  false-success incident was observed. A real-target verifier outage/denied
  read-back has not yet been exercised. The GitHub MCP template has not been
  validated end-to-end against a real server.
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

The tag exists; do not move it. The hosted PASS and deliberately mismatched
FAIL described above are operator-reported acceptance evidence. Still pending:
one successful disposable-account write followed by an unavailable or denied
authoritative read-back, yielding UNKNOWN; a separate end-to-end GitHub MCP
template run if that integration is claimed; and sustained real traffic before
any reliability or production claims. For a local target run, keep credentials
in environment variables and review reports locally before sharing.
