# Fourgate

**Open source · MCP preflight + runtime wrap**

Catch it
before the agent
does.


---

# Fourgate

**Status: early, pre-alpha.** Two tools in this repo, at different levels of maturity:

1. A **preflight CLI** — spawns your MCP server, talks raw JSON-RPC to it, and reports stdout-cleanliness and schema-fuzzing failures before you ship. This one works end to end.
2. A **runtime wrap** — sits on the live `tools/call` path between an MCP host and server, and rewrites what the model reads when a tool result looks like a silent failure. This one is real code with a real proof, but it currently does nothing on any server you haven't hand-built a baseline for. See "What doesn't work yet" below before you rely on it.

Fourgate does not claim to prevent silent failures. Today it classifies exactly one kind (`silent_empty`), only when a baseline exists, and passes everything else through unchanged.

## Why this exists

MCP tools can return a technically-valid, schema-valid "success" that is actually empty, fake, or stale — an expired auth token that still returns `200`, a search that silently returns `{results: []}` instead of an error, a payload so large the agent truncates its own reasoning around it. The JSON-RPC layer sees no error. The agent sees "done" and acts on it. Fourgate's premise is that this class of failure has to be caught on the path the model actually reads, not in a log a human checks later.

---

## 1. Preflight CLI

Spawns your MCP server as a real subprocess and speaks JSON-RPC to it directly — not through a client library that would just crash on the same bug it's supposed to catch.

- **Stdout cleanliness** — any non-JSON line on stdout breaks the JSON-RPC stream. Fourgate reads raw and reports the exact offending line. This is the confirmed, narrow gap: the one failure mode the MCP framework itself does not protect you from.
- **Schema robustness** — for every declared tool, sends a valid call, a wrong-typed call, and a numeric edge case, and checks whether the server fails closed with a clean JSON-RPC error, or fails open with a crash, hang, or silently-coerced bad data.

### Quickstart

```bash
git clone https://github.com/hifzabuildsai/fourgate.git
cd fourgate
pip install -r requirements.txt

python3 checker/preflight.py fixtures/broken_server.py   # catches a real bug
python3 checker/preflight.py fixtures/clean_server.py    # same server, fixed -> ALL CLEAR

# or side by side:
bash demo.sh
```

### Example output

```
Fourgate Preflight Report — fixtures/broken_server.py
============================================================
  ℹ [tools_list] Discovered 3 tool(s): ['add_numbers', 'get_greeting', 'divide']
  ✘ [stdout_cleanliness] Non-JSON output on stdout broke the JSON-RPC stream: 'DEBUG: adding 1 + 1'
  ✔ [tool_call:add_numbers:valid] Call completed normally.
  ...
------------------------------------------------------------
  8 passed, 2 failed, 0 warnings

  RESULT: NOT SAFE TO SHIP — fix the failures above first.
```

Fix the line (`print(...)` → `print(..., file=sys.stderr)`) and re-run: `8 passed, 0 failed, 0 warnings — ALL CLEAR.`

### Honest limitations (preflight)

- FastMCP already catches unhandled exceptions (e.g. division by zero) and returns a clean error on its own. Fourgate's malformed-input checks confirm this rather than discovering new crashes — stdout pollution is the real gap.
- Not a replacement for MCP Inspector or MCPTrust, which target teams already running production MCP fleets with CI gates. Fourgate is for someone shipping their first connector who wants a plain-language answer, fast.
- An earlier version of this tool uploaded fuzz results to Supabase. That path has been removed and the tables deleted after a security review found it wasn't safe as built; there is currently no remote upload path — everything runs and stays local.

---

## 2. Runtime wrap

A host-side stdio proxy that sits on the live `tools/call` path between an MCP host and server, and rewrites the response the model reads into a structured verdict: `{kind, tool, evidence, recovery}`.

**What's proven, today:**

