# Phase D2: reference pack to local MCP — 2026-10-23

## Starting point and bounded gap

Rechecked [PR #52](https://github.com/hifzabuildsai/fourgate/pull/52): merged.
`git fetch origin main` resolved current remote main to
`67fe057554c05aa89907758cc1dc62c03ca0b892`, matching the last reported main only
after verification. The clean existing worktree
`C:\hifzazafar\fourgate\fourgate-pr-49` moved from D1 head `91450ff0` to branch
`codex/d2-reference-mcp-integration` at that verified main. Repository AGENTS.md
searches found no file; the existing repository skill/shared workflow and the
previously read engineering/code-work instructions continue to apply.

Inspected D1's contract, driver, stdio fixture and tests; C2 execution, state,
validation/replay helpers and tests; and the existing pytest CI job. D1 already
establishes induced wrong expectation/identity and ambiguous/unavailable
read-back semantics. C2 already establishes generic grants, replay and privacy.
The gap is their combination with the reviewed Issue pack and explicit GET
counts, not another implementation of those components or negative controls.

Change contract: one local integration test, a reproduction link in the pack
guide, and this evidence note. No product runtime, report schema, dependency,
fixture implementation or CI changes. Existing pytest collection finds the new
test. No D1 induced control was rerun for D2.

## Fresh integration fixtures and actual results

[`test_reference_pack_single_use_mcp_execution_and_restart`](../../tests/test_github_issue_mcp.py)
reuses the unchanged D1 `scan.example.json` and `stdio_fixture.py`, C2's command,
preparation/request/counting helpers, and the existing scripted stdio client.
An inline test-owned startup marker observes target **starts** as well as calls;
it runs the tracked D1 fixture, not an untracked local server dependency.

The locally configured template keeps the reviewed request-derived extraction
and equality maps. Only its synthetic request values, local command and
loopback HTTP transport are configured. The selected fictional Issue is seeded
closed with a different title/body. The registry and one-call policy bind the
actual copied contract's SHA-256; no pin is refreshed and state is prepared
once in the new pytest fixture. Prior grant/state paths are never input.

Each independently prepared integration fixture completed with these cumulative
observations (one initial run and one final run after a test-assertion repair):

| Step | Adapter tool calls | Target starts | Protected calls | Read-back GETs | Typed result |
| --- | --- | --- | --- | --- | --- |
| State preparation | 0 | 0 | 0 | 0 | Actions NOT_RUN; process exit 0 |
| validate_workflow | 1 | 0 | 0 | 0 | CONFIG_VALID / STATIC_CONFIG_ONLY / NOT_RUN |
| Fresh run_workflow | 2 | 1 | 1 | 1 | PASS; new_execution true |
| get_run_report | 3 | 1 | 1 | 1 | Saved PASS; new_execution false |
| Repeated run_workflow | 4 | 1 | 1 | 1 | Saved PASS; new_execution false |
| Restarted-client run_workflow | 5 | 1 | 1 | 1 | Saved PASS; new_execution false |
| Restarted-client get_run_report | 6 | 1 | 1 | 1 | Saved PASS; new_execution false |

Fresh execution returned `run_state: COMPLETED`, `action_status: ATTEMPTED`,
`reserved_tool_calls: 1`, `call_attempts: 1`, overall `verdict: PASS` and case
`PASS / postcondition_satisfied`. The local authority independently contains the
approved number/title/body/open state. `get_run_report` and cached run requests
retain the recorded ATTEMPTED status, but explicitly set `new_execution: false`:
that is historical execution, not a fresh write or fresh authoritative read.
Authority, target trace and SQLite bytes remain unchanged during retrieval and
replay. The contract fingerprint is unchanged after all requests.

Per fixture, the static-validation process and two execution/replay serving
processes all exited **0**; preparation also exited **0**. Process success alone is not
the PASS oracle: assertions inspect the typed verdict, case reason, authoritative
local state and observed call/GET counts after each response. Static validation
also leaves prepared state and initial authority unchanged.

The wire results have matching text/structuredContent, the existing structural
field allowlist and case shape, and the 16 KiB bound. Private request title/body,
credential sentinel, absolute fixture path, endpoint and raw tool-claim text do
not enter the MCP response. The saved SQLite report equals the fresh structural
payload. `d2-counts.json` is a **local test diagnostic**, not a new MCP report
field or runtime schema.

## Exact commands and counts across actual commands

Environment: existing Python **3.14.6**, pytest **9.1.1**, source Fourgate **0.3.0**.
No installation, upgrade, model request or client configuration edit.

```text
C:\Python314\python.exe -B -m pytest -q -s tests/test_github_issue_mcp.py --basetemp fourgate-output/d2-focused --tb=short
```

Exit **0**, **1 passed in 2.46 s**. Exactly one fresh integration fixture:
`fourgate-output/d2-focused/test_reference_pack_single_use0/`. Its `D2_COUNTS`
output and `d2-counts.json` record **1 target start, 1 protected update, 1 GET,
6 adapter tool calls** (validate 1, run 3, report 2), three serving exits 0 and
preparation exit 0. The registry, policy, authority, traces and consumed SQLite
state remain local/ignored. They are never committed or reused by another run.

Diff review found a Windows-specific weakness in the **new test assertion**:
a raw path substring is not necessarily present in its JSON-escaped wire form.
An in-memory synthetic-path reproduction demonstrated that the old comparison
missed the encoded value; no workflow was executed by that reproduction. The
privacy assertion now compares the JSON-encoded private sentinel. This was not
an observed runtime privacy leak or a failed protected action. Recheck after
the one-line assertion repair used a separate new fixture:

```text
C:\Python314\python.exe -B -m pytest -q -s tests/test_github_issue_mcp.py --basetemp fourgate-output/d2-final-privacy --tb=short
```

Exit **0**, **1 passed in 2.17 s**. Fresh fixture
`fourgate-output/d2-final-privacy/test_reference_pack_single_use0/`: **1 target
start, 1 protected update, 1 GET and 6 adapter calls**, with the same phase
counts as above. All 12 files from the first fixture, including its consumed
state, were hash-verified unchanged. These two runs exercise the same test;
they are not added together as distinct test coverage.

```text
C:\Python314\python.exe -B -m pytest -q tests/test_github_issue_reference.py::test_reference_expectations_come_from_the_reviewed_request tests/test_example_contracts.py --basetemp fourgate-output/d2-static-checks --tb=short
```

Exit **0**, **4 passed in 0.29 s**. These are static template checks: no grant,
target start/call, HTTP GET or MCP adapter call. D1's induced controls and C2's
generic execution/negative matrices were inspected, not repeated.

```text
C:\Python314\python.exe -B -m pytest --collect-only -q tests/test_github_issue_mcp.py
```

Exit **0**, **1 test collected in 0.31 s**; zero workflow execution. Normal
`python -m pytest -q` CI collection includes it without a new workflow/job.
Syntax parsing and Git whitespace checks also exited 0, without execution.

**Totals across these actual D2 check commands:** two separately isolated fresh
grants prepared and consumed, **2 target starts, 2 simulated protected updates,
2 loopback GETs and 12 adapter tool calls**. Static/collection checks and the
in-memory matcher demonstration add zero execution. The test counts above are separate invocation results,
not additional executions or a sum of overlapping test coverage. No standalone
D1 demo, induced control, external workflow or installed Codex session was run.

Normal-user permission was requested for the loopback integration because prior
D1 sandbox evidence already established environmental loopback uncertainty.
There was no failed D2 execution or write retry. All earlier sandbox failures,
acceptance artifacts and consumed grants remain preserved with their original
classifications; no old result is silently upgraded or replaced.

## Preservation and limitations

Before D2, hashes captured all **1,314** existing artifact files and persistent
client configuration in `fourgate-output/d2-preservation-before.json`. Only the
new test and two documentation files enter this slice. No execution database,
credential, generated contract, trace or acceptance artifact enters the commit.
Existing C2 state is never reset, repinned or reused. Git metadata changes are
limited to the authorized branch/commit/push; the original checkout is not edited.

This closes the **scripted local stdio** integration evidence gap only. The
modern per-request wire helper and restarted server/client are not an installed
Codex app-server, SDK-version or Desktop UI acceptance test. The fixture uses
generic loopback HTTP with GitHub-shaped data; live GitHub MCP schema mapping,
read identity/visibility, credential permissions, freshness and write causality
remain unverified. A cached PASS does not revisit current state. Existing D1/C2
limitations on same-host tampering, exactly-once claims, customer CI and production
reliability remain. Hosted CI, the wider protocol/OS matrix and packaging are
not inferred from these local results. No merge, release or deployment.
