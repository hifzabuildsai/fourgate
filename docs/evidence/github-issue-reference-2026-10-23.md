# Phase D1: GitHub Issue reference pack — 2026-10-23

## Verified starting point and change contract

GitHub PR metadata confirmed [PR #51](https://github.com/hifzabuildsai/fourgate/pull/51)
merged, with final reviewed head `9db92a085b46bc68c96f9cb001f933b6d2c96596`.
`git fetch origin main` resolved remote main to
`56f1051031103ded1396f4b1305d613d68ff7daf`; it was not inferred from the PR head.
The existing clean, detached worktree at
`C:\hifzazafar\fourgate\fourgate-pr-49` moved from `b2bfaaa3` to new local branch
`codex/d1-github-issue-reference` at that verified main. No new checkout was
created. Applicable ancestor/repository AGENTS.md searches found no file.
The Fourgate engineering and code-work skills were selected manually.

Scope: one preselected GitHub Issue update, with number/title/body/state
expected from a human-reviewed request and the repository pinned in read-back
configuration. Reuse the existing scanner, deterministic HTTP engine and local
JSON/HTML reports. Demonstrate matching local authority and induced wrong
expectation/identity and unavailable/ambiguous evidence. No product-runtime,
report-schema, version, remote MCP or client-configuration change.

Inspection covered the existing GitHub create/title template,
`fourgate.readback`, `fourgate.verify_http`, scanner/report code, local fixtures,
identity/404 tests and manual CI example. The predicates and verdict semantics
already existed. The missing slice was a reusable request/identity review card,
an update template and a local acceptance pack. Updating a preselected Issue
makes approved record identity explicit without implying fresh-create causality.

## Changes and acceptance mapping

- [Reference contract](../../examples/github-issue/scan.example.json): returned
  number is only the lookup locator; response number equals approved request
  issue_number, and title/body/state equal approved request arguments. The fixed
  repository must match the reviewed owner/repo. 404 remains ambiguous.
- [Review card and limits](../../examples/github-issue/review-card.example.md)
  and [pack guide](../../examples/github-issue/README.md): unconfigured logical
  tool/schema, exact fields, separate credentials, visibility, freshness and
  causality limits; no claim of live schema compatibility or execution approval.
- [Local driver](../../examples/github-issue/run_local.py) and synthetic stdio
  fixture: one bounded local update with real scanner/HTTP read-back, then five
  read-only controls. New output directories are mandatory; old evidence is
  refused, not replaced. No C2 grant or execution database is involved.
- [Acceptance tests](../../tests/test_github_issue_reference.py): load the actual
  template; prove request-derived expectations despite a conflicting tool claim;
  exercise the specialized GitHub URL builder with an intercepted transport;
  reject wrong/missing identity; inspect real local reports and call counts;
  verify an existing output directory cannot be reused.

No new runtime metadata or case-reference schema was justified: one case per
reviewed contract plus reference directories and contract hashes identify the
pack's evidence. Read-only control reports use the existing renderer, but omit
scan/write retry instructions. Their manifest records `NOT_RUN` for action
execution and null process exits; read-back FAIL/UNKNOWN are still distinct.
The existing full-suite CI job automatically collects the new tests; no new
workflow permissions or live CI run were introduced.

## Fresh local results

Python **3.14.6**, existing pytest **9.1.1**, source Fourgate **0.3.0**. No
installation, dependency upgrade, model call or release bump.

The successful standalone command was:

```text
C:\Python314\python.exe -B examples/github-issue/run_local.py --out fourgate-output/d1-github-issue-final
```

Exit **0**, `expectations_met: true`. Actual observations:

| Simulation / induced read-only control | Verdict | Reason |
| --- | --- | --- |
| Healthy approved local Issue update | PASS | postcondition_satisfied |
| Induced wrong expected title | FAIL | field_mismatch |
| Induced wrong expected Issue number, matching title | FAIL | field_mismatch |
| Ambiguous GET 404 | UNKNOWN | readback_unconfirmed |
| Unavailable GET 503 | UNKNOWN | readback_unconfirmed |
| 200 body missing required identity | UNKNOWN | readback_shape_invalid |

The standalone trace records **one** protected local target call and **six**
loopback GETs. Controls do not repeat the write, and the authority bytes are
unchanged by them. The tool deliberately claims a different saved title;
matching state passes only because the predicates use the approved request.
Zero external workflow-target requests/writes. Source/PR metadata fetches are
separate from workflow execution.

The healthy scan's subprocess exit was 0 with typed PASS. The read-only controls
call `readback.evaluate_extracted` directly: their process exit is null, not
invented scanner exits 0/1. The demo driver's exit 0 means its **expected mixed
outcomes** were observed, not that every case passed. Readiness/NOT_RUN are not
action PASS, and UNKNOWN is never treated as a confirmed defect.

Local artifacts are under `fourgate-output/d1-github-issue-final/`:
`acceptance.json`, approved request, contract, authority, target request/response
traces, scanner command/exit, and six JSON/HTML report directories. Those private
artifacts are not committed; the reference pack reproduces them with a fresh
output path. Generated JSON/HTML remains subject to best-effort redaction and
local review before sharing.

## Commands, failures and proportionate verification

All commands ran from the stated existing worktree. Git commands used the
command-scoped `-c safe.directory=C:/hifzazafar/fourgate/fourgate-pr-49` ownership
exception; no global Git configuration was changed.

| Command | Observed result |
| --- | --- |
| `git fetch origin main` | exit 0; origin/main `56f1051031103ded1396f4b1305d613d68ff7daf` |
| `git switch -c codex/d1-github-issue-reference 56f1051031103ded1396f4b1305d613d68ff7daf` | exit 0; same worktree |
| `C:\Python314\python.exe -B -m pytest -q tests/test_github_issue_reference.py --basetemp fourgate-output/d1-red --tb=short` | exit 1; 5 expected failures because pack/config did not yet exist |
| `C:\Python314\python.exe -B -m pytest -q tests/test_github_issue_reference.py --basetemp fourgate-output/d1-green --tb=short` | exit 0; 5 passed after implementation |
| `C:\Python314\python.exe -B -m pytest -q tests/test_github_issue_reference.py tests/test_example_contracts.py tests/test_readback.py tests/test_verify_http.py tests/test_report.py --basetemp fourgate-output/d1-affected --tb=short` | exit 0; 49 passed, including final control-report assertions |
| `C:\Python314\python.exe -B -m pytest -q tests/test_github_issue_reference.py tests/test_scan.py tests/test_readback_auth.py --basetemp fourgate-output/d1-scan-regression --tb=short` | exit 0; 64 passed; overlaps the five pack tests above |
| `C:\Python314\python.exe -B -m pytest -q tests/test_github_issue_reference.py --basetemp fourgate-output/d1-final-focused --tb=short` | exit 0; final 5 passed after making the preexisting Issue seed explicit |

The first sandboxed pytest attempt had four missing-pack failures plus a default
temp-directory permission error. The explicit local basetemp/normal-user red
run then established all five intended missing-pack failures. No dependency
installation was used to resolve the environment restriction.

A separate **sandboxed** standalone run at
`fourgate-output/d1-github-issue-2026-10-23/` exited 1 after one local write and
`UNKNOWN / readback_error` on loopback read-back (scanner exit 1). This is retained
as environmental uncertainty, not reclassified as PASS or a product defect.
After approval, the successful normal-user run used a **fresh** output directory;
it did not replay that target or overwrite its authority/evidence. No C2 state
was prepared, consumed, reset or rerun in D1. Multiple independent fresh test
fixtures are separate local simulations, not live write retries.
The intermediate normal-user evidence remains under
`fourgate-output/d1-github-issue-2026-10-23-normal-user/`. The final fresh run
additionally records the initial closed Issue and its transition to the approved
open state, so the local action is demonstrably an update of a preselected
record. Its six outcomes and one-write/six-GET counts are the same.

The full unrelated C2/SDK suite and packaging were not rerun: no runtime,
dependency or packaging surface changed. The relevant scanner, HTTP wrapper,
authentication and reporting checks above passed. Hosted CI, another Python/OS
matrix, actual GitHub server adaptation and customer validation remain unrun.

## Preservation and remaining uncertainty

Before implementation, hashes captured all **860** existing acceptance/artifact
files, including prior execution databases, and persistent client config. The
original checkout at `C:\hifzazafar\fourgate\fourgate` was read only to capture
HEAD/status (`1d7b900e92bf0095f694b76f6a72191a9dbfa04c`). Git fetch/branch operations
update shared Git metadata but do not edit that checkout's files or branch.
Final preservation checks and the complete review patch are retained locally
as `fourgate-output/d1-preservation-after.json` and `fourgate-output/d1-review.patch`.

This pack demonstrates configured equalities at observation time. It does not
prove token scopes, fresh state, write causality, exactly-once behavior, rollback,
tenant isolation beyond the reviewed fixed lookup, customer CI or production
reliability. A preexisting matching record or a concurrent update can satisfy
these predicates. The current live tool schema remains an operator-reviewed
adaptation step. No natural silent-success defect was found or claimed.

The initial D1 work was returned as a local uncommitted reviewable branch/diff.
The subsequent user-authorized review preparation below permits committing
only these D1 files, pushing this branch and opening a **draft** PR. Merge,
release and deployment remain excluded.

## Independent review preparation — 2026-10-23

Reinspected the complete nine-file diff against
`56f1051031103ded1396f4b1305d613d68ff7daf` while staying in the existing worktree
and `codex/d1-github-issue-reference`. No in-scope implementation blocker was
found. The self-check confirmed:

- Identity/title/body/state expectations use reviewed request arguments. The
  returned number is only the GET locator; claimed saved fields are not the
  oracle. Repository binding remains an explicit human-review responsibility.
- Wrong title/identity controls are deliberately induced. Ambiguous 404,
  unavailable 503 and missing required identity remain UNKNOWN.
- The live template is unconfigured, with a placeholder executable and logical
  fixture tool schema. Configuring it requires actual schema discovery and
  explicit target/request/budget approval.
- Reproduction depends on the source-controlled `run_local.py`,
  `stdio_fixture.py` and `scan.example.json`; no local-only executable, secret,
  evidence directory or execution database is a commit input.
- Product runtime, report schema, package/dependencies, CI configuration and
  persistent client configuration are unchanged. No consumed grant is reused.

Fresh consolidated affected check (normal-user execution, existing Python
3.14.6 and pytest 9.1.1):

```text
C:\Python314\python.exe -B -m pytest -q tests/test_github_issue_reference.py tests/test_example_contracts.py tests/test_readback.py tests/test_verify_http.py tests/test_report.py tests/test_scan.py tests/test_readback_auth.py --basetemp fourgate-output/d1-independent-review-tests --tb=short
```

**Exit 0; 108 passed in 60.14 s, from this one invocation.** This is not a sum
of the earlier overlapping 49/64/5 results. Full unrelated C2/SDK tests,
packaging and another OS/Python matrix were not rerun for this source/example
slice. No claim of hosted CI success is made from these local checks.

Fresh standalone reproduction:

```text
C:\Python314\python.exe -B examples/github-issue/run_local.py --out fourgate-output/d1-independent-review-demo
```

**Exit 0**, `expectations_met: true`; one simulated Issue update, six loopback
GETs. Healthy PASS, induced wrong-expectation/identity FAIL, and ambiguous
404/unavailable 503/missing-identity UNKNOWN match the table above. The five
negative controls are read-only and do not repeat the target call. The original
sandbox failure and all earlier successful/failed evidence directories were
preserved, not reused. Environmental UNKNOWN was not upgraded to PASS or
treated as a product defect; the successful normal-user run is separate evidence.

Before this review-preparation turn, hashes captured all **1,151** existing
artifact files plus persistent client configuration. The local preservation
manifest is `fourgate-output/d1-review-prep-preservation-before.json`. Artifacts
and consumed grant databases remain excluded from the commit. Live tool schema,
read identity/visibility, freshness, write causality and customer/production
acceptance remain unverified exactly as described in the pack guide.