- **Byte-identical passthrough** when there's nothing to flag — verified on-path: kill the wrap process and the call never completes, meaning it's genuinely in the loop, not a sidecar reading a copy.
- **Request/response correlation** with a **fail-open gate at 100ms** — if classification doesn't resolve in time, the original response passes through unmodified. A slow or broken wrap degrades to transparent, never to a hang.
- A **`silent_empty` classifier**, gated on a per-tool baseline. It only flags a result when it has a known-good shape to compare against; without a baseline it passes the result through untouched. Three deliberate false-positive cases (e.g. a legitimate "no results" text response) are tested and pass.
- **In-band verdict rewrite**, canary-tested for redaction — when the wrap does rewrite a response, a canary test confirms nothing sensitive leaks into the rewritten payload.
- **A self-check** (`--selfcheck`) that fails loudly if the wrap isn't actually on the call path — so a silent-failure detector can't itself silently no-op.

### Quickstart

> **Confirm before relying on this** — path/flags below are drafted from description, not yet verified against the pushed entrypoint.

```bash
python3 wrap/fourgate_wrap.py -- <your-mcp-server-launch-command>
```

**`--selfcheck`** — verifies the wrap is genuinely intercepting `tools/call`, not bypassed. Fails if it can't prove it's on-path.

**`--observe PATH`** — shape-only JSONL logging: counts, booleans, byte sizes. No argument or result values are written. Error responses are logged too, not just successes.

### What doesn't work yet

- **Baseline generation is not built.** Baselines exist only as two hand-written fixtures. On any real server you haven't hand-baselined, the wrap runs but has nothing to compare against — it passes every result through byte-identical, silently doing nothing. This is the current headline limitation.
- **`fake_success`, `auth_expiry`, and `token_bloat` are named in the design but not implemented.** Only `silent_empty` classifies anything today.
- **Tested on Windows only.** Behaviour on macOS/Linux is unverified, not merely untested-but-assumed-fine.
- **Claude Desktop `.dxt` extension builds reject this install path.** DXT packages launch the MCP server directly as a self-contained bundle; there's currently no supported way to insert the wrap into that launch command. This only works today for hosts where you control the server's launch invocation directly.
- **No alerting is built.** The structured verdict is available in-band and via `--observe`; there's no push/webhook path yet.

---

## Field evidence

24 real `tools/call` invocations across 4 live servers (filesystem, fetch, duckduckgo, heventure), logged and committed at [`specs/field-observations.md`](specs/field-observations.md).

**Result: zero `silent_empty` hits.** Every result carried non-empty content; errors came back as errors. One zero-result search returned "No matches found" as a text string — the false-positive gate correctly let it pass rather than flagging it.

**What actually failed, four times, all silently, all *before* any `tools/call`** happened: a server unreachable, an SDK import crash, a dependency install that broke a different server, and a config key in the wrong path so a server never loaded. In each case the agent reported the tool as unavailable and used something else instead. None of these are in scope for the current `silent_empty` classifier, which only runs once a call is made — this is a real gap the field data surfaced, not a hypothetical one.

**The open question driving the baseline work:** the one verified external report is from Prathmesh Patel (CEO @mcpjams, ex-Asana API/MCP lead) — an Atlassian MCP server returned `{issues: [], isLast: true}` for a nonexistent project, and the agent reported no issues and offered to create some. As written today, Fourgate would **not** flag this: it's a named empty collection, and the current classifier only acts where a baseline exists. This is the concrete case the unbuilt baseline-generation work is meant to close.

---

## Architecture (preflight)

```
your MCP server (subprocess, stdio)
        │
        ▼
Fourgate (raw JSON-RPC client)
        │  reads every line raw, before treating it as a message
        ▼
  initialize → tools/list → tools/call (valid / malformed / edge case)
        │
        ▼
  pass/fail report (human-readable or --json)
```

## Roadmap

- [ ] Baseline generation (the current blocker — everything else in the wrap is gated behind it)
- [ ] `fake_success`, `auth_expiry`, `token_bloat` classifiers
- [ ] Optional alert path out of `--observe`
- [ ] Verify on macOS/Linux
- [ ] Investigate a supported install path for Claude Desktop `.dxt` builds


## License

MIT — see [LICENSE](LICENSE).
