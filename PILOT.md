# Fourgate pilot: how it works and where your data goes

This page is for a team evaluating Fourgate, including whoever reviews it for
security. It describes what runs, what is stored, and what leaves your
machines. [`SECURITY.md`](SECURITY.md) has the full data-flow detail.

## The short version

- Fourgate runs **entirely on your machines** (a laptop, a server, or your CI).
  There is no Fourgate cloud service, account, database or telemetry.
- Fourgate **never stores your credentials**. You set them as environment
  variables on your side; they are never written to contracts, logs or the
  summary page.
- Nothing is sent to Fourgate. You decide what, if anything, to share with us,
  and the summary page is built to be shareable.
- In shadow mode (the pilot default, without the legacy `--baseline` flag),
  your agent receives **exactly the same bytes** it would without Fourgate. If anything in Fourgate fails, the call
  passes through unchanged.

## What runs where

```
 Your agent (e.g. an MCP client)
        │  tools/call
        ▼
 wrap.py  ── local process on your machine ─────────────────────────────┐
        │  forwards the call unchanged                                  │
        ▼                                                               │
 Your MCP server  ──(its own API calls, as today)──►  Your system of record
        │  "success" result                                             ▲
        ▼                                                               │
 wrap.py extracts only the contracted fields (e.g. record ID, title)    │
        │                                                               │
        └─► verifier (local)  ── HTTPS GET with a separate read-only ───┘
                 │               credential
                 ▼
         PASS / FAIL / UNKNOWN  ──►  outcomes.jsonl (local, structure only)
                                            │
                                            ▼
                               fourgate summary  ──►  local HTML page
```

The only new network traffic Fourgate adds is the verifier's **GET request to
the read-back endpoint you configure**. It never writes, deletes, or retries a
write.

## What is stored

| Item | Where | What it contains | What it never contains |
|---|---|---|---|
| Runtime contract (`runtime-contract.json`) | Your machine or repo | Tool names, which fields to extract, the verifier command, env var **names** | Credentials, customer data |
| Read-back config (`readback.json`) | Your machine or repo | The GET URL template, expected fields, status rules, env var **name** of the read token | The token itself |
| Outcome log (`outcomes.jsonl`) | Path you choose | Per protected call: time, server label, tool name, mode, PASS/FAIL/UNKNOWN, reason code, names of checked fields, time the check added | Arguments, field values, record IDs, response bodies, credentials |
| Summary page (`fourgate-summary.html`) | Path you choose | Counts and charts built from the outcome log | Same exclusions as the log; no JavaScript, no network requests |
| Scan reports (`fourgate-report.json/.html`) | Only if you pass `--report-dir` | For test-account scans: the contracted request, tool response and read-back evidence for non-passing cases, after best-effort secret redaction | Review before sharing; redaction is best effort |

Fourgate keeps no other state. To uninstall, `pip uninstall fourgate`, point
your MCP client back at the original server command, and delete these files.

## Credentials

- The MCP server keeps its own write credential, exactly as today.
- The verifier uses a **separate, read-only** credential that you create.
  When you list its variable name in `verifier.secret_env`, `wrap.py` removes
  it from the MCP server's environment, so the server under test cannot see
  or use it.
- Both are environment variables you set yourself. Contracts, logs and the
  summary page contain only the variable **names**; the verifier reads the
  token value from its environment at call time and sends it only to the
  read-back endpoint you configured.

## Failure behavior

- **Shadow mode** (default): results are recorded only; the agent sees nothing
  different.
- **Enforce mode** (only after you approve the contracts): on a confirmed FAIL,
  Fourgate adds one attributed verdict before the tool's original response so
  the agent knows the write did not land. Nothing else changes.
- Any Fourgate problem (verifier timeout, network error, bad config, internal
  error) is **UNKNOWN and fails open**: the call goes through untouched.
- No LLM makes the PASS/FAIL decision; it is a deterministic read-back check.

## What a pilot looks like

1. **Scope (30 min call):** pick 1–3 state-changing tools that matter, and the
   API that can confirm each write.
2. **Contracts:** we write the contracts with you; you review and approve them.
3. **Test account scan:** run `fourgate scan` against a disposable account to
   prove each contract (healthy write = PASS, deliberate mismatch = FAIL).
4. **Shadow run:** wrap the server for your real agent traffic in shadow mode.
5. **Review:** `fourgate summary outcomes.jsonl` turns the log into one page.
   You choose whether to share it with us.

## Current requirements and limits

- MCP servers launched as **local stdio** processes. Remote (HTTP) MCP servers
  are not supported yet.
- Read-back is an **HTTPS GET** to an API that can return the written record,
  authenticated with a Bearer token or with no auth.
- Each check is capped at 2000 ms. On a Windows laptop the HTTP verifier
  measured 1.2–1.6 s per call, so add this latency to protected calls.
- Contracts are written by hand and reviewed by a human.
- Python 3.10+. Tested on Windows and Linux.
