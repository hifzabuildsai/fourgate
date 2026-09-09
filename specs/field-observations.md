# Field Observations — Runtime Wrap, 2026-09-09

Status: observation record only. **Not a spec change, not a classifier change.**
This document records what was actually seen on one live session; it does not
add, modify, or reinterpret any FR in [runtime-wrap.md](runtime-wrap.md).

---

## What this is

8 real `tools/call` results were observed passing through the runtime wrap
during ordinary use of two wrapped MCP servers (`filesystem`, `fetch`) in one
working session. The observations below are a factual record of those 8
results, kept for reference against FR-8 (silent_empty scoping) and FR-15
(redacted evidence) as the classifier is built out.

---

## Observed calls

| # | Server | Tool | Outcome | Content empty/missing? | Notes |
|---|---|---|---|---|---|
| 1 | filesystem | `list_allowed_directories` | success | No | Directory listing text |
| 2 | filesystem | `list_directory` | success | No | File listing text |
| 3 | filesystem | `read_text_file` | error (`isError: true`) | No | Descriptive "Access denied — path outside allowed directories" message |
| 4 | filesystem | `directory_tree` | success | No | JSON tree text |
| 5 | filesystem | `search_files` | success, zero matches | No | Text content `"No matches found"` — a well-formed zero-result payload, not an absent one |
| 6 | fetch | `fetch` (example.com) | success | No | Page content returned as text |
| 7 | fetch | `fetch` (404 URL) | error (`isError: true`) | No | Descriptive "Failed to fetch ... status code 404" message |
| 8 | filesystem | `list_directory` (nonexistent path) | error (`isError: true`) | No | Descriptive ENOENT message |

---

## Observations

**Zero results had empty or missing content.** All 8 observed results carried
a non-empty `content` array with non-empty text — successes and errors alike.
No result reached the model with an absent or empty payload.

**The zero-result search (#5) returned text, not absence.** `search_files`
against a pattern with no matches returned the literal text `"No matches
found"` as its content — a legitimate, well-formed zero-result payload. Under
FR-8, this is exactly the case that must pass through unflagged: there is
interpretable payload (the "no matches" text itself), so no baseline is even
needed to reach the correct pass-through outcome here.

**All errors carried `isError` plus a descriptive message.** #3, #7, and #8
each set `isError: true` and paired it with specific, human-readable text
naming the actual failure (permission denial, HTTP status, ENOENT). None of
these were a silent or empty error shape.

**silent_empty did not occur in any observed call.** Across all 8 results —
4 plain successes, 1 zero-result success, 3 errors — none exhibited a
successful terminal result with no interpretable payload. There is nothing in
this observation set for a `silent_empty` verdict to have matched against.

**One tool description contained an embedded prompt-injection string.**
Unrelated to any `tools/call` result: the `fetch` tool's own description text
(returned at tool-discovery time, not as a call result) included a line
addressed directly at the model claiming it previously lacked internet access
and was now being granted it. This was identified as an injection attempt and
not acted on. It is noted here because it's a real example of untrusted text
arriving through an MCP surface other than a `tools/call` result — out of
scope for the wrap's result-classification path (FR-6–FR-12), but relevant
context for anyone reasoning about the wrap's trust boundary.

---

## Non-conclusions

This is a record of 8 calls in one session, not a test suite and not
evidence of correctness at scale. It does not exercise `fake_success`,
`auth_expiry`, or `token_bloat`, and it says nothing about baselined
`silent_empty` behavior — every tool observed here either had no baseline
in play or returned genuine content. No conclusions beyond what's stated
above should be drawn from it.
