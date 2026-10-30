# GitHub MCP reference compatibility — 2026-10-31

## Bounded gap

The D1 reference pack used a synthetic `update_issue` tool and selected the
read-back Issue from `result.structuredContent.number`. That fixture behavior
was useful local evidence, but it was not compatible with the current official
GitHub MCP Server.

The official GitHub MCP Server **v2.0.3**, released 2026-10-21, was inspected at
signed tag commit `b98d115bbb080e9555466a96656ec4df605aea21`:

- [`issue_write` schema and update dispatch](https://github.com/github/github-mcp-server/blob/b98d115bbb080e9555466a96656ec4df605aea21/pkg/github/issues.go)
- [`MinimalResponse` definition](https://github.com/github/github-mcp-server/blob/b98d115bbb080e9555466a96656ec4df605aea21/pkg/github/minimal_types.go)
- [v2.0.3 release](https://github.com/github/github-mcp-server/releases/tag/v2.0.3)

Observed upstream behavior: an update uses `issue_write` with
`method: "update"`; its success payload is a minimal object containing `id` and
`url`. It does not return authoritative Issue number, title, body or state.
This is upstream schema inspection, not a live GitHub execution.

## Change contract

The reference pack now uses `issue_write` and the explicit update method. The
human-reviewed request's owner/repository/Issue number selects the independent
GET. Expected number/title/body/state also come from that request. The tool's
minimal success object is not evidence that the requested state persisted.

No Fourgate runtime, verdict semantics, report schema, dependency, release
version or CI workflow changed. The server command remains unconfigured until
an operator reviews and pins an authorized local stdio server.

## Local results

The standalone reference simulation completed with one local protected update
and six loopback GETs:

| Control | Verdict | Reason |
| --- | --- | --- |
| Healthy | PASS | `postcondition_satisfied` |
| Wrong expectation | FAIL | `field_mismatch` |
| Wrong identity | FAIL | `field_mismatch` |
| Ambiguous 404 | UNKNOWN | `readback_unconfirmed` |
| Unavailable 503 | UNKNOWN | `readback_unconfirmed` |
| Missing observed identity | UNKNOWN | `readback_shape_invalid` |

The D2 local MCP integration then completed with one target start, one
protected update, one loopback GET and six adapter calls. Static validation
performed no action. Saved-report and restarted-client replay added no target
start, target call or GET. All three serving processes exited zero; the typed
PASS plus the authoritative read-back established the healthy outcome, not the
process exits alone.

The repository Python lacked pytest, so these focused test functions were
executed directly with fresh temporary paths: all five D1 reference checks and
the one D2 integration check completed. Python compilation, JSON parsing and
`git diff --check` also succeeded. Hosted pull-request CI remains the normal
pytest and platform-matrix authority for this change.

All target state and HTTP traffic in these checks were local fixtures. External
workflow requests were zero. Live v2.0.3 discovery, credential scope,
visibility, freshness, write causality, customer CI and production reliability
remain unverified. Induced controls are not natural findings, and UNKNOWN is
not PASS or proof of a server defect.
