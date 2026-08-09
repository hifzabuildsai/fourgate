# Fourgate

**Checks whether your MCP connector actually protects identity and fails closed — before a user finds out it doesn't.**

Fourgate is a preflight checker for [MCP](https://modelcontextprotocol.io) connectors. It spawns your server, talks real JSON-RPC to it over stdio, and catches the failure modes that break agent connections silently — before you ship.

Built for developers shipping their **first** MCP connector, not enterprise platform teams. No CI lockfiles, no SIEM integration — just a clear answer to "why did my connector break," in plain language.

## Why this exists

Every MCP connector runs on a strict protocol: any stray non-JSON output on stdout breaks the connection, silently. It's a one-line mistake — a leftover `print()` statement — and the failure is invisible until an agent hits it in the wild.

Fourgate catches it before that happens.

## Quickstart

```bash
git clone https://github.com/hifzabuildsai/fourgate.git
cd fourgate
pip install -r requirements.txt

python3 checker/preflight.py fixtures/broken_server.py   # catches a real bug
python3 checker/preflight.py fixtures/clean_server.py    # same server, fixed -> ALL CLEAR

# or watch both side by side:
bash demo.sh
```

## What it actually catches, today

Fourgate spawns your MCP server as a real subprocess and speaks JSON-RPC to it directly — not through a client library that would just crash on the same bug it's supposed to catch.

- **Stdout cleanliness** — any non-JSON line on stdout breaks the JSON-RPC stream. Fourgate reads raw and reports the exact offending line. *(This is the real, confirmed failure mode — the #1 cause of silent MCP connector breakage.)*
- **Schema robustness** — for every declared tool, Fourgate sends a valid call, a deliberately wrong-typed call, and a numeric edge case (e.g. division by zero), and checks whether the server fails closed with a clean JSON-RPC error, or fails open with a crash, a hang, or silently-coerced bad data.

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

Fix the one line (`print(...)` → `print(..., file=sys.stderr)`) and re-run:

```
Fourgate Preflight Report — fixtures/clean_server.py
============================================================
  ...
------------------------------------------------------------
  8 passed, 0 failed, 0 warnings

  RESULT: ALL CLEAR.
```

## Honest limitations

- **FastMCP already catches unhandled exceptions** (e.g. division by zero) and returns a clean error result on its own. Fourgate's malformed-input and edge-case checks confirm this rather than "discovering" new crashes — the framework already guards against it. Stdout pollution is the real, narrow gap: something the framework does **not** protect you from.
- **Not a replacement for MCP Inspector or MCPTrust.** Those tools are built for teams already running production MCP fleets, with CI gates and lockfiles. Fourgate is for someone shipping their first connector who needs a plain-language answer, fast.
- **No interviews confirming willingness to pay, yet.** This is a working prototype validating a hypothesis, not a proven product.

## Roadmap

- [ ] Identity check: is user identity read from a verified token, or leaking through a tool argument? (the trust bug named explicitly in the Connector-Native Apps curriculum)
- [ ] Fail-closed check: does the server degrade honestly when a dependency is down, or does it improvise?
- [ ] Simple web UI: paste code, get the same report, no local install
- [ ] Run against real student connectors from the GIAIC Marathon and publish what it actually catches

## Architecture

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

## License

MIT — see [LICENSE](LICENSE).
