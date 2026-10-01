# Fourgate operator guide (Windows)

This is the step-by-step routine for running Fourgate scans against real MCP
servers without outside help: set up, write a contract, run the two standard
checks twice, read the report, and file a bug upstream. Every command is for
**Windows PowerShell 5.1**. The scanner's exact contract format is in
[`specs/scan-contract-v1.md`](specs/scan-contract-v1.md), and the data flow
is in [`SECURITY.md`](SECURITY.md).

Hard rules, every time:

- Writes go only to **your own disposable/free-tier test accounts**. Email
  tools send only to your own test inbox.
- Never run a delete tool on data you did not create.
- Never put a key in a contract, a chat, a bug report, a screenshot or a
  commit. Refer to keys by environment variable **name** only.
- If a write times out, do not rerun it until you have checked the account by
  hand. It may already have happened.
- **UNKNOWN is never FAIL.** A finding counts only after two matching runs.

## One scan day at a glance

1. Update the repo and run the tests (section 1).
2. Make a scan-work folder for the target and install the server there (section 1).
3. Write two contracts from the templates: healthy and invalid-credential (section 3).
4. Set keys in this PowerShell window only (section 2).
5. Run check A twice, then check B twice (sections 4 and 5).
6. Read each report (section 6).
7. For a confirmed finding: duplicate search, SECURITY.md, bug report (sections 7 and 8).
8. Paste the handoff block into the traction notes (section 9).
9. Close the PowerShell window (it discards the keys).

## 1. Setup

### Two folders: the repo and the scan-work folder

- **Repo**: `C:\hifzazafar\fourgate\fourgate`. Only Fourgate's own code and
  docs live here. Never put real contracts, reports or `node_modules` here.
- **Scan-work folder**: one folder per target **outside the repo**, for
  example `C:\fourgate-work\<target>\`. It holds the server install, your
  real contracts, and the `run1`/`run2` report folders. Nothing in it is ever
  committed.

### Blocked programs on this laptop

PowerShell blocks `.ps1` scripts and Application Control blocks some `.exe`
launchers. Therefore:

| Do not use | Use instead |
| --- | --- |
| `.venv\Scripts\activate` / `Activate.ps1` | call `.venv\Scripts\python.exe` directly |
| `pytest`, `pytest.exe` | `.venv\Scripts\python.exe -m pytest -q` |
| `fourgate`, `fourgate.exe` | `.venv\Scripts\python.exe -m fourgate scan ...` |
| `npm`, `npx` (they run `npm.ps1`) | `npm.cmd`, `npx.cmd` |

### Update Fourgate and check it works

```powershell
cd C:\hifzazafar\fourgate\fourgate
git checkout main
git pull
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

Only the first time, before the commands above: `py -3 -m venv .venv`.
Expect every test to pass. If one fails, stop and do not scan.

### Install the server under test (Node servers)

```powershell
New-Item -ItemType Directory -Force C:\fourgate-work\<target>
cd C:\fourgate-work\<target>
npm.cmd init -y
npm.cmd install <server package>
node --version
```

Find the server's start file: open
`node_modules\<server package>\package.json` and read its `"bin"` entry (for
example `dist/index.js`). The contract's `server.command` then becomes:

```json
["node", "node_modules/<server package>/<bin entry>"]
```

The command runs from the contract's folder, so the relative path works when
the contract is saved in the same scan-work folder. Avoid `npx` in the
contract: it re-downloads, prints extra output, and is slower to start.
`["npx.cmd", "-y", "<server package>"]` is a fallback only.

For a Python server, install it into its own venv in the scan-work folder and
use that venv's full `python.exe` path as the first command element.

## 2. Credentials

There are up to two keys, each in its **own** environment variable:

