# External disposable-account scan (second-person guide)

**Audience:** a second person who has never run Fourgate, with access to one
authorized disposable MCP test account. **Version:** limited beta `0.4.0b1`.

Supported path: **local command-configured stdio** only. No remote MCP
transport, no Fourgate hosted endpoint, no telemetry. Customer CI and Desktop
UI execution remain unvalidated.

## What “done” looks like

| Step | Command | Success signal |
| --- | --- | --- |
| Install | `python -m pip install --pre "fourgate==0.4.0b1"` | `fourgate 0.4.0b1` |
| Scaffold | `fourgate init …` | Writes `readback.json`, `runtime.json`, `scan.json` |
| Edit | hand-edit the three files | No `REPLACE_*` / `REPLACE WITH …` markers left |
| Preflight | `fourgate doctor …` | `Verdict: READY FOR SHADOW` (exit 0) |
| Disposable scan | `fourgate scan … --report-dir …` | Local redacted `fourgate-report.json` + `.html` |
| Runtime log (optional) | `fourgate guard --mode shadow …` then `fourgate summary …` | `outcomes.jsonl` + HTML summary |

`fourgate scan` writes **scan reports**. `fourgate summary` reads **runtime**
`outcomes.jsonl` from `guard`, not scan reports. Both steps are part of a clean
external path; do not skip doctor before the first real write.

### Verdicts (PASS / FAIL / UNKNOWN)

| Verdict | Exit (scan) | Meaning |
| --- | --- | --- |
| **PASS** | 0 if every case PASS | Independent read-back matched contracted fields |
| **FAIL** | 1 | Read-back confirmed missing/mismatched record |
| **UNKNOWN** | 1 | Cannot confirm (timeout, auth, network, missing selector, incomplete result, …). Fails open. **Never PASS.** |

Runtime verifier budget remains **2000 ms**. Scan HTTP/GitHub read-back uses the
per-case `timeout_ms` in the contract (templates use ≤1500 ms so runtime headroom
stays available).

---

## 0. Install (bash and PowerShell)

```bash
python -m pip install --pre "fourgate==0.4.0b1"
python -m fourgate --version
```

```powershell
py -3 -m pip install --pre "fourgate==0.4.0b1"
py -3 -m fourgate --version
```

Expected stdout: `fourgate 0.4.0b1`.

For the bundled demo fixture or this repository’s GitHub Issue pack, also
install from a source checkout: `python -m pip install .`

---

## 1. Primary path — `init` → edit → `doctor` → `scan` → (`guard` → `summary`)

Use this for any stdio MCP write tool whose record can be confirmed with an
**HTTPS GET** (Bearer / custom header / Basic). Credentials are env **names**
only; never put values in contracts or chat.

### 1a. Scaffold

Pick a disposable work directory **outside** git if the contract will contain
account-specific IDs.

**Bash**

```bash
mkdir -p "$HOME/fourgate-scan-work/demo" && cd "$HOME/fourgate-scan-work/demo"
export READBACK_TOKEN  # set a real read token in your shell; do not echo it
fourgate init \
  --tool create_issue \
  --test-account disposable-demo \
  --id-path result.structuredContent.issue_id \
  --readback-url 'https://api.example.com/issues/{record_id}' \
  --expect title=title \
  --arg title=FOURGATE-SCAN-TEST \
  --token-env READBACK_TOKEN \
  --missing-status 404 \
  --dir ./fourgate-config \
  -- python -m fourgate.demo.server
```

**PowerShell**

```powershell
New-Item -ItemType Directory -Force $env:USERPROFILE\fourgate-scan-work\demo | Out-Null
Set-Location $env:USERPROFILE\fourgate-scan-work\demo
# Set $env:READBACK_TOKEN securely (Read-Host -AsSecureString); never print it.
fourgate init `
  --tool create_issue `
  --test-account disposable-demo `
  --id-path result.structuredContent.issue_id `
  --readback-url 'https://api.example.com/issues/{record_id}' `
  --expect title=title `
  --arg title=FOURGATE-SCAN-TEST `
  --token-env READBACK_TOKEN `
  --missing-status 404 `
  --dir .\fourgate-config `
  -- python -m fourgate.demo.server
```

`init` prints the next `doctor` / `scan` / `guard` / `summary` lines with your
paths filled in. It never starts the server or contacts the endpoint.

For a **real** vendor server: replace the command after `--` with the reviewed
local stdio command, replace the read-back URL with the provider’s GET template
containing `{record_id}`, and set `--id-path` / `--expect` / `--arg` from
discovery. Keep write and read credentials in **different** env var names.

### 1b. Edit until ready

Open `fourgate-config/scan.json`, `runtime.json`, and `readback.json`. Confirm:

- `server.test_account` is the disposable label you will pass to `--confirm-test-account`
- `server.command` is the real local stdio command (no `REPLACE_*`)
- arguments are harmless disposable values
- `readback.token_env` names the read credential already set in this shell
- `verifier.secret_env` lists every read credential name

`fourgate scan` **refuses to run** while `REPLACE_*`, `REPLACE WITH …`, or
`your-mcp-server` markers remain (exit 2).

### 1c. Doctor (no write)

**Bash**

```bash
fourgate doctor \
  --contracts ./fourgate-config/runtime.json \
  --server demo \
  --log ./outcomes.jsonl \
  -- python -m fourgate.demo.server
```

**PowerShell**

```powershell
fourgate doctor `
  --contracts .\fourgate-config\runtime.json `
  --server demo `
  --log .\outcomes.jsonl `
  -- python -m fourgate.demo.server
```

Expected: lines tagged `[ OK ]` / `[WARN]`, ending with
`Verdict: READY FOR SHADOW` and exit **0**. Doctor never sends `tools/call`.

