# Fourgate

**Open source · MCP preflight + runtime wrap**

Catch it
before the agent
does.

Two tools, one repo:

1. **Preflight** (`checker/`) — a CLI that spawns your MCP server and talks real JSON-RPC to it over stdio, fuzzing it before you ship.
2. **Runtime wrap** (`wrap/`) — a stdio proxy that sits inline on an already-running MCP server's live `tools/call` path, classifies one specific failure shape (`silent_empty`), and rewrites the model-visible result to `{kind, tool, evidence, recovery}` when it matches.

They're independent. You can use either one without the other.

---

## 1. Preflight CLI

Spawns your MCP server as a subprocess, talks real JSON-RPC to it over stdio, and catches the failure modes that break agent connections silently — before you ship.

### Quickstart

```bash
git clone https://github.com/hifzabuildsai/fourgate.git
cd fourgate
pip install -r requirements.txt

python3 checker/preflight.py fixtures/broken_server.py
python3 checker/preflight.py fixtures/clean_server.py

# or watch both side by side:
bash demo.sh
```

### ⚠️ Important: pinned dependency

`requirements.txt` pins `mcp==1.9.4` on purpose. The official MCP SDK shipped a
breaking **2.0.0** release that renames `FastMCP` to `MCPServer` and moves it
to a different module path — a fresh unpinned install silently breaks the
fixture servers. If you're building your own connector against the newer SDK,
that's fine; just know the pin here is intentional, not an oversight.

### What it actually catches, today

- **Stdout cleanliness** — any non-JSON line on stdout breaks the JSON-RPC stream. Fourgate reports the exact offending line. This is the real, confirmed failure mode — the #1 cause of silent MCP connector breakage.
- **Schema robustness** — a valid call, a wrong-typed call, and a numeric edge case (e.g. division by zero) against every declared tool, checking whether the server fails closed or fails open.

**v0 limitation, stated plainly:** the checker spawns servers as Python scripts (`sys.executable <path>`). It only works on **Python** MCP servers right now — not Node.js/TypeScript ones. That's the next thing to build, not something already covered.

### Honest limitations

- FastMCP already catches most unhandled exceptions and returns a clean error result on its own. Fourgate's malformed/edge-case checks confirm this rather than "discovering" new crashes — stdout pollution is the real, narrow gap the framework doesn't already close.
- Python-only, as above.
- No confirmed-by-users evidence yet that this saves real time.

### Roadmap

- [ ] TypeScript/Node.js connector support
- [ ] Identity check: is user identity read from a verified token, or leaking through a tool argument?
- [ ] Fail-closed check: does the server degrade honestly when a dependency is down?
- [ ] Simple web UI: paste code, get the same report, no local install

---

## 2. Runtime wrap

`wrap/wrap.py` spawns your already-configured MCP server as a child process and proxies stdio bytes between it and the real client, unchanged, in both directions (`FR-1`). Alongside that forwarding, it tracks which `tools/call` request a later response belongs to, and runs every resolved `tools/call` **result** through a bounded classifier.

Right now that classifier implements exactly one kind — `silent_empty` — and only its narrowest case: a successful terminal result with no interpretable payload at all (no non-empty text, no non-text content item, no `structuredContent`), for a tool whose baseline declares that its successful responses contain payload. When that fires, the line the client receives is rewritten so the model sees a verdict instead of the original (empty) result:

```json
{"kind": "silent_empty", "tool": "myserver/fetch_document", "evidence": {"content_present": false, "content_item_count": 0, "structured_content_present": false}, "recovery": "stop"}
```

delivered in-band, attributed with a `[FOURGATE]` marker so the agent doesn't mistake it for something the tool itself said. Every other result — including a well-formed zero-result payload like `{"results": [], "count": 0}`, or any tool with no matching baseline entry — passes through byte-identical, with no verdict, annotation, or log entry.

The wrap has no dependencies beyond the Python standard library — nothing in `requirements.txt` is needed to run it.

### Install

There's no separate install step — it's the same clone as above. Wrapping a server means editing that server's existing `command`/`args` block in your MCP client's config so the client launches `wrap/wrap.py` (which then execs your original command as a child process, after a standalone `--`) instead of launching your server directly. This is the same `command`+`args` stdio shape Claude Code and Cursor both use for local MCP servers, so the edit looks the same in either client's config file.

Before:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python3",
      "args": ["server.py"]
    }
  }
}
```

After — only this block changes; `my-server`'s own source, credentials, tool names, schemas, and descriptions are untouched:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python3",
      "args": [
        "/absolute/path/to/fourgate/wrap/wrap.py",
        "--baseline", "/absolute/path/to/my-server-baseline.json",
        "--server-label", "my-server",
        "--",
        "python3", "server.py"
      ]
    }
  }
}
```

Restart the client. Every `tools/call` result for `my-server` now traverses `wrap.py` before the model sees it.