| Purpose | Variable name | Who reads it |
| --- | --- | --- |
| Server **write** key | Whatever the server's README/source reads (search the source for `process.env.` or `os.environ`) | The MCP server |
| **Read-back** key | `FOURGATE_READBACK_TOKEN` (the template's `token_env`) | Fourgate only; it is removed from the server's environment |

Use two separate keys when the vendor allows it, ideally a read-only key for
read-back. Never reuse one variable for both.

Set a key **in the current PowerShell window only**. It is not echoed:

```powershell
$s = Read-Host "Server write key" -AsSecureString
$env:<SERVER_KEY_ENV> = [System.Net.NetworkCredential]::new("", $s).Password
Remove-Variable s

$s = Read-Host "Read-back key" -AsSecureString
$env:FOURGATE_READBACK_TOKEN = [System.Net.NetworkCredential]::new("", $s).Password
Remove-Variable s
```

Check them with True/False only. Never print the value:

```powershell
[bool]$env:<SERVER_KEY_ENV>
[bool]$env:FOURGATE_READBACK_TOKEN
```

Rules:

- Never use `setx` or the System Properties dialog. They save the key
  permanently to the registry and every future program inherits it.
- Never type `$env:NAME` on its own (it prints the key), and never paste a key
  into a chat, contract, issue or commit.
- When you are done: `Remove-Item Env:<SERVER_KEY_ENV>, Env:FOURGATE_READBACK_TOKEN`,
  or close the window.
- Report redaction replaces values of environment variables whose **name**
  contains `token`, `secret`, `password`, `api_key`/`apikey`, `authorization`,
  `cookie` or `credential`. If the server's variable name contains none of
  these, its value is not auto-redacted. Review reports before sharing them
  in any case.

## 3. Writing a contract

Start from a template in [`examples/contracts/`](examples/contracts/):

- `text-id-readback.example.json` for check A (healthy write and read-back).
- `invalid-credential-check.example.json` for check B (invalid key, nothing created).

Every `<...>` value must be replaced. Work through these steps.

### 3a. Find the write tool and its arguments

In the server source (`node_modules\<server package>\` or the server's
GitHub repo), find where tools are registered:

```powershell
Get-ChildItem -Recurse -Include *.js,*.ts,*.py node_modules\<server package> |
  Select-String -Pattern "registerTool|server\.tool\(|@mcp\.tool|name:\s*['""]" |
  Select-Object -First 40
```

Pick one tool that **creates** a record (send, create, add, post). Copy its
name exactly into `write_tools` and `cases[0].tool`. Next to the
registration, read its input schema (zod object, JSON Schema or Python
signature). Fill `arguments` with only the required fields plus a recognizable
title, using harmless test values: your own test inbox, and a title such as
`FOURGATE DISPOSABLE TEST run1`.

### 3b. Pick how to extract the new record's ID

Read the tool's handler and look at what it returns. Then choose one selector
for `record_id`:

| The handler returns | Selector |
| --- | --- |
| `structuredContent: { id: ... }` | `{"source":"result","path":"result.structuredContent.id"}` |
| Text that is pure JSON or contains a JSON object, e.g. `Created! {"id":"..."}` | `{"source":"result","path":"result.content.0.text","parse":"embedded_json","field":"id"}` |
| Plain text, e.g. `Created task 12345` | `{"source":"result","path":"result.content.0.text","parse":"regex","pattern":"Created task (\\S+)"}` |

The regex uses the first capture group. Text selectors only work on
`result.content.0.text`. The pattern may be at most 256 characters. The
templates use a regex that captures a JSON `"id":"..."` value. In a JSON
file, every `\` in a pattern is written `\\` and every `"` is written `\"`.

### 3c. Find the read-back GET endpoint

In the **vendor's API docs** (not the MCP server), find the "retrieve/get one
record by ID" endpoint, e.g. `GET https://api.vendor.example/v1/items/{id}`.
Put it in `readback.url_template` with the extracted name in braces:
`https://<vendor-api-host>/<path-to-record>/{record_id}`.

- The host must be fixed and HTTPS. Only the path or query can use `{...}`.
- Fourgate sends `Authorization: Bearer <read-back key>`. If the vendor needs
  a different auth header, generic read-back cannot be used for that vendor.
- Leave out `missing_statuses`. A 404 then stays UNKNOWN. Add `[404]` only
  after confirming that the read-back key can fetch a record you created by
  hand.

### 3d. Choose expected_fields

`expected_fields` maps a **path in the GET response JSON** to an extracted
name. Compare a value you sent, usually the title or subject:

```json
"extract": {
  "record_id": { "...": "selector from 3b" },
  "title": {"source": "arguments", "path": "subject"}
},
"readback": { "expected_fields": {"subject": "title"} }
```

Paths are dot-separated. List indexes are numbers, e.g. `data.0.name`. Never
compare timestamps, IDs generated by the server, or values that the vendor
reformats.

### 3e. Save the file without a BOM

PowerShell 5.1's `Out-File` and `Set-Content -Encoding utf8` add a byte order
mark (BOM), which makes the contract invalid. Save with .NET instead, using a
**full path**:

```powershell
$json = @'
{
  "scan_version": 1,
  ...paste the whole edited contract here...
}
'@
[IO.File]::WriteAllText("C:\fourgate-work\<target>\healthy.json", $json)
```

The `'@` line must start at column 0. Notepad is also fine if it saves as
"UTF-8", **not** "UTF-8 with BOM".

### 3f. Validate before any write

These two checks start no server and send no write:

```powershell
Select-String -Path C:\fourgate-work\<target>\healthy.json -Pattern "<"
cd C:\hifzazafar\fourgate\fourgate
.venv\Scripts\python.exe -c "from fourgate.scan import load_contract as l; l(r'C:\fourgate-work\<target>\healthy.json', 'my-disposable-account'); print('valid')"
```

The first command must print nothing (no `<placeholder>` left). The second
must print `valid`. The label argument must equal the contract's
`server.test_account` exactly.

## 4. The two standard checks

### Check A: healthy write on a disposable account

- Contract: from `text-id-readback.example.json`, saved as `healthy.json`.
- Keys: a **valid** server write key for the disposable account, plus the read-back key.
- Expect **`PASS / postcondition_satisfied`**: the tool returned an ID and
  the independent GET found the record with the values you sent.

Check A shows that the contract is right. Do not interpret check B for a
server until check A has passed for it, or until you have a documented reason
why A cannot run (for example, the vendor's read API needs an auth header
that Fourgate does not send).

### Check B: invalid-credential failure check

- Contract: from `invalid-credential-check.example.json`, saved as
  `invalid-key.json`. It has no `token_env` and needs no read-back key.
- Keys: set the server's write-key variable to an obviously fake value. No
  account is used and nothing can be created:

  ```powershell
  $env:<SERVER_KEY_ENV> = "invalid-fourgate-check-key"
  ```

- A **correct** server reports the vendor's rejection as a tool error:
  `"isError": true` in the tool result. Fourgate shows that as
  **`UNKNOWN / not_success_result`**. That is the healthy outcome; there is
  no finding.
- **Finding**: `UNKNOWN / success_without_record_id`, and in the report's
  `evidence.tool_response.result` the text contains an API error (401,
  `Unauthorized`, `invalid API key`, ...) while `isError` is absent or
  `false`. The server returned a failure as a successful tool result, so an
  agent would believe the write worked.
- A JSON-RPC `error` object instead of `result` also shows as
  `not_success_result`. The failure is visible, so this check does not count
  it as a finding.
- If the server refuses to start with a fake key (`RuntimeError`, tool
  `null`), it validates keys at startup. Note it and move on; this is not a
  finding.
- If the result unexpectedly contains an ID, stop and inspect the tool
  response by hand. Do not file anything until you understand it.

## 5. Running: always two runs

Run from the repo with the venv's Python. Each run gets its own report folder:

```powershell
cd C:\hifzazafar\fourgate\fourgate
.venv\Scripts\python.exe -m fourgate scan C:\fourgate-work\<target>\healthy.json --confirm-test-account "my-disposable-account" --report-dir C:\fourgate-work\<target>\healthy-run1
$LASTEXITCODE
```

Then change the title argument from `run1` to `run2`, so the second write
creates a fresh, distinguishable record. Save the file without a BOM again
and rerun with `--report-dir ...\healthy-run2`. Do the same for check B
(`invalid-run1`, `invalid-run2`).

Exit codes: `0` = every case PASS; `1` = any FAIL or UNKNOWN; `2` = invalid
configuration or the server command could not be launched (read the
`fourgate: scan configuration error:` line).

**A finding counts only if run1 and run2 match**: same status, same
`reason_code`, and the same kind of tool response (for check B: the same
error text and no `isError` both times). If the runs differ, it is not a
finding. Note it and investigate; do not file it.

## 6. Reading reports

Each `--report-dir` gets `fourgate-report.json` and a self-contained
`fourgate-report.html`. Show the summary:

```powershell
$r = Get-Content C:\fourgate-work\<target>\healthy-run1\fourgate-report.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.cases | Select-Object tool, status, reason_code, attempts
$r.cases[0].evidence.tool_response.result | ConvertTo-Json -Depth 10
$r.cases[0].evidence.readback | ConvertTo-Json -Depth 10
```

`evidence` appears only for cases that did not PASS.

| status / reason_code | Meaning | What to do |
| --- | --- | --- |
| PASS / `postcondition_satisfied` | Independent GET found the record and every `expected_fields` value matched. | Healthy. Check A done. |
| FAIL / `field_mismatch` | The record exists, but a field differs (`mismatched_fields` shows expected vs observed). | Check your response path and whether the vendor reformats the value first. A finding only if the stored value really differs from what was sent, in both runs. |
| FAIL / `record_missing` | GET returned a status you listed in `missing_statuses` on every attempt. | Possible missing write. Confirm by hand in the vendor UI before calling it a finding. |
| UNKNOWN / `readback_unconfirmed` | GET returned another status. `evidence.readback.status` holds the number. | 401/403: wrong read-back key or scope. 404: wrong URL or record not visible yet. 429/5xx: vendor problem, rerun later. |
| UNKNOWN / `success_without_record_id` | Tool result had no `isError`, but the ID selector found no ID. No read-back was attempted. | Check B: if the text is an API error, this is the finding. Check A: fix the selector (3b) or read the text: it may be an error reported as success. |
| UNKNOWN / `not_success_result` | Tool result had `isError: true` (or a JSON-RPC error). | Check B: the correct, healthy outcome. Check A: the write failed; read the text. |
| UNKNOWN / `credential_missing` | `token_env` is not set in this window. **No write was sent.** | Set the read-back key (section 2) and rerun. |
| UNKNOWN / `tool_not_discovered` | The server's tool list does not contain that name. **No write was sent.** | Wrong tool name, or the server needs a flag/env var/mode to enable write tools (see its README). |
| UNKNOWN / `RuntimeError`, tool `null` | The server failed to start, initialize or list tools. | See troubleshooting. |
| UNKNOWN / `TimeoutError` | The call exceeded `call_timeout_ms` and the scan stopped. | The write **may have happened**. Check the account by hand before any rerun. |
| UNKNOWN / `readback_shape_invalid` | GET returned 200, but an `expected_fields` path is absent. | Fix the response path (3d). |
| UNKNOWN / `readback_error`, `readback_timeout` | Network failure or the read-back time budget ran out. | Rerun later; raise `timeout_ms` (max 10000) if needed. |
| UNKNOWN / `required_field_missing` | An extract selector other than the ID found nothing. | Fix that selector's path. |

**UNKNOWN is never FAIL.** UNKNOWN means Fourgate could not confirm the
outcome either way. Only check B's specific `success_without_record_id`
pattern, with the error text visible in the tool response, is filed as a
finding, because there the server's own response proves the failure.

## 7. Before filing

1. **Duplicate search** in the server's GitHub repo (`is:issue` covers open
   and closed issues):
   - `is:issue isError`
   - `is:issue "<exact error text from the tool response>"`
   - `is:pr isError`, in case a fix is already in review.

   If a matching issue exists, add a short comment with your new
   reproduction instead of opening a new issue.
2. **Read the repo's `SECURITY.md`.** If the bug exposes data or credentials,
   or allows acting without authorization, report it **privately** in the way
   SECURITY.md describes (often Security tab, then "Report a vulnerability").
   Never report it in a public issue.
3. **Use the repo's issue form** if "New issue" offers templates. Choose the
   bug form and put the section 8 content into its fields.

## 8. Bug report template

Fill in only real values, and delete any line you cannot fill. Do not include
a pitch, a Fourgate link, keys, emails, account IDs or record IDs. Paste
error text only after removing any identifiers it contains.

````markdown
**Title:** `<tool name>` returns API failures as a successful tool result (missing `isError: true`)

### Environment
- Server: `<package name>` `<version>` (stdio)
- Node: `<node --version>` / OS: Windows 11
- MCP protocol version: 2024-11-05

### What happens
When the upstream API rejects the request, `<tool name>` returns the error
message as normal text content without `isError: true`. An MCP client or
agent reads this as a successful call.

### Steps to reproduce
1. Set `<SERVER_KEY_ENV>` to an invalid value, e.g. `invalid-key`.
2. Start the server over stdio and call `<tool name>` with:
   `{"<argument>": "<harmless test value>"}`
3. Look at the `tools/call` result.

Reproduced 2/2 times.

### Actual result
```json
{"content": [{"type": "text", "text": "<error text, identifiers removed>"}]}
```
No `isError` field.

### Expected result
`"isError": true` in the tool result, so clients and models can see that the
call failed. The MCP spec says tool execution errors should be reported in
the result with `isError` set to true.

### Where in the code
`<file>:<line>`: the error path / catch block returns
`{ content: [...] }` without `isError`.

### Possible fix
Return `{ content: [...], isError: true }` on that path (and check whether
the other write tools share it).
````

After filing: if there is no reply in 5–7 days, post **one** follow-up comment
that adds new information only, e.g. "still reproduces on `<new version>`".
Then stop.

## 9. Engineering handoff block

After each scan day, paste this into the traction notes. Server names stay in
private notes only and never go into public posts:

```text
Engineering handoff <YYYY-MM-DD>:
- Servers scanned: <n> (<names; private notes only>)
- Checks run: A <n> / B <n>, each twice
- Confirmed findings (both runs matched): <n>
- Bug reports filed: <links>
- Maintainer replies or fixes: <which, or "none">
- Anything traction can use publicly (anonymized): <one line, or "none">
```

Nothing else crosses over: no commands, keys, raw reports or account details.

## 10. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `scan configuration error: Unexpected UTF-8 BOM` | Contract saved with a BOM (`Out-File`, `Set-Content -Encoding utf8`, Notepad "UTF-8 with BOM"). | Save again with `[IO.File]::WriteAllText` (3e). |
| `scan configuration error: --confirm-test-account must exactly match ...` | Label differs from `server.test_account`. | Copy the label exactly, including case and spaces. |
| `scan configuration error: [WinError 2] ...` | The first `server.command` element was not found (e.g. `npx` instead of `npx.cmd`, or `node` not on PATH). | Use `node` plus the bin path (section 1), or `npx.cmd`; check `node --version`. |
| `UNKNOWN / tool_not_discovered` | The tool name is misspelled, or the server hides write tools unless a flag or mode is set (read-only mode, a toolset list, a feature flag). | Copy the name from the source (3a); enable the server's write mode as its README describes. |
| `UNKNOWN / RuntimeError` with `"tool": null` | The server did not start or crashed before listing tools. A common cause is a failed native build during `npm.cmd install` (node-gyp / missing build tools), which leaves a broken `node_modules`. | Run the server command by hand in the scan-work folder to see its error. For a failed native build: make a **fresh** folder and run `npm.cmd install <server package> --ignore-scripts`, then retry. Also check that its required env vars are set. |
| `UNKNOWN / credential_missing` | `token_env` is not set in **this** window (keys do not carry over between windows). | Section 2, then `[bool]$env:FOURGATE_READBACK_TOKEN` must print `True`. |
| `UNKNOWN / readback_unconfirmed`, `evidence.readback.status: 401` (or 403) | The read-back key is wrong, expired, lacks read scope, or the vendor expects a different auth header than `Bearer`. | Re-enter the key; check its scope in the vendor dashboard. If the vendor does not use Bearer auth, generic read-back cannot verify it. |
| PASS expected but `success_without_record_id` in check A | The ID selector does not match the real response text. | Look at `evidence.tool_response.result.content` and fix the regex/path (3b). |

## 11. Runtime shadow mode

To run the same approved postcondition through the runtime Outcome Guard
wrapper (`wrap/wrap.py`) in shadow mode with a real agent client, follow
[`HANDOFF.md`](HANDOFF.md), section "Shadow mode with a real connector".
Start only from a check A contract that already returned PASS. Never use
`--outcome-mode enforce`.
