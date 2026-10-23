# Phase A protocol repair and Codex setup preparation — 23 October 2026

This is local engineering evidence, not customer validation or a natural
silent-success finding. Product version remains 0.3.0; the changes described
here are source changes awaiting review, not a published PyPI release.

## Workspace and baseline

- Execution: Linux x86_64, Python 3.12.14. The supplied Windows checkout
  `C:\hifzazafar\fourgate\fourgate` is not mounted here. No Windows Desktop
  client session was inspected or modified.
- Fresh main checked before work and again before PR preparation:
  `a0e7c0dbd7e9c2217212486e4cd2b3df1f7d238e`.
  [Main CI 39700722507](https://github.com/hifzabuildsai/fourgate/actions/runs/39700722507)
  was independently re-read as completed/success for that exact commit.
- Existing clean checkout/branch at `43d9b44b127b4773f6f1c841cc2085512bb343fd`
  preserved. New worktree: `fourgate-phase-a-20261023`, branch
  `codex/phase-a-current-mcp`, based on the fresh main above.
- No AGENTS.md or CLAUDE.md repository instructions were found. Existing
  HANDOFF.md, scan specification, client skill and CI configuration inspected.
- Existing isolated dev environment: pytest 9.1.1, mcp 1.9.4, Pydantic 2.13.5,
  build 1.6.1. No Codex/Claude executable available here. No runtime dependency
  or SDK upgrade was introduced.

## Reproduction and bounded change contract

Before production edits, the new local fixture suite produced **3 passed,
9 failed**. The explicit modern scan configuration was rejected before startup;
doctor had no modern protocol option. A separate direct StdioClient diagnostic
showed native mode failing after `initialize`, while legacy and compatibility
fixtures answered legacy discovery. This establishes a compatibility blocker,
not a failure of every MCP server or an external missing write.

Repair: preserve explicit legacy/default behavior; add explicitly selected
2026-07-28 scanner/doctor discovery and request metadata; reject incomplete,
unknown or missing modern completion types before verification; stop further
writes without automatic tools/call retry. Reuse existing deterministic
verifiers. Do not modify the runtime proxy, shadow/enforce semantics or budgets.

Scope is an explicit protocol subset, not automatic dual-era negotiation:

| Selected mode | Observed local request sequence |
| --- | --- |
| Legacy 2024-11-05 / 2025-11-25 | initialize → notifications/initialized → tools/list → contracted tools/call |
| Native 2026-07-28 | server/discover → tools/list → contracted tools/call |
| Compatibility fixture, legacy selected | Legacy lifecycle |
| Compatibility fixture, modern selected | Modern lifecycle; no initialize |
| Modern discovery/version/type blocker | No tools/call and no legacy downgrade |
| Doctor, modern selected | server/discover → tools/list; zero tools/call/verifier runs |

The modern requests carry protocol version, empty client capabilities and client
info in params._meta. The single supported modern version must be advertised.
Multi-round input completion, automatic version downgrade, remote transport and
runtime guard modern-lifecycle acceptance are outside this change. Stdio close
now gives EOF a bounded opportunity before terminate/kill fallback.

## Verdict controls — all simulated or induced

| Control | Observed result |
| --- | --- |
| Healthy local persistence, all five era/version combinations | PASS / postcondition_satisfied, scan exit 0 |
| Induced missing persistence | FAIL / record_missing, scan exit 1 |
| Induced input_required | UNKNOWN / incomplete_tool_result, exit 1; no verifier/next write |
| Induced unfamiliar resultType | UNKNOWN / unsupported_result_type, exit 1; no verifier/next write |
| Induced missing modern resultType after a persisted write | UNKNOWN / missing_result_type, exit 1; no verifier/next write |
| Induced discovery input/missing type, unsupported version or missing selected version | UNKNOWN at discovery, no tools/call |
| Native server with default legacy doctor | NOT READY, no tools/call |
| Native/compatibility server with modern doctor | READY FOR SHADOW, no action verdict |

A marker verifier proves it is not executed for incomplete/invalid completion
results. Request traces distinguish separate approved cases from retries.
Modern absence of resultType is rejected; legacy absence still means complete.
UNKNOWN does not prove whether an action persisted. The local missing-type
control deliberately persists a record and still stops as UNKNOWN.

## Commands and actual results

Commands ran from the new worktree using the isolated dev interpreter. `PATH`
placed its bin directory first for console-command tests.

```text
python -m pytest -q tests/test_protocol_compatibility.py --tb=short
  BEFORE production repair: 3 passed, 9 failed
python -m pytest -q tests/test_protocol_compatibility.py tests/test_scan.py tests/test_cli_doctor.py
  intermediate repair: 65 passed, 1 skipped
  after first review corrections: 69 passed, 1 skipped
python -m pytest -q tests/test_protocol_compatibility.py
  final independent review: 18 passed
PATH=<dev-venv>/bin:$PATH python -m pytest -q
  final full suite: 448 passed, 9 skipped, 69.13 seconds
python demo_outcome.py
  exit 0; simulated failure/healthy/shadow behavior accepted
python wrap/wrap.py --selfcheck
  exit 0; selfcheck OK
python -m build --no-isolation
  exit 1; existing dev venv lacked setuptools (environment prerequisite)
python -m build
  exit 0; isolated build produced wheel and sdist
python <skill-creator>/scripts/quick_validate.py <each client skill directory>
  exit 0 for both; Skill is valid!
git diff --check
  exit 0
```

An earlier full run without the dev bin on PATH reported 439 passed/12 skipped;
the final run above enabled the installed-console checks. Existing skipped tests
are not passed tests. The dev console installation predates this source change,
so the new CLI was also checked from a freshly built wheel below.

Wheel installed with `pip install --no-index --no-deps <built-wheel>` into a
fresh venv outside the checkout. Module location confirmed inside site-packages;
no source-tree import/PYTHONPATH. Version/help/product demo succeeded. Actual
installed console scans returned legacy PASS/0, native PASS/0, compatibility
modern PASS/0 and induced input-required UNKNOWN/1. Installed modern doctor
returned readiness and its trace contained discovery/list only. Raw local smoke
commands/results: `fourgate-output/phase-a/wheel-smoke.json` (ignored operator
artifact, not a published customer report). Repository CI results for the PR
must be checked separately on its exact head.

One independent agent reviewed production code and fixtures. It found missing
modern resultType acceptance and omitted required fixture cache fields. Both
were corrected; the follow-up review reported no remaining material issue in
this bounded scope. This is one reviewer with a follow-up, not multiple reviews.

## Codex onboarding preparation and remaining gates

Codex and Claude now have thin entries referencing one shared workflow and
command guide. Official Codex documentation establishes repository
`.agents/skills` and the documented MCP config mechanism. Both skill files
passed frontmatter validation; 14 relative document links resolved and the
illustrative TOML parsed. No real client config was installed.

A fresh-context instruction exercise used the Codex skill, inspected the bundled
create_issue schema, prepared isolated custom-verifier contract copies and ran
doctor. It reported exit 0, READY FOR SHADOW with one custom-verifier inspection
warning. Store and outcome log remained absent; no scan, verifier or protected
action ran. It correctly rejected inventing an HTTP endpoint to make the
file-based fixture fit init; the shared workflow now makes that limit explicit.
This tests instruction use in this execution environment, not discovery or
activation inside the founder's installed Codex Desktop.

| Next gate | Status |
| --- | --- |
| Actual Windows Codex version, skill discovery and explicit activation | NOT RUN here; needs the founder's existing Desktop checkout |
| Fresh-thread ordinary-language activation | NOT RUN |
| Desktop no-write configuration/doctor acceptance | NOT RUN in Desktop; local instruction exercise only |
| Authorized Desktop simulation/shadow and repeat use | NOT RUN |
| Customer workflow/CI and production reliability | Unvalidated |
| New local Fourgate MCP interface / reference pack / release candidate | Not implemented in this slice; proceed in dependency order |

No external workflow credentials were used or requested. No live issue was
created, no customer target was scanned and no merge/release/deployment occurred.
The next concrete step is the [Codex no-write acceptance](../codex-setup.md),
using the reviewed source revision; external action approval is separate.

## Primary specification references

Checked 23 October 2026. Fixture schema subset pinned to specification repository
commit `80041ab0a139a8f4fb3adbc99f7ae9113ea59671`, including Result,
RequestMetaObject, DiscoverResult and ListToolsResult/CacheableResult.

- [Pinned MCP schema](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/80041ab0a139a8f4fb3adbc99f7ae9113ea59671/schema/2026-07-28/schema.ts)
- [2026-07-28 stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
- [2026-07-28 versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
- [2026-07-28 result and metadata rules](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)
- [Legacy lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex MCP config](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
