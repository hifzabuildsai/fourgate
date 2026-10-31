# Phase D3: live GitHub Issue acceptance — 2026-10-31

## Result and evidence boundary

**D3_LIVE_PASS / CLEANUP_VERIFIED.** One previously authorized update of the
existing [disposable Issue #10 (private; access required)](https://github.com/hifzabuildsai/fourgate-e2e-validation/issues/10)
returned a fresh typed PASS through Fourgate's local MCP adapter. One saved-report
retrieval matched it without another target start, call or outcome GET. An
independent read matched the approved fields. Only after complete PASS evidence
was written and hashed, one cleanup close and one independent GET confirmed
`closed`, retaining the verified title/body.

This note reconciles **preserved local artifacts**, not a new acceptance run.
Documentation closeout made no workflow, target, verifier, credential check,
Issue GET or cleanup call. The original **three-mutation budget is exhausted**;
the command history below is not permission or instructions to rerun it.
This was a scripted local stdio client against the real official GitHub MCP
Server and GitHub API, not Desktop UI/app-server acceptance or customer CI.

The earlier [D1](github-issue-reference-2026-10-23.md),
[D2](github-issue-mcp-2026-10-23.md) and
[v2.0.3 compatibility](github-mcp-compatibility-2026-10-31.md) records retain their
dated scope. Their simulations/schema inspection did not themselves establish
this later live result.

## Exact source, binary and contract pins

| Item | Preserved value |
| --- | --- |
| Fourgate source, detached worktree | `c5d61fbd3f3ffedbf5221e6f13d750ef7acf6dd3` |
| Fourgate package/typed-report version string | `0.3.0`; source revision above, not a new PyPI release |
| Official GitHub MCP Server | `2.0.3`, commit `b98d115bbb080e9555466a96656ec4df605aea21` |
| Platform asset | `github-mcp-server_Windows_x86_64.zip` |
| Asset SHA-256 | `f0e1b9880a1b88730d1250d1c25cfee39617ec3e800a7a252f2279cd0c8394e0` |
| Extracted executable SHA-256 | `647fe7e7f3c1296d1acb936b5c7704bbcdb6bda95b4533c524157446b33f0f16` |
| Exact adapted `scan.json` SHA-256 | `3f7b0a7d3cecd4896877c7285cfeb7f2bebfaab1c445493d7db75f9f99dd36bd` |
| Registry file SHA-256 | `0141a6eda224c8a4dcf9a0c827ecc40bfb0e047e9c89ac212c2d6b3a20a186a2` |
| Policy file SHA-256 | `60b8542098ffeb325771fdbe0d692577505f5491bd8492129bdfd82ffcda8f5a` |
| Workflow ID | `reference-issue` |
| Single-use run ID | `d3-live-20261031-954767a7d92e4381a13d7cffa483299b` |

The archive came from the
[official v2.0.3 asset](https://github.com/github/github-mcp-server/releases/download/v2.0.3/github-mcp-server_Windows_x86_64.zip).
Its required checksum matched before execution; `--version` reported the exact
version and commit above. No global install, PATH or client configuration change
was made. The original checkout and user changes were preserved during D3;
the source worktree was detached and clean.

The merged [reference template](../../examples/github-issue/scan.example.json)
kept its request-derived extraction and equality predicates. The reviewed request
used `issue_write`, `method: update`, owner `hifzabuildsai`, repository
`fourgate-e2e-validation`, Issue number `10`, and `state: open`:

- Title: `[Fourgate D3] VERIFIED c5d61fbd`
- Body: `Fourgate D3 live GitHub MCP v2.0.3 acceptance. One protected update; outcome independently read back. Source c5d61fbd.`

The static read-back repository was the same owner/repository; expected number,
title, body and state came only from the approved arguments. Read-back used
`FOURGATE_GITHUB_READ_TOKEN`, `attempts: 1`, `interval_ms: 0`, `timeout_ms: 1500`,
and `missing_is_fail: false`. The target's separate credential was named
`GITHUB_PERSONAL_ACCESS_TOKEN`; the scanner withheld the read credential from
the child target. GitHub MCP's minimal `{id, url}` result was not the PASS oracle.

## Credential preflight is NOT_RUN, not an outcome verdict

All credential checks below are historical. No credential was loaded or checked
for this documentation closeout. Existing encrypted credential files were
preserved; replacement write and read credentials were supplied separately
through masked local setup and loaded into process memory for D3.

| Preflight attempt | Issue endpoint GETs | Observed HTTP statuses | Protected action / Fourgate outcome |
| --- | --- | --- | --- |
| Original write credential | 1 | Write `401`; stopped before checking read | `NOT_RUN`; not evaluated |
| Replacement write, preserved original read | 2 | Write `200`, read `401`; stopped | `NOT_RUN`; not evaluated |
| Separate replacement write and read | 2 | Write `200`, read `200`; exact open PRESTATE matched | `NOT_RUN`; not evaluated |

PRESTATE was `[Fourgate D3] PRESTATE c5d61fbd`, Issue number `10`, state `open`;
both successful final preflight reads agreed on the selected Issue fields.
Before the successful continuation there were zero protected calls and no
prepared grant. A readable record alone did not establish write permission,
read-only token scope, or an action PASS.

The first preserved stop file used `UNKNOWN` for the overall acceptance stop.
It must not be interpreted as a Fourgate outcome verdict: no adapter execution,
target call or outcome GET had occurred. Both HTTP 401 failures remain
credential-preflight failures with **protected action NOT_RUN and no Fourgate
outcome verdict**; the original artifacts were retained verbatim.

## Recorded commands and process exits

Only local path prefixes are normalized below: `OUT` denotes the original ignored
`fourgate-output/d3-live-20261031-6c8f3a9e` directory in the existing checkout,
`SRC` the detached source worktree, and `PY` the existing checkout's
`.venv/Scripts/python.exe`. The generated helpers remain private/local and are
not included in Git. Arguments and ordering describe the preserved executions.

| Recorded process / command | Working directory | Exit |
| --- | --- | --- |
| `pwsh.exe -NoProfile -ExecutionPolicy Bypass -File OUT/secure-run.ps1 -Stage preflight` | Existing checkout | `20` (original write GET 401; NOT_RUN) |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File OUT/secure-resume.ps1 -Stage preflight` | Existing checkout | `10` (read GET 401; NOT_RUN) |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File OUT/secure-live.ps1 -Stage preflight` | Existing checkout | `0` (both GETs 200; still NOT_RUN) |
| `OUT/github-mcp-server.exe --version` | `OUT` | `0` |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File OUT/offline-discovery.ps1` | Existing checkout | `0` |
| `OUT/github-mcp-server.exe stdio --tools=issue_write` (fake-token discovery) | `OUT` | `0`, no forced termination |
| `PY -B -m fourgate mcp --registry OUT/registry.json --execution-policy OUT/policy.json --prepare-execution-state` | `SRC` | `0`, prepared exactly once; actions NOT_RUN |
| `PY -B OUT/adapter-observer.py` (scripted MCP serving process) | `SRC` | `0`, no forced termination |
| `OUT/github-mcp-server.exe stdio --tools=issue_write` (protected target) | `OUT` | `0` |

The `secure-live.ps1` launcher's remaining recorded stages were `pin`, `prepare`,
`execute`, `cleanup` and `finalize`, each with the same PowerShell flags above
and exit **0**. The observer recorded starts, wire messages and GET boundaries
while delegating once to the unchanged pinned adapter/scanner/verifier functions;
it introduced no tracked runtime changes. The serving entry called Fourgate's
MCP adapter with `--registry OUT/registry.json --execution-policy OUT/policy.json`.
Process exit 0, `isError: false`, static readiness or a minimal tool result alone
was never accepted as an action PASS.

Earlier non-action preparation/reporting errors are also preserved: the initial
Git fetch hit a sandbox `FETCH_HEAD` permission error (exit 1), then the authorized
fetch succeeded (exit 0); the detached-worktree creation exited 0. An initial
local report seal exited 20 on synthetic token-pattern matches in the existing
redaction unit test. Its local audit and corrected seal exited 0 with no actual
credential matches. None was a protected action failure or a protected-write retry.

## Discovery, static readiness, fresh execution and saved report

Offline discovery used a clearly fake token, an active outbound firewall block
scoped to the pinned executable, and a blocked proxy as a second restriction.
Under protocol `2026-07-28`, only `server/discover` and `tools/list` were sent:
**one offline start, two RPC requests, zero tools/call**. Only `issue_write` was
advertised; `update` and owner/repo/issue_number/title/body/state were confirmed.
The temporary firewall rule was removed before the live target started.

The real adapter then received `server/discover`, `tools/list`, and exactly these
three tool calls, in order. Counts below are cumulative for live execution;
they exclude the separate fake-token discovery and the `--version` process.

| Step | Adapter tool calls | Live target starts | Target tools/call | Fourgate outcome GETs | Typed meaning |
| --- | --- | --- | --- | --- | --- |
| One-time state preparation | 0 | 0 | 0 | 0 | Actions NOT_RUN; grant AVAILABLE |
| `validate_workflow` once | 1 | 0 | 0 | 0 | CONFIG_VALID / STATIC_CONFIG_ONLY / NOT_RUN |
| Fresh `run_workflow` once | 2 | 1 | 1 | 1 | COMPLETED / ATTEMPTED / PASS; new_execution true |
| `get_run_report` once | 3 | 1 | 1 | 1 | Saved matching PASS; new_execution false |

Static validation left the AVAILABLE grant's bytes unchanged. Fresh and saved
responses had matching text/structuredContent, `resultType: complete` and
`isError: false`. The fresh report recorded `reserved_tool_calls: 1`,
`call_attempts: 1`, case **PASS / postcondition_satisfied**, and the pinned run ID
and contract hash. The stored report equaled the fresh payload. Retrieval
returned that payload with only `new_execution` changed to `false`, added
**zero starts, zero calls and zero GETs**, and left the SQLite bytes unchanged.
Its retained `action_status: ATTEMPTED` describes the original action, not a new
attempt or a fresh verification.

There were five adapter RPC requests in total and three live target RPC requests
(`server/discover`, `tools/list`, `tools/call`). No repeated `run_workflow`,
write retry or restarted-client replay was attempted in D3. D2's separate local
replay evidence remains historical evidence, not additional D3 traffic.

## Issue reads, completed grant and cleanup

| Issue endpoint reads across the whole D3 task | GET count |
| --- | --- |
| Credential/preflight reads, including both stopped attempts | 5 |
| Fourgate deterministic outcome verification | 1 |
| Independent read after fresh PASS and saved-report retrieval | 1 |
| Independent cleanup confirmation | 1 |
| **Total Issue endpoint GETs** | **8** |

The final successful continuation alone accounts for five of those eight GETs:
two credential reads plus the single outcome GET, independent after-read and
cleanup confirmation. Public release/asset access and Git fetch are outside this
Issue-read count. `get_run_report` added no HTTP GET. The outcome and independent
after-read both observed exact approved number/title/body/`open` equalities.

One one-call grant was prepared, verified **AVAILABLE / reserved_calls 0 / no
report**, then consumed. It remained **COMPLETED / reserved_calls 1**, with the
fresh report stored, after retrieval and cleanup. No grant was reset, restored,
replaced, repinned or prepared again. The policy's canonical fingerprint was
`3904e79c32734b976835c40641c7602f005716a998e3fc9d6bc5089e1e11048b`
(distinct from the policy file's SHA-256). The preserved completed database
SHA-256 was `9cbcb6ad3e33fcd3b85fa442fc0f971dd45de2767906c941ac14b01ea1af97c5`.

| Authorized mutation | Count | Preserved observation |
| --- | --- | --- |
| Already consumed Issue #10 setup | 1 | Existing PRESTATE record; not recreated |
| Protected `issue_write` update | 1 | Exact fields independently matched; typed PASS |
| Cleanup close after preserved PASS | 1 | PATCH body only `{"state":"closed"}`; HTTP 200 |
| **Total / maximum** | **3 / 3** | **Budget exhausted; protected-write retries 0** |

Cleanup did not send title/body changes. Its response and the separate read-token
GET both returned HTTP **200**, Issue `10`, state **closed**, with the exact
verified title/body above. This records state at those observations; it is not
a new statement about current remote state. The consumed database and all prior
evidence remain preserved. The continuations and documentation closeout reused
the existing Issue; no additional Issue was created or recreated.

## Preserved artifacts and remaining limits

The ignored `OUT` contains the raw local records. Relevant records include
`live-validation.json`, `live-fresh-result.json`, `live-saved-result.json`,
`live-target-requests.jsonl`, `live-events.jsonl`, `live-outcome-readback.json`,
`live-independent-after.json`, `live-cleanup-verified.json`, and
`live-final-report.json`. Credentials, encrypted files, databases, raw logs,
generated contracts and harness scripts are not published in this PR.

| Local integrity anchor | SHA-256 |
| --- | --- |
| Complete PASS manifest, written before cleanup | `d21f1ee63cee626d9cfbd5ece6d96dd5bf5b44ac8b6897a8a360403ae88ccb45` |
| Final artifact manifest | `4c2f0edca33a8b3d0f6c5b3cbfc1c57903695e5383404d21ab4eeb074be63efa` |
| Final sanitized report | `9f0adbc1d45b8beafa45d049ba8c24b4deb8c92af9498d2466417452df06881a` |
| Complete typed PASS record | `df86d21b1d1e8ce4985d992117b36f86a25b556317871f83a67d19bdd2c2cf89` |
| Cleanup verification record | `d7715c915abfc81bf35e67c9fc00c14989e18be2e96248a1cd9862d27cb45db7` |

Five preserved manifests were verified locally during reconciliation; their
contents, including consumed state, were not rewritten. The D3 final secret
scan recorded zero exact current-credential matches and zero unreviewed token
patterns; two matches were known redaction-test fixtures. It scanned 197 tracked
files across the two checkouts and 118 generated text/private records. This is
preserved scan evidence, not a fresh credential check or a guarantee of universal
secret detection. Raw artifacts require local access; the Issue link requires
private-repository access. Public hashes alone do not expose or independently
reproduce those private observations.

This closes the bounded founder-owned live GitHub mapping and scripted local
stdio acceptance gap at the exact source/server pins. Desktop UI/installed
app-server routing, automatic activation, external-owner/customer CI, broader
OS/protocol coverage, later GitHub MCP releases and sustained production
reliability remain outside this evidence. Matching fields do not establish
universal freshness, token scopes, write causality or provider exactly-once
behavior. No natural silent-success incident was observed or claimed. No
runtime change, release/version bump, merge or deployment accompanies this note.
