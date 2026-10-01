# Fourgate

Fourgate catches MCP tools that say 'success' when nothing actually happened.

**Status: early, pre-alpha.**

Operators running scans against real MCP servers: see [`OPERATOR.md`](OPERATOR.md) for the step-by-step Windows guide and contract templates.

## Scan a disposable MCP test account (under five minutes)

From a clean checkout with Python 3.10+:

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

See [`specs/outcome-guard-mvp.md`](specs/outcome-guard-mvp.md) for the contract and failure semantics.

## Existing components

### Preflight CLI

`checker/preflight.py` starts a Python MCP server over stdio, speaks raw JSON-RPC, detects stdout pollution, and exercises a limited set of schema/argument edge cases. Keep it free/low-cost infrastructure; it is not a replacement for MCP Inspector or conformance tooling.

### Runtime wrap

`wrap/wrap.py` is the on-path stdio proxy. It already correlates `tools/call` requests/results by JSON-RPC id, supports byte-identical pass-through, a bounded fail-open legacy classifier path, an attributed in-band verdict, and shape-only observation.

The existing `silent_empty` behavior remains deliberately narrow. Fourgate does **not** flag `{"issues":[]}`, `No matches found`, or explicit empty structured data merely because it is empty. Empty data is wrong only when an approved contract/postcondition proves it.

## Field evidence

The original field run observed 24 real `tools/call` results and zero `silent_empty` events. Four observed failures happened before `tools/call` at spawn/connect/discovery/configuration. That weakens the original empty-payload wedge; it does not validate Outcome Guard. Outcome Guard now needs real shadow-mode traffic and reproducible false-success incidents.

### Hosted scan validation (2026-09-30)

Operator-reported validation on a disposable account: a real hosted MCP write
returned an ID, and an independent HTTPS read-back with a separate credential
produced `PASS / postcondition_satisfied`. An intentionally mismatched
postcondition produced `FAIL / field_mismatch` with authoritative read-back
evidence. A manual search of the generated reports found neither tested API
credential. No naturally occurring false-success incident was observed. This
single integration does not establish production reliability.

## Current limitations

- Outcome contracts are hand-authored and human-approved; generation is not implemented.
- The MVP verifier adapter is a local command protocol. Production database/API adapters are not implemented yet.
- Outcome verification adds the verifier's declared read-back latency. It has an explicit per-contract timeout (MVP cap: 2000 ms) and fails open on uncertainty.
- Only command-configured local stdio MCP servers are covered by this implementation.
- No dashboard, alerting product, gateway, retry engine, or automatic compensation.
- Preflight still pins `mcp==1.9.4` and uses the older protocol version in its test handshake.

## Tests

```bash
pytest -q tests/test_outcome_guard.py
python wrap/wrap.py --selfcheck
```

The historical full suite additionally requires the repository's declared `mcp==1.9.4` dependency.

## License

MIT — see [LICENSE](LICENSE).
