# Founder-reported Windows Codex acceptance — 23 October 2026

## Provenance and scope

Source: the founder's pasted workspace, no-write acceptance and bounded
regression summaries from Codex Desktop. The Windows worktree and raw local
artifacts were **not independently accessed or reviewed** in the implementation
environment. This note records operator-reported results, separately from
[independently executed Linux/CI checks](engineering-2026-10-23.md).

All executable results below refer to source commit
`b2bfaaa3ee2ed1490ca62eedc482774f5f1fed96`, before this documentation update.
They do not establish a new PyPI release, customer adoption, production
reliability or a natural silent-success incident.

## Workspace and available tooling

- Isolated Windows worktree, detached HEAD at the exact commit above; tracked
  changes absent before and after the exercises. Original checkout and its
  untracked client configuration were reported preserved.
- `C:\Python314\python.exe`, Python 3.14.6, source Fourgate 0.3.0. The
  dependency-free source path ran without installation or environment changes.
  This is limited path evidence, not full Python 3.14 test-suite support.
- Earlier workspace preparation reported Codex CLI `0.163.0-alpha.11`.
  The Desktop application build was not established by the acceptance report.
- Git required a command-scoped ownership exception; no persistent Git
  configuration change was reported.

## No-write acceptance

The supplied Codex skill catalog listed the repository's
`.agents/skills/fourgate-setup/SKILL.md` before manual reading. Explicit
activation was reported observed. Actual fixture schemas were inspected and
three isolated contract copies passed static validation using the existing
custom verifier.

Version/help checks and both doctors exited 0. Each doctor reported
**READY FOR SHADOW**, with one custom-verifier inspection warning. Reported
request traces distinguish the two exercised lifecycles:

| Mode | Observed requests |
| --- | --- |
| Legacy | initialize → notifications/initialized → tools/list |
| Native 2026-07-28 | server/discover → tools/list |

This stage reported **zero tools/call, zero verifier executions and zero
external requests**. No store or outcome log was created. The protected action
was **NOT RUN**; readiness was not an outcome PASS. The custom-verifier warning
does not establish the verifier's credential scope or safety independently.

Operator artifact references, local and not available from this repository:
`fourgate-output/acceptance-20261023-b2bfaaa3/ACCEPTANCE.md` and `acceptance.json`.

## Bounded local regression exercise

The founder subsequently reported exactly three native 2026-07-28 scans using
the existing scanner and custom verifier. Each case used a distinct absolute
store path, also bound to `FOURGATE_DEMO_STORE` for its verifier.

| Simulation / induced control | Actual verdict | Reason | Scan exit | Store observation |
| --- | --- | --- | --- | --- |
| Healthy simulation | PASS | postcondition_satisfied | 0 | ISSUE-001 and requested FOURGATE-SCAN-TEST title saved; both checked |
| Induced missing persistence | FAIL | record_missing | 1 | Fresh store remained absent |
| Induced malformed authority | UNKNOWN | verifier_error | 1 | Invalid JSON remained unchanged |

Reported invocation pattern:

```text
C:\Python314\python.exe -m fourgate scan <case>\scan.json --confirm-test-account disposable-demo --report-dir <case>\reports
```

Each trace contained server/discover, tools/list and one tools/call: nine
protocol requests, **three tools/call total**, zero write retries. Read-only
verifier replays separately returned exit 0 / typed pass, exit 0 / typed fail
(record_missing), and exit 2 / empty stdout. Process exit 0 was not used as
proof of PASS. The malformed-authority UNKNOWN does not establish a missing
write or a defect; the evidence was deliberately made unreadable.

The summary preserves exact commands, contracts, traces, reports and store
observations locally at:
`fourgate-output/bounded-regression-f5fd04921d3f4ef6920a89ac916bfd96/summary.json`.
No external request, customer action, installation, upgrade or client-config
change was reported. Existing artifacts and tracked files remained unchanged.

## Activation result and remaining gates

Automatic skill activation was **not observed** in the regression exercise.
The agent manually selected/read the repository skill; that does not count as
automatic activation. Explicit invocation is the observed supported setup path.
No cause for automatic selection being missed has been established. Do not
present this as a confirmed Codex defect or promise unattended activation.

| Gate | Evidence status |
| --- | --- |
| Repository skill discovery and explicit invocation | Operator-reported observed |
| No-write configuration and doctor, both lifecycles | Operator-reported observed |
| Native local PASS / induced FAIL / induced UNKNOWN scans | Operator-reported observed |
| Automatic skill activation | Not observed; manual selection used |
| Desktop application build | Not established |
| Guard route installation/reload and same-call runtime shadow task | NOT RUN in these exercises |
| Native runtime-guard compatibility | Unvalidated |
| External owner workflow, repeat use and customer CI | Unvalidated |
| Natural read-back-proven silent-success case | Not established |

These checks add one founder-controlled client/environment observation, not
completion of external onboarding acceptance. The fixed fixture ID and local
JSON-file authority do not establish external tenant isolation, freshness,
causality or delayed completion. Runtime shadow/enforce guarantees and the
two-second verifier cap remain unchanged.
