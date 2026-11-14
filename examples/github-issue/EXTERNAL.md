# Live disposable GitHub Issue scan (second person)

Use this only after the [local simulation](README.md#reproduce-entirely-locally)
exits 0 on your machine. This path performs a **real Issue update** on an
authorized disposable repository.

**Fourgate version:** limited beta `0.4.0b1`. **Transport:** local stdio only.
Customer CI / Desktop UI remain unvalidated.

## Secrets (names only)

| Purpose | Environment variable **name** | Who reads it |
| --- | --- | --- |
| GitHub MCP write | `GITHUB_PERSONAL_ACCESS_TOKEN` (confirm against your installed server’s docs) | MCP server process |
| Independent read-back | `FOURGATE_GITHUB_READ_TOKEN` | Fourgate only (withheld from the server) |

Use two separate tokens when possible. Never put values in JSON, chat, commits,
or screenshots. Confirm presence with a boolean check, not by printing.

```bash
test -n "$GITHUB_PERSONAL_ACCESS_TOKEN" && test -n "$FOURGATE_GITHUB_READ_TOKEN" && echo ready
```

```powershell
[bool]$env:GITHUB_PERSONAL_ACCESS_TOKEN; [bool]$env:FOURGATE_GITHUB_READ_TOKEN
```

## Exact steps

1. **Install** `fourgate==0.4.0b1` (see [docs/external-disposable-scan.md](../../docs/external-disposable-scan.md)).
2. **Discover** the official GitHub MCP Server local stdio binary and pin a
   reviewed version (reference shape: v2.0.3 `issue_write` update → minimal
   `{id,url}` success). Do not guess the command from the package name alone.
3. **Complete** [review-card.example.md](review-card.example.md) for one existing
   disposable Issue (not a PR). Note the current title/body/state before changing them.
4. **Copy** into a private work directory (not this git tree):

   - `scan.example.json` → `scan.json`
   - `runtime.example.json` → `runtime.json`
   - `readback.example.json` → `readback.json`

5. **Edit** every `REPLACE_*` / `REPLACE WITH …` marker in all three files so they
   agree:

   - `server.command` = reviewed local stdio argv
   - `arguments.owner` / `arguments.repo` / `readback.repository` = `owner/repo`
   - `arguments.issue_number` = the existing Issue number
   - `title` / `body` / `state` = the approved post-update values
   - `server.test_account` stays `disposable-github-issue` (or change it and use
     the same label with `--confirm-test-account`)

6. **Doctor** (no write):

```bash
fourgate doctor \
  --contracts ./runtime.json \
  --protocol-version 2026-07-28 \
  --server github \
  --log ./outcomes.jsonl \
  -- /path/to/github-mcp-server stdio
```

Expect `Verdict: READY FOR SHADOW` (exit 0).

7. **Scan** (one contracted update):

```bash
fourgate scan ./scan.json \
  --confirm-test-account disposable-github-issue \
  --report-dir ./fourgate-report
```

```powershell
fourgate scan .\scan.json `
  --confirm-test-account disposable-github-issue `
  --report-dir .\fourgate-report
```

8. **Review** `fourgate-report.html` before sharing. Redaction is best effort.

## Expected results

| Scenario | `cases[0].status` / `reason_code` | Scan exit |
| --- | --- | --- |
| Healthy update; GET matches approved number/title/body/state | `PASS` / `postcondition_satisfied` | 0 |
| Deliberate wrong expected title (authority unchanged) | `FAIL` / `field_mismatch` | 1 |
| `FOURGATE_GITHUB_READ_TOKEN` unset | `UNKNOWN` / `credential_missing` (no write sent) | 1 |
| GitHub GET 404 with `missing_is_fail: false` | `UNKNOWN` / `readback_unconfirmed` | 1 |
| Template markers left in the contract | configuration error naming the paths | 2 |

Keep `missing_is_fail: false`. A 404 is ambiguous (missing vs invisible).

Do not retry a timed-out write. Cleanup (e.g. restore title/close) is a
**separate** authorized action after you have reviewed the report.

## Runtime shadow (optional)

```bash
fourgate guard --contracts ./runtime.json --mode shadow --server github \
  --log ./outcomes.jsonl -- /path/to/github-mcp-server stdio
fourgate summary ./outcomes.jsonl --out ./fourgate-summary.html --json
```

Use the summary for [measurement](../../docs/measurement-package.md). Runtime
verifier timeout stays **2000 ms**.
