# M2 coverage audit and M3 onboarding slice — 22 October 2026

**Baseline:** `81eabe235ac9d374dbfa6cc1a26e8cde1d994579` (main, PR #47 merged).
**Scope:** inventory existing correctness evidence, fill two specific fixture
coverage gaps, and package one experimental Claude Code setup skill around the
existing CLI. No runtime/interface change or new transport is part of this slice.

The source and tests were inspected in an isolated Linux checkout. The original
8 October milestones remain acceptance gates, not a list completed by this PR.
The founder's Windows checkout and external accounts were not accessed.

## M2 requirement-to-evidence map

Test links identify behavioral evidence. Local servers/stores, fake credentials
and deliberately faulty inputs are **simulations/induced controls**, not natural
incidents or customer validation. A passing negative test means the expected
FAIL/UNKNOWN behavior occurred; it is not a successful business action.

| Requirement | Existing or added executable evidence | Coverage boundary |
| --- | --- | --- |
| Contracted healthy state | `test_matching_record_passes_with_token`; `test_real_scan_distinguishes_persisted_from_false_success` | Declared fields at observation time only |
| Authoritative mismatch | `test_field_mismatch_fails_with_structural_evidence_only`; report mismatch tests | Controlled values; does not validate human intent |
| Record/tenant mismatch when explicitly contracted | Added `test_explicit_record_and_tenant_predicates` (healthy, wrong ID, wrong tenant) | Checks configured identity equalities; trusted expected identity and caller binding remain contract responsibilities |
| Missing authoritative identity | Added `test_missing_authoritative_identity_is_uncertainty` | Missing field is unconfirmed, not contradiction; no automatic mandatory tenant field |
| Approved absence versus ambiguous missing | `test_confirmed_missing_after_retries`; `test_unconfigured_404_exits_nonzero`; GitHub 404 uncertainty test | A configured missing rule is a human assumption; tests cannot establish provider visibility |
| 401/403/503 and denied read | Parametrized `test_auth_denied_and_unconfigured_status_exit_nonzero`; `test_wrong_auth_stays_unknown` | Loopback responses, not credential-scope enumeration |
| Missing ID and selector errors | `test_success_without_record_id_is_unknown_and_skips_http_readback`; text-selector validation tests | Scanner ID guard is optional; contract must choose the right result selector |
| Malformed input/config/store and verifier faults | HTTP verifier input/config tests; `test_malformed_authoritative_store_is_unknown`; runtime fail-open tests | Source-specific error handling; not arbitrary provider/schema conformance |
| Bounded GET retries and delayed visibility | `test_delayed_visibility_retries_to_pass`; `test_timeout_exits_nonzero` | Local timing; no proof beyond the configured observation budget |
| Write timeout stops later cases | Added `test_write_timeout_stops_before_the_next_case` | Real local subprocess records calls while withholding replies; no second write is sent |
| Read/write credential isolation | `test_read_token_not_inherited_by_mcp_server`; runtime `secret_env` tests; Basic/header auth tests | Environment-name separation, not validation of actual token privileges; verifier inherits launch environment |
| Redacted evidence | Report redaction tests; structural runtime HTTP mismatch test | Best effort for covered patterns; arbitrary free text still needs review |
| Shadow preservation and enforce attribution | Runtime guard, CLI guard and HTTP shadow tests | After-response behavior; no rollback or guaranteed agent obedience |
| Request/result binding | `test_argument_result_correlation_isolated`; `test_interleaved_ids_bind_to_correct_tool` | JSON-RPC binding is not proof of correct human intent or cross-system operation identity |
| Agent setup prerequisites | Existing init/doctor tests, including handshake-only, no-verifier/network and no-secret-output checks | CLI mechanics only; does not demonstrate Claude Code follows the new skill |

Relevant source/test files:

- [HTTP verifier tests](../../tests/test_verify_http.py), [read-back tests](../../tests/test_readback.py)
- [Scan tests](../../tests/test_scan.py), [auth tests](../../tests/test_readback_auth.py)
- [Runtime tests](../../tests/test_outcome_guard.py), [secret isolation](../../tests/test_runtime_secret_env.py)
- [Init tests](../../tests/test_cli_init.py), [doctor tests](../../tests/test_cli_doctor.py), [guard tests](../../tests/test_cli_guard.py)
- [Report tests](../../tests/test_report.py), [text selectors](../../tests/test_text_selectors.py), [correlation tests](../../tests/test_isolation.py)

## Explicit gaps and limits

- A pre-existing matching record can satisfy a current-state contract. This does
  not prove the tested action created/changed it. Causality, freshness, uniqueness,
  pending/final completion, concurrent writers and multi-system completion are not
  established automatically. Require adequate provider evidence or exclude them.
- A wrong intended action can be verified perfectly. Human-approved intent and
  trustworthy expected account/record values must precede the write.
- Contract identity controls do not prove universal tenant isolation. Customer
  schemas, caches, visibility, privileges and deployment paths remain unvalidated.
- The runtime verifier cap is two seconds. A controlled local timeout test is not
  a latency benchmark. No new cold/warm network sample or p50/p95 is claimed here;
  representative deployment latency remains a measurement gap.
- No model-backed extraction was added; held-out semantic-assistance evals are
  conditional on adding such a component, not a requirement to add one.
- These are selected assertions, not an exhaustive independent verdict-accuracy
  benchmark. Test counts are not production false-PASS/false-FAIL rates.

**M2 remains partial:** broader contract/deployment adequacy and representative
latency are open. This slice makes evidence and remaining uncertainty reviewable.

## M3 change contract

**Workflow:** ask a coding agent to set up verification for one supported MCP write.
**Gap:** installed CLI commands/configuration currently require manual orchestration;
the repository had no packaged coding-agent setup instructions.
**Reuse:** `init`, `doctor`, `scan`, `guard`, `summary`, existing contracts and verifier.
**Change:** one `.claude/skills/fourgate-setup` instruction package and a client
acceptance guide. No model makes deterministic verdicts.
**Acceptance:** the agent inspects actual schema, prepares an approved contract,
keeps credentials local, runs readiness checks, honors mutation bounds, uses shadow
mode, and reports actual three-valued evidence without requiring the operator to
compose Fourgate commands. See [client acceptance cases](../claude-code-setup.md).
**Stop:** unsupported transport/evidence, unavailable access, unapproved live writes
or required client behavior that cannot be validated.

Claude Code is not installed here. A Codex forward check of the instructions can
exercise preparation/error handling, but cannot establish Claude Code discovery,
invocation, configuration/reload or an external developer's live acceptance.
The M3 milestone therefore remains partial even if all local checks pass.

## Execution evidence

Environment: Linux, Python 3.12.14; isolated virtual environment installed from
this checkout with `python -m pip install '.[dev]' build`. Actual test dependencies
included pytest 9.1.1, mcp 1.9.4 and Pydantic 2.13.5. The virtual environment's
scripts directory was put first on PATH for the full test command. No external
API credentials were used.

| Command / check | Observed result |
| --- | --- |
| `python -m pytest -q tests/test_verify_http.py tests/test_scan.py -k 'explicit_record_and_tenant or missing_authoritative_identity or write_timeout_stops'` | 5 passed, 30 deselected; exit 0; 2.53 s |
| `python -m pytest -q -ra` | 430 passed, 9 skipped; exit 0; 55.67 s. Skips are Windows-only launch/environment checks |
| `python -m build --outdir /tmp/fourgate-build-20261022` | Wheel and sdist built; exit 0 |
| Fresh venv outside checkout: install built wheel with `--no-deps`, `python -m fourgate --version`, `python -m fourgate demo --out ...` | All exit 0; simulated demo self-check passed and summary file exists |
| `python wrap/wrap.py --selfcheck` | Exit 0; legacy intercept-path self-check passed, not a new heuristic or natural finding |
| Skill frontmatter/reference checks, named test references, Markdown fences and 19 relative links | Passed |
| `git diff --check` | Exit 0 |
| Installed Claude Code and external live onboarding | NOT RUN |

One separate Codex agent executed the skill against a preparation-only scenario:
a trusted local fixture and approved test title, a placeholder read endpoint, an
unset read credential, and no live-write/client-change authorization. Its actual
command/doctor output was reviewed. `init` exited 0; strict configuration loaders
passed; handshake discovered `create_issue`; doctor exited 1 / NOT READY for the
missing credential. No scan, verifier read, runtime task, cleanup or client change
was executed. There was no action verdict. The wording was tightened afterwards
to distinguish NOT RUN and doctor results from PASS/FAIL/UNKNOWN; the revised
wording has source/structure review, not a second independent forward execution.

This exercise supports bounded configuration preparation and blocked-readiness
handling, not Claude Code invocation or end-to-end onboarding. The results above
are local; PR CI and client-dependent checks must be read separately.

## Milestone disposition

| Milestone | Evidence after this slice |
| --- | --- |
| M1 GitHub reference | Existing bounded issue/title controls; exact scope enumeration and broader predicates remain limited |
| M2 correctness/measurement | Mapped fixture coverage plus five focused new controls; open limits above |
| M3 coding-agent onboarding | Instruction package prepared; local mechanics and client acceptance reported separately |
| M4 hosted/customer CI | Founder-owned hosted validation documented; customer CI pending |
| M5 agent task outcome | Existing runtime shadow evidence; full task-level acceptance remains open |
| M6 pilot engineering | Requires an authorized named external workflow and owner acceptance |
| M7 expansion | Conditional on demonstrated reusable demand and support requirements |

See [GitHub evidence](github-validation-2026-10-12.md) for historical live controls.
No naturally occurring read-back-proven silent success, new customer CI result,
production reliability or commercial outcome is established by this slice.
