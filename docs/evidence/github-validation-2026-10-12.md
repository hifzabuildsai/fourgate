# GitHub validation evidence — 2026-10-11–12

Bounded validation on our private disposable repository using Fourgate **0.3.0**
and the official **GitHub MCP server 2.0.2**, running locally over stdio against
GitHub's live API. This is hosted CI validation on our disposable repository;
**customer CI validation remains pending**.

## Local operator evidence (2026-10-11)

The reviewed local report records two healthy issue creations with independent
GET/title verification as `PASS / postcondition_satisfied`, plus one real write
through the runtime guard in shadow mode with the same PASS result. Upstream and
forwarded response bytes matched for that same shadow call. These are locally
reported results, not independently observed Actions runs.

The first title check passed after an initial local harness configuration
correction and cleanup; it proves existence/title, not a fresh-open-state
postcondition. Four local test issues were reported independently verified
closed. Raw local reports and private payloads are not published here.

## Hosted Actions evidence (2026-10-12)

Run/job conclusions were checked independently through GitHub's Actions API;
verdicts, scanner exits and cleanup checks were cross-checked against reviewed
structural artifacts. The manual-only workflow ran on GitHub-hosted Ubuntu with
Fourgate 0.3.0 pinned to its resolved release commit and a checksum-verified
native GitHub MCP 2.0.2 release. Negative exits were not hidden.

**All run, commit and PR links below point to a private repository and require
repository read access.**

| Control | Fourgate verdict / reason | Scanner exit | Actions job | Private run (access required) |
| --- | --- | --- | --- | --- |
| Healthy creation + title GET | PASS / postcondition_satisfied | 0 | success | [Healthy run](https://github.com/hifzabuildsai/fourgate-e2e-validation/actions/runs/38275507893) |
| **Induced** incorrect title expectation | FAIL / field_mismatch | 1 | failure | [FAIL control](https://github.com/hifzabuildsai/fourgate-e2e-validation/actions/runs/38276994903) |
| **Induced** missing read-back credential | UNKNOWN / credential_missing | 1 | failure | [UNKNOWN control](https://github.com/hifzabuildsai/fourgate-e2e-validation/actions/runs/38277006437) |

The hosted UNKNOWN stopped at the credential precheck **before a write**
(attempts 0); it did not create an issue. Cleanup, structural-report review and
upload succeeded on all three final runs, including the two failed jobs. Reports
had two-day artifact retention. Runtime shadow/response-preservation evidence
belongs to the local run above, not these hosted runs.

### Initial cleanup-harness failure and correction

The [initial healthy run](https://github.com/hifzabuildsai/fourgate-e2e-validation/actions/runs/38273476062)
returned scanner PASS/exit 0 but **job failure**: immediate issue-list lookup
omitted the fresh issue, leaving cleanup count zero and causing the review step
to fail. Direct GET subsequently found the exact created record. It was closed
and separately read-back-verified before continuing.

[Cleanup fix PR](https://github.com/hifzabuildsai/fourgate-e2e-validation/pull/7)
changed the disposable harness to derive the issue number from that call's
observed native response URL, then verify exact run markers and closed state by
direct GET. The [final execution commit](https://github.com/hifzabuildsai/fourgate-e2e-validation/commit/afbed42c78bfa29cb96e78ea88fe7bc65104d525)
contains this correction. Including the initial run, three hosted test issues
were created and independently confirmed closed with a separate read credential.
Collection absence or a GitHub 404 alone was not treated as missing-state proof.

## Limits

These induced controls are **not natural silent-success findings**. UNKNOWN is
never PASS or bug proof. No naturally occurring read-back-proven silent success
was established. The cleanup failure was a validation-harness defect; it did not
change the product runtime. Only this bounded issue-create/title path was tested;
exact credential scope settings were not independently enumerated. Customer CI
and production reliability remain unvalidated. Earlier vendor findings remain in
the README's separate dated 2026-10-01 snapshot.
