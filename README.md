# Fourgate

**Open source · MCP preflight**

## Catch it
## before the agent
## does.

**Checks whether your MCP connector actually protects identity and fails closed — before a user finds out it doesn't.**

Fourgate is a preflight checker for [MCP](https://modelcontextprotocol.io) connectors. It spawns your server, talks real JSON-RPC to it over stdio, and catches the failure modes that break agent connections silently — before you ship.

Every run — yours or a student's — syncs to a shared log, so the checker gets sharper as more real connectors get checked, instead of every result disappearing when the terminal closes.

## Quickstart

```bash
git clone https://github.com/hifzabuildsai/fourgate.git
cd fourgate
pip install -r requirements.txt

python3 checker/preflight.py fixtures/broken_server.py --checked-by "your name"
python3 checker/preflight.py fixtures/clean_server.py --checked-by "your name"

# or watch both side by side:
bash demo.sh
```

Add `--no-upload` to any run to skip syncing (e.g. while testing offline).

## ⚠️ Important: pinned dependency

`requirements.txt` pins `mcp==1.9.4` on purpose. The official MCP SDK shipped a
breaking **2.0.0** release that renames `FastMCP` to `MCPServer` and moves it
to a different module path — a fresh unpinned install silently breaks the
fixture servers. If you're building your own connector against the newer SDK,
that's fine; just know the pin here is intentional, not an oversight.

## What it actually catches, today

- **Stdout cleanliness** — any non-JSON line on stdout breaks the JSON-RPC stream. Fourgate reports the exact offending line. This is the real, confirmed failure mode — the #1 cause of silent MCP connector breakage.
- **Schema robustness** — a valid call, a wrong-typed call, and a numeric edge case (e.g. division by zero) against every declared tool, checking whether the server fails closed or fails open.

**v0 limitation, stated plainly:** the checker spawns servers as Python scripts (`sys.executable <path>`). It only works on **Python** MCP servers right now — not Node.js/TypeScript ones. That's the next thing to build, not something already covered.

## Where the data goes

Every run posts to a shared Supabase project — two tables, the same
two-table pattern taught in the Connector-Native Apps course:

- `runs` — one row per check: connector name, who ran it, pass/fail counts, overall result
- `findings` — one row per individual finding, linked to its run

This is what turns "I ran this once on my own fixture" into an actual growing
record of real MCP failure patterns across everyone who runs it.

**v0 posture:** the shared log currently accepts open inserts (no auth system
yet) — fine for a small, trusted marathon cohort this week, not meant to
stay this way if this goes wider. Tighten before broader use.

## Honest limitations

- FastMCP already catches most unhandled exceptions and returns a clean error result on its own. Fourgate's malformed/edge-case checks confirm this rather than "discovering" new crashes — stdout pollution is the real, narrow gap the framework doesn't already close.
- Python-only, as above.
- No confirmed-by-users evidence yet that this saves real time — that's what this week is for.

## Roadmap

- [ ] TypeScript/Node.js connector support
- [ ] Identity check: is user identity read from a verified token, or leaking through a tool argument?
- [ ] Fail-closed check: does the server degrade honestly when a dependency is down?
- [ ] Simple web UI: paste code, get the same report, no local install
- [ ] Query the shared log for the most common real failure pattern across everyone who's run it

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
        ├──► local report (human-readable or --json)
        └──► shared Supabase log (runs + findings)
```

## License

MIT — see [LICENSE](LICENSE).