For protocol `2026-07-28` servers, add `--protocol-version 2026-07-28` before `--`.

### 1d. Scan (real contracted write)

**Bash**

```bash
fourgate scan ./fourgate-config/scan.json \
  --confirm-test-account disposable-demo \
  --report-dir ./fourgate-report
```

**PowerShell**

```powershell
fourgate scan .\fourgate-config\scan.json `
  --confirm-test-account disposable-demo `
  --report-dir .\fourgate-report
```

| Result | Typical stderr / files | Process exit |
| --- | --- | --- |
| All PASS | `reports written to …/fourgate-report.json and …/fourgate-report.html` | 0 |
| Any FAIL or UNKNOWN | same reports; JSON `cases[].status` is FAIL or UNKNOWN | 1 |
| Bad config / placeholders left | `fourgate: scan configuration error: …` | 2 |

Open `fourgate-report.html` locally. Reports are redacted best-effort (secret-looking
keys, recognized token patterns, secret env values). **Review before sharing.**

**Local demo fixture (no provider keys):** from a Fourgate checkout,

```bash
export FOURGATE_DEMO_STORE="$(mktemp -d)/issues.json"
export FOURGATE_DEMO_MODE=broken
fourgate scan fixtures/contracts/scan_demo.json \
  --confirm-test-account disposable-demo --report-dir ./fourgate-output/broken
# expect FAIL / record_missing, exit 1
```

```bash
export FOURGATE_DEMO_STORE="$(mktemp -d)/issues.json"
export FOURGATE_DEMO_MODE=healthy
fourgate scan fixtures/contracts/scan_demo.json \
  --confirm-test-account disposable-demo --report-dir ./fourgate-output/healthy
# expect PASS / postcondition_satisfied, exit 0
```

### 1e. Shadow guard + summary (runtime path / measurement)

After scan contracts look correct:

```bash
fourgate guard \
  --contracts ./fourgate-config/runtime.json \
  --mode shadow \
  --server demo \
  --log ./outcomes.jsonl \
  -- python -m fourgate.demo.server
# Point your MCP client at this guard command instead of the bare server.
# Reproduce a few protected writes, then stop the client.
fourgate summary ./outcomes.jsonl --out ./fourgate-summary.html --json
```

```powershell
fourgate guard `
  --contracts .\fourgate-config\runtime.json `
  --mode shadow `
  --server demo `
  --log .\outcomes.jsonl `
  -- python -m fourgate.demo.server
fourgate summary .\outcomes.jsonl --out .\fourgate-summary.html --json
```

Summary HTML has no JavaScript and makes no network requests. It contains
structure only (counts, reason codes, `gate_ms` latency) — not arguments or
credentials. Use it for the [measurement package](measurement-package.md).

---

## 2. Strongest write reference — GitHub Issue update pack

The reviewed reference workflow is **update one existing disposable GitHub
Issue** via the official local stdio GitHub MCP Server (`issue_write`), with
independent `github_issue` GET read-back.

Full pack: [`examples/github-issue/`](../examples/github-issue/README.md).
Live adaptation steps: [`examples/github-issue/EXTERNAL.md`](../examples/github-issue/EXTERNAL.md).

### Prove the tooling without GitHub credentials

```bash
python -B examples/github-issue/run_local.py --out ./fourgate-output/github-issue-local-001
# exit 0 means expected PASS + induced FAIL/UNKNOWN controls were observed
```

```powershell
py -3 -B examples\github-issue\run_local.py --out .\fourgate-output\github-issue-local-001
```

### Live disposable path (env names only)

| Role | Env var **name** | Notes |
| --- | --- | --- |
| MCP write | `GITHUB_PERSONAL_ACCESS_TOKEN` (or the name your installed server documents) | Write scope on the disposable repo only |
| Fourgate read-back | `FOURGATE_GITHUB_READ_TOKEN` | Separate token; scanner withholds it from the server |

Do not paste values into chat, contracts, or commits.

1. Complete [`examples/github-issue/review-card.example.md`](../examples/github-issue/review-card.example.md).
2. Copy `scan.example.json` → a private work folder as `scan.json`; replace every
   `REPLACE_*` / `REPLACE WITH …` marker; set `server.command` to the reviewed
   local stdio binary.
3. Copy `runtime.example.json` + `readback.example.json` beside it and keep the
   same owner/repo/issue fields and `FOURGATE_GITHUB_READ_TOKEN`.
4. `fourgate doctor --contracts runtime.json --protocol-version 2026-07-28 --log outcomes.jsonl -- <server command>`
5. `fourgate scan scan.json --confirm-test-account disposable-github-issue --report-dir ./fourgate-report`
6. Review redacted HTML. Expected healthy: `PASS / postcondition_satisfied`.
   Induced wrong title expectation: `FAIL / field_mismatch`. Missing read token:
   `UNKNOWN / credential_missing` (no write is sent). GitHub 404 with
   `missing_is_fail: false`: `UNKNOWN / readback_unconfirmed`.

Historical founder live evidence (not a rerun authorization):
[D3](evidence/github-issue-d3-live-2026-10-31.md),
[D4](evidence/github-issue-d4-hosted-2026-10-31.md).

---

## Hard rules

- Writes only to **your** disposable account/repo. Confirm the label with
  `--confirm-test-account` (attestation, not a sandbox).
- Never retry a timed-out write until you have checked the account by hand.
- UNKNOWN is never PASS and never a confirmed finding by itself.
- Prefer two matching runs before filing an upstream bug ([OPERATOR.md](../OPERATOR.md)).
- Keep the 2000 ms runtime verifier budget; do not raise it to hide latency.
