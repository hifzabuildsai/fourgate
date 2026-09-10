# Fourgate

**Open source · MCP preflight + runtime wrap**

Catch it
before the agent
does.


---

Fourgate

Experimental MCP preflight checks and deterministic runtime outcome guards.

Fourgate currently contains two working prototypes:

checker/preflight.py starts a Python MCP server over stdio, exercises raw
JSON-RPC initialization/list/call flows, detects non-JSON stdout pollution,
and makes a small set of generated valid, wrong-type, and numeric-edge calls.

wrap/wrap.py is an on-path stdio proxy. It correlates live tools/call
requests and results, fails open within a 100 ms classification budget, and
can place an attributed Fourgate verdict before the connector result.

This is pre-alpha evidence code, not a production gateway.

Outcome Guard demo

The new demo models an issue connector that returns a protocol-valid
Created ISSUE-… result without writing the issue to its system of record.
A hand-authored postcondition queries SQLite and produces a deterministic
outcome_failed verdict. A healthy write passes unchanged.

python3 demo_outcome.py

The contract and acceptance criteria are in
specs/outcome-guard-mvp.md.

Runtime wrap

python3 wrap/wrap.py --selfcheck

python3 wrap/wrap.py \
  --baseline path/to/contract.json \
  --server-label issue-tracker \
  -- your-mcp-server command args

Implemented runtime detections:

silent_empty: only total absence of interpretable payload, and only when a
hand-authored baseline requires content.

outcome_failed: only when an explicit local postcondition verifier returns
a deterministic failure or its declared result witness is absent.

What does not fire today:

A named empty collection such as {"issues": []}.

Explicit empty structuredContent such as [] or {}.

Text such as No matches found.

Shape regression, fake-success heuristics, auth-expiry classification, or
token-bloat classification.

Spawn, connection, discovery, environment, or configuration failures before
tools/call.

Baselines and postconditions are hand-authored. There is no baseline generator.
Verifier crashes, timeouts, non-zero exits, and malformed output fail open.

Preflight

python3 checker/preflight.py path/to/server.py

Preflight is currently Python-oriented, launches the target with the running
Python interpreter, uses legacy protocol version 2024-11-05, and pins
mcp==1.9.4. Its argument generation is intentionally small; it is not a full
JSON Schema fuzzer or a replacement for the official MCP Inspector or
conformance suite.

Field evidence

The current observation log contains 24 real tools/call results and zero
silent_empty detections. Four observed failures occurred earlier in the
lifecycle at spawn, connection, discovery, or configuration. The sample was
biased toward prose-returning tools and is not evidence that structured
false-success cases never happen. See
specs/field-observations.md.

Tests

python -m pip install -r requirements.txt
pytest -q

License

MIT — see LICENSE.
