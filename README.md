# Fourgate

Fourgate catches MCP tools that say 'success' when nothing actually happened.

**Status: early, pre-alpha.**

## Results so far (2026-10-01)

Tested against 4 official vendor MCP servers from 4 companies (run locally over
stdio against the vendors' live APIs), using disposable test accounts or
deliberately invalid credentials so no real data could be changed.

| Check | Result |
|---|---|
| Servers where a write tool returned an API failure as a successful tool result (no `isError`) | **3 of 4**, each reproduced at least twice, reported upstream |
| Healthy write verified by independent read-back | 1 server: PASS, with FAIL and UNKNOWN controls behaving as specified |
| Runtime shadow calls from a real agent client | 2 of 2 PASS |
| Read-back-proven silent success (reported done, record missing or wrong) | 0 observed so far |

An agent reading a result without `isError` has no protocol-level signal that
the call failed. Fourgate reports these as `UNKNOWN / success_without_record_id`
rather than PASS. Vendors are not named here; details are under
[Field evidence](#field-evidence).

Operators running scans against real MCP servers: see [`OPERATOR.md`](OPERATOR.md) for the step-by-step Windows guide and contract templates.

## Scan a disposable MCP test account (under five minutes)

Python 3.10+. Install the v0.2.0 release:

```bash
python -m pip install "git+https://github.com/hifzabuildsai/fourgate@v0.2.0"
```

Or, from a clean checkout of this repository (the bundled fixture below needs
the checkout):

```bash
python -m pip install .
```

For the bundled **local fixture only**, set a disposable store location and
scan its deliberately broken issue creation. Bash:

```bash
export FOURGATE_DEMO_STORE="$(mktemp -d)/issues.json"
export FOURGATE_DEMO_MODE=broken
fourgate scan fixtures/contracts/scan_demo.json \
  --confirm-test-account disposable-demo --report-dir ./fourgate-output
```

PowerShell:

```powershell
$env:FOURGATE_DEMO_STORE = "$env:TEMP\fourgate-demo-issues.json"
$env:FOURGATE_DEMO_MODE = "broken"
fourgate scan fixtures/contracts/scan_demo.json --confirm-test-account disposable-demo --report-dir ./fourgate-output
```

The expected result is `FAIL / record_missing` (exit 1), with local
`fourgate-report.json` and self-contained `fourgate-report.html` in the chosen
directory. Set `FOURGATE_DEMO_MODE=healthy` and rerun with a fresh store path to
see PASS (exit 0). UNKNOWN is never counted as PASS (exit 1). Invalid scan
configuration exits 2. Reports include the exact contracted request, response,
read-back evidence and reproduction steps for a confirmed failure, after
best-effort secret redaction. Review locally before sharing.

Only explicitly named write tools and arguments in the contract are called.
The scanner supports stdio MCP servers and local command, generic HTTPS, or
GitHub Issue read-back. HTTP/GitHub verification makes GET requests to the
configured endpoint; no scan telemetry is sent to Fourgate. See
[`specs/scan-contract-v1.md`](specs/scan-contract-v1.md) and
[`SECURITY.md`](SECURITY.md). The GitHub contract is a template that still
requires a disposable repository, tokens, and real end-to-end acceptance.

## Run in CI

[`examples/ci/fourgate-scan.yml`](examples/ci/fourgate-scan.yml) is a
copy-paste GitHub Actions workflow for your own repository. It installs
Fourgate from a release tag, runs `fourgate scan` on manual dispatch, uploads
the JSON/HTML reports as a workflow artifact, and fails the job on any FAIL or
UNKNOWN (non-zero exit). Edit the marked values: contract path, the
`--confirm-test-account` label (must equal `server.test_account`), and the
environment variable names. The MCP server's write credential and the
read-back token come from two separate secrets, `FOURGATE_MCP_WRITE_TOKEN` and
`FOURGATE_READBACK_TOKEN`, mapped to separate environment variables.

Every run performs real contracted writes: target a disposable test account
only. Workflow artifacts are readable by anyone with read access to the
repository, so use a private repository and review reports before sharing.
Fourgate's own CI runs the template's steps against the bundled demo fixture
(broken exits 1, healthy exits 0); the template has not yet been run against a
hosted connector.

## Outcome Guard MVP

The current pitch-ready slice protects explicitly contracted state-changing MCP tools. After a connector reports success, Fourgate extracts only the minimum contract-approved fields and runs a deterministic authoritative verifier. No LLM makes the runtime PASS/FAIL decision.

Three outcomes are possible:

- **PASS** — connector response is unchanged.
- **CONFIRMED FAIL** — in enforce mode, Fourgate prepends an attributed `outcome_failed` verdict before the connector's original content.
- **UNKNOWN** — verifier crash, timeout, malformed output, missing selector, or Fourgate internal fault fails open; connector response is unchanged.

Shadow mode is the default. It records structural verdict metadata without changing what the model receives.

### Run the proof

```bash
python demo_outcome.py
```

The demo runs the same `create_issue` workflow three ways:

1. **Broken connector without Fourgate:** returns `Created ISSUE-001` but persists nothing.
2. **Broken connector with Fourgate enforce:** an approved read-back check confirms the issue is absent and the model receives `[FOURGATE] {"kind":"outcome_failed", ...}` first; the original `Created ISSUE-001` remains behind it.
3. **Healthy connector with Fourgate enforce:** the issue exists and the connector response passes through unchanged.

### Wrap a local stdio server

```bash
python wrap/wrap.py \
  --outcome-contracts path/to/contracts.json \
  --outcome-mode shadow \
  --server-label my-server \
  --outcome-log outcomes.jsonl \
  -- python your_server.py
```

Switch to `--outcome-mode enforce` only for human-approved contracts after shadow traffic is clean.

For a hosted connector, the verifier can be the scan's own HTTP read-back:
`python -m fourgate.verify_http readback.json` takes the extracted fields on
stdin and runs the same bounded GET as `fourgate scan`. Any uncertainty exits
nonzero and is recorded as UNKNOWN. `verifier.secret_env` names the read
credential's environment variables; `wrap.py` removes them from the wrapped
server's environment while the verifier still receives them:

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
        "command": ["{python}", "-m", "fourgate.verify_http", "readback.json"],
        "cwd": ".",
        "timeout_ms": 2000,
        "secret_env": ["READBACK_TOKEN"]
      },
      "allowed_failure_reasons": ["field_mismatch"],
      "recovery": "stop"
    }
  }
}
```

`readback.json` is a scan contract `readback` object with `timeout_ms` of at
most 1500. The read token is sent as `Authorization: Bearer` unless
`readback.auth` selects a custom header (`{"scheme": "header", "header":
"X-Api-Key"}`) or Basic auth; `readback.headers` adds fixed, non-secret headers
such as an API version. List every read credential variable (`token_env`, and
`auth.username_env` if used) in `verifier.secret_env`. Details:
[`OPERATOR.md` → 3c](OPERATOR.md#3c-find-the-read-back-get-endpoint). Step-by-step setup and the verifier dry run are in
[`HANDOFF.md` → Shadow mode with a real connector](HANDOFF.md#shadow-mode-with-a-real-connector).

See [`specs/outcome-guard-mvp.md`](specs/outcome-guard-mvp.md) for the contract and failure semantics.

## Existing components

### Preflight CLI

`checker/preflight.py` starts a Python MCP server over stdio, speaks raw JSON-RPC, detects stdout pollution, and exercises a limited set of schema/argument edge cases. Keep it free/low-cost infrastructure; it is not a replacement for MCP Inspector or conformance tooling.

### Runtime wrap

`wrap/wrap.py` is the on-path stdio proxy. It already correlates `tools/call` requests/results by JSON-RPC id, supports byte-identical pass-through, a bounded fail-open legacy classifier path, an attributed in-band verdict, and shape-only observation.

The existing `silent_empty` behavior remains deliberately narrow. Fourgate does **not** flag `{"issues":[]}`, `No matches found`, or explicit empty structured data merely because it is empty. Empty data is wrong only when an approved contract/postcondition proves it.

## Field evidence

The original field run observed 24 real `tools/call` results and zero `silent_empty` events. Four observed failures happened before `tools/call` at spawn/connect/discovery/configuration. That weakens the original empty-payload wedge; it does not validate Outcome Guard on its own.

### Hosted scan validation (2026-09-30)

Operator-reported validation on a disposable account: a real hosted MCP write
returned an ID, and an independent HTTPS read-back with a separate credential
produced `PASS / postcondition_satisfied`. An intentionally mismatched
postcondition produced `FAIL / field_mismatch` with authoritative read-back
evidence. A manual search of the generated reports found neither tested API
credential. No naturally occurring false-success incident was observed. This
single integration does not establish production reliability.

### Runtime shadow run (2026-10-01)

Operator-reported: a real agent client made two protected send calls through
`wrap.py` in shadow mode against the same hosted email-sending MCP server on a
disposable account, verified by `fourgate.verify_http` with `secret_env`
withholding the read-back key from the connector. `outcomes.jsonl` recorded
`pass / postcondition_satisfied` for both. Two calls is a smoke test, not
production traffic.

### Errors returned as success

Operator scans of three official company MCP servers (hosting, payments, work
management), using deliberately invalid credentials so nothing could be
created, found write tools returning API failures as successful tool results
with no `isError`. Fourgate reports these as `UNKNOWN /
success_without_record_id`. Each was reproduced at least twice and reported
upstream. These are error-reporting bugs: no read-back-proven silent success
(a write reported as done whose record is missing or wrong) has been observed
yet.

## Current limitations

- Outcome contracts are hand-authored and human-approved; generation is not implemented.
- Runtime verifiers are local commands. The bundled one, `fourgate.verify_http`, is a generic HTTP GET read-back with optional Bearer token; there are no database adapters.
- Outcome verification adds read-back latency on the protected call. The runtime caps each verifier at 2000 ms and fails open (UNKNOWN) on uncertainty. `verify_http` measured 1.2–1.6 s per call on a Windows laptop, and a first cold call exceeded its budget, so headroom is small on slow networks.
- Only command-configured local stdio MCP servers are covered (scanner and runtime); no remote MCP transport.
- No dashboard, alerting product, gateway, retry engine, or automatic compensation.
- Preflight's test handshake uses an older MCP protocol version, and its tests need the `mcp==1.9.4` dev dependency.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python wrap/wrap.py --selfcheck
```

The `dev` extra installs `pytest` and the `mcp==1.9.4` package that the
preflight tests need.

## License

MIT — see [LICENSE](LICENSE).