### Flags

- **`--selfcheck`** — `python3 wrap/wrap.py --selfcheck`, no target command needed. Spawns a *separate* `wrap.py` subprocess wrapping the repo's own bundled fixture server (`fixtures/silent_server.py`) with a bundled baseline, speaks real JSON-RPC to it over real stdio, and prints back the verdict it reads from that subprocess's stdout — the same bytes a real client would receive. This proves the intercept-and-rewrite path is wired correctly in your environment. **It does not check your own server or your own client config** — there's no way yet to point `--selfcheck` at a specific wrapped server.
- **`--observe PATH`** — permanent, off-by-default observation log. Appends one JSON line per resolved `tools/call` result: server label, tool name, `isError`, whether it was a JSON-RPC protocol-level error rather than a tool result, content-block count, whether any content text was non-empty, whether `structuredContent` was present, payload size in bytes, and whether `silent_empty` would have fired against the loaded baseline. Never records a field value, tool argument, or user content — only counts, booleans, and byte lengths. It's a side channel: the client-visible bytes are always written first, so a slow or failing `--observe` write can never delay or change what the model sees.
- **`--server-label LABEL`** — qualifies the `tool` field of every verdict as `LABEL/tool_name`. Defaults to `server` if omitted. Set a distinct label per wrapped server when wrapping more than one, or two servers exposing an identically named tool will produce indistinguishable verdicts.
- **`--baseline PATH`** — the JSON file declaring which tools' successful responses are expected to carry payload. With no `--baseline` (or a path that fails to load), the wrap still runs and still forwards everything — it just never has grounds to emit `silent_empty`, since there's no declared contract to check the result against.

### Fail-open behaviour

Classification runs on a background thread under a 100ms wall-clock budget (`FR-2`). If it raises an exception, times out, or the result can't be parsed as JSON, `wrap.py` forwards the original bytes unchanged — no partial rewrite, nothing dropped. Any line that isn't a `tools/call` response (the tool list, notifications, `initialize`, everything else) is forwarded byte-for-byte with no parsing gate on it at all, so a healthy session stays byte-identical to running the server unwrapped. If `wrap.py` can't start the wrapped command, it prints an error to stderr and exits non-zero rather than presenting a silently healthy, zero-tool server.

### What does NOT work yet

- **No baseline generation.** Baselines are hand-written JSON (see `tests/fixtures/*_baseline.json` for the current format). `silent_empty` cannot fire for any tool without a hand-authored baseline entry that declares `content` as a required field — nothing yet derives a baseline from preflight output or from watching real traffic.
- **`fake_success`, `auth_expiry`, `token_bloat` are unbuilt.** Only `silent_empty` is implemented, and only its narrowest case — total absence of payload. Shape regression (a non-empty-looking collection missing a baseline-required companion field) is specced but not implemented either.
- **Windows-tested; Claude Desktop's DXT install path is not supported.** Development and testing so far have been on Windows, against the `command`+`args` stdio config shape Claude Code and Cursor both use. The wrap has not been packaged or tested as a Claude Desktop extension (`.dxt`).

See [specs/runtime-wrap.md](specs/runtime-wrap.md) for the full behavioural spec this slice implements against, and [plan.md](plan.md) for what was deliberately left out of this first slice and why.

---

## What we've actually watched it do

24 real `tools/call` results have been observed passing through the wrap, across two sessions and four wrapped MCP servers (`filesystem`, `fetch`, `duckduckgo`, `heventure`). **Zero of them were `silent_empty`** — every result observed carried interpretable content, successes and descriptive errors alike, including a legitimate zero-match search that returned a well-formed "no matches found" payload rather than an absent one.

The same sessions also surfaced four real failures — a network-unreachable server, an SDK import crash, an install that broke the shared MCP environment, and a config key mismatch — none of which happened at the `tools/call` layer the wrap classifies. They occurred at spawn, connect, or discovery time, before any `tools/call` result existed to classify, which means they were invisible both to the agent and to the wrap.

Full detail in [specs/field-observations.md](specs/field-observations.md). It's an observation record, not a test suite or a correctness claim — read it as exactly that.

---

## Architecture

**Preflight:**

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
  local report (human-readable or --json)
```

**Runtime wrap:**

```
MCP client (Claude Code / Cursor, stdio)
        │
        ▼
wrap/wrap.py  ── spawned in place of your server's own command
        │  pumps raw bytes both ways; parses a copy for id/tool tracking only
        ▼
your MCP server (unmodified, spawned as a child, stdio)
```

Every `tools/call` response is gated through the classifier (bounded to 100ms) against an optional baseline; a match rewrites the line before it's written back to the client. Everything else — the tool list, all non-`tools/call` traffic, and any result that doesn't match — is forwarded byte-identical.

## License

MIT — see [LICENSE](LICENSE).
