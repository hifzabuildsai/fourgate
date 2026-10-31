# Phase D4: founder-owned hosted acceptance — 2026-10-31

## Preserved result and scope

**D4_HOSTED_PASS / CLEANUP_VERIFIED.** The separately authorized
[private run 41189432989 (access required)](https://github.com/hifzabuildsai/fourgate-e2e-validation/actions/runs/41189432989)
completed on attempt **1**. Both `local-controls` and `live` succeeded, but the
live acceptance decision below comes from the downloaded typed reports,
execution counters, consumed state and cleanup evidence, not job color alone.

This closes the bounded **founder-owned hosted CI** gate for the GitHub Issue
reference pack. It does not establish customer CI, production reliability,
automatic agent activation or complete Desktop UI execution. The
[bounded Desktop record](codex-desktop-2026-10-31.md) retains its static readiness
observation and stopped NOT_RUN execution attempt. Earlier
[D2 local simulation](github-issue-mcp-2026-10-23.md) and
[D3 live local-stdio](github-issue-d3-live-2026-10-31.md) evidence retain their own
source pins and limits.

D4 reconciliation used preserved files only. No live workflow, Issue GET,
external target/verifier or cleanup was rerun, and no acceptance credential
values were loaded. The separate [package candidate checks](limited-beta-candidate-2026-10-31.md)
use static checks and local fixtures.
The D4 Issue mutation budget is exhausted. These historical commands and records
are not authorization to repeat execution or restore consumed state.

## Exact reviewed identities

| Item | Recorded value |
| --- | --- |
| Private repository | `hifzabuildsai/fourgate-e2e-validation`, ID `1413863836` |
| Workflow | `.github/workflows/fourgate-beta.yml` |
| Reviewed workflow / dispatched main commit | `4ea01ecafb5e52b6e46f25d9520784e31db70405` |
| Pinned Fourgate source | `9107a48eea4b16beb269c0efd925c17e80782cbf` |
| Fourgate version string | `0.3.0`; no release or maturity bump |
| Official GitHub MCP Server | `2.0.3`, commit `b98d115bbb080e9555466a96656ec4df605aea21` |
| Linux x86_64 asset SHA-256 | `f797c20fe02a755865d0e2d46184ab47e31bf1619b0855b8d89c531e45a651c2` |
| Approval marker | `fg-d4-20261031-4ea01ec` |
| New disposable target | [Issue #12 (private; access required)](https://github.com/hifzabuildsai/fourgate-e2e-validation/issues/12) |
| Execution run ID | `d4-41189432989` |
| Recorded contract SHA-256 | `9a479f592648f4e9cf5e5a5f1877b536f79e10ea4e082fc319590255f4f3e663` |

Before Issue creation, the repository was confirmed private, maintainer/admin
authorization and Actions readiness were checked, reviewed workflow/driver and
source-template blobs matched, and both separate D3 replacement credentials
could read the private repository. Only `FOURGATE_MCP_WRITE_TOKEN` and
`FOURGATE_READBACK_TOKEN` were updated, using authenticated `gh secret set`
with secret values on process stdin, never arguments, chat or tracked files.
The original D3 files, encrypted replacements and consumed database remained
unchanged. This is historical credential-handling evidence, not a credential
check performed during closeout.

The sole setup creation requested title
`[Fourgate D4] PRESTATE fg-d4-20261031-4ea01ec` and body
`fg-d4-20261031-4ea01ec`. Only the returned number **12** was bound. A subsequent
read confirmed the exact open PRESTATE and absence of `pull_request`. Issue #10
was not recreated or modified.

Main was rechecked against the reviewed commit immediately before the single
dispatch, whose exact non-secret payload was:

```json
{
  "ref": "main",
  "inputs": {
    "issue_number": "12",
    "approval_marker": "fg-d4-20261031-4ea01ec",
    "reviewed_workflow_sha": "4ea01ecafb5e52b6e46f25d9520784e31db70405"
  }
}
```

## Recorded commands and typed evidence

Paths below are normalized historical records. `OUT` is the original ignored
`fourgate-output/d4-hosted-20261031-7b9e4a`; `REPO` is the private repository above.
Generated local controllers/loaders are not part of the package or this PR.

| Stage | Recorded command/result |
| --- | --- |
| Secret updates | `gh secret set FOURGATE_MCP_WRITE_TOKEN --repo REPO --app actions` and `gh secret set FOURGATE_READBACK_TOKEN --repo REPO --app actions`; values via stdin; each exit 0 |
| Setup | One authenticated Issue creation with the exact title/body above; returned Issue #12 |
| Dispatch | `gh api --method POST repos/REPO/actions/workflows/fourgate-beta.yml/dispatches --input - --include`; payload above via stdin; exit 0, HTTP 204; raw headers withheld |
| Hosted local controls | `python -B -m unittest discover -s ci -p test_beta_acceptance.py -v`; step success; simulations/no-write gates, no live credentials |
| Hosted acceptance | `python -B ci/beta_acceptance.py`; step success; pinned source and first-attempt gates before execution |
| Hosted collection | `python -B ci/beta_acceptance.py --collect`; step success; reviewed structural/state allowlist and secret checks |
| Artifact download | `gh api repos/REPO/actions/artifacts/13038425933/zip`; binary stdout saved to a fresh local ZIP; exit 0 |

The reviewed workflow pins its checkout/setup/upload actions. Its live job is
manual-dispatch-only and requires successful local controls. The reviewed
driver rejects reruns, a changed workflow/source pin, wrong repository,
historical Issue numbers and mismatched PRESTATE. It uses the existing
request-derived number/title/body/state predicates, one read-back attempt and
the independent read credential. No custom live verdict implementation was
introduced into Fourgate.

| Phase | Target starts | Protected call attempts | Outcome GET attempts | Typed record |
| --- | --- | --- | --- | --- |
| `validate_workflow` | 0 | 0 | 0 | CONFIG_VALID / STATIC_CONFIG_ONLY / NOT_RUN |
| Fresh `run_workflow` | 1 | 1 | 1 | COMPLETED / ATTEMPTED / PASS; new_execution true |
| `get_run_report` | 1 | 1 | 1 | Same recorded PASS; new_execution false |

Counts are cumulative for the **live job**, not its separate simulated control
job. Report retrieval added **zero starts, calls or GETs** and left consumed
SQLite bytes unchanged. Fresh and saved payloads matched except for
`new_execution`; fresh `reserved_tool_calls` and `call_attempts` were both **1**,
with case **PASS / postcondition_satisfied**. The adapter exit record was **0**.
Saved `action_status: ATTEMPTED` describes the original action, not another write.

The single instrumented outcome GET is distinct from repository/credential
readiness reads. On the reviewed successful hosted path, three additional Issue
GETs checked PRESTATE, pre-cleanup open state and post-cleanup closed state.
Operator observations separately confirmed the newly created Issue and the
closed record after artifact review. Local credential readiness used two
repository GETs. These scopes must not be collapsed into one total described
as "one GET for the whole workflow".

## Consumed grant, cleanup and mutation accounting

The retained grant is **COMPLETED**, `reserved_calls: 1`, run ID
`d4-41189432989`; its stored report equals the fresh typed payload. Its canonical
policy fingerprint is
`fc8e2676fc742cc454c200e48be336062c85f18f502919344be5964c2fe138f1`.
The downloaded database was inspected read-only and never restored for execution.

Before cleanup, the hosted driver wrote `before-cleanup.json` and a
`pass-manifest.json` pinning the completed state and reports. Only a complete
typed PASS plus matching authoritative open state allowed the close. The PATCH
sent only `{"state":"closed"}`, retaining the verified title/body. Hosted
cleanup recorded `CLOSED_GET_VERIFIED`; an independent operator read also
observed Issue #12 closed with title
`[Fourgate D4] VERIFIED fg-d4-20261031-4ea01ec` and body
`Fourgate D4 hosted acceptance fg-d4-20261031-4ea01ec`.

| Actual Issue mutation | Count |
| --- | --- |
| One new disposable setup Issue | 1 |
| One protected update | 1 |
| One PASS-only cleanup close | 1 |
| **Total / authorized maximum** | **3 / 3** |

Workflow dispatches: **1**. Run attempts: **1**. Write retries and dispatch
retries: **0**. There was no manual cleanup retry, reopen, grant reset or reuse
of D3 state. No additional live acceptance action was taken for this closeout.

## Downloaded artifacts and remaining limits

Artifact `d4-structural-41189432989-1`, ID `13038425933`, contained 14 reviewed
structural/state files. The 6,726-byte ZIP was downloaded and matched GitHub's
recorded digest before its two-day expiry, `2026-11-02T09:37:36Z`.

| Integrity anchor | SHA-256 |
| --- | --- |
| Downloaded artifact ZIP / GitHub digest | `c5a087c2029b4ed4baa36a31cda95494497ffffa922e344e7e302176c50acd67` |
| Consumed database | `360b54e4591a3e40f321c71fd75b8e87323c1b3e427d90e32ea8f85f65da9c36` |
| Local D4 artifact manifest | `6e91b6e1a33d22230687615b2a77a7028e567a19113ada2bcc5d99aa09275b51` |

The local report and all **94 recorded file hashes** reconciled during closeout.
`collection.json` hashes matched the downloaded files; all nine provided files
referenced by the pre-cleanup manifest matched, including consumed state. The
workflow intentionally omitted raw `scan.json`, `registry.json`, `policy.json`
and server traffic. The recorded contract hash agrees between typed results and
the pre-cleanup manifest, but the exact raw contract bytes cannot be independently
rehash-verified from that structural bundle alone. No withheld file was recreated
or grant repinned to fill that evidence boundary.

Credentials, encrypted files, database, ZIP, raw API records and generated
harnesses remain local/ignored. Private links require repository access; public
hashes do not make their underlying private observations public evidence.

Founder-owned hosted acceptance does not demonstrate customer-owned CI or full
Desktop UI routing/restart acceptance. Broader platform/protocol coverage,
universal freshness, token scopes, write causality and provider exactly-once
behavior remain unproven. There is no natural silent-success finding, release,
version/maturity upgrade, merge or deployment implied by this record.
