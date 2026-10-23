# Local MCP execution controls — 23 October 2026

## Scope and provenance

Phase C2 starts from merged main `d2f1887f2e1c0ae4eccd4932906ed656670f6677`
(PR #50). Main was rechecked before preparing this PR. Source changes reuse
the scanner/verifier, add opt-in operator grants and structural report tools,
and keep default MCP validation read-only. See [operator setup and limits](../local-mcp-execution.md).

The observations below were executed in this Linux implementation environment,
not supplied as customer or Windows reports. Every target was an isolated local
fixture or packaged demo. There were no external workflow-target requests or
mutations. Simulations, induced uncertainty and deliberate state-corruption
controls are not natural silent-success findings.

The published source head and its hosted CI are recorded on the PR. This note
does not establish a PyPI release, production reliability or commercial maturity.

## Actual commands and results

Python 3.12.14, pytest 9.1.1, MCP Python SDK 1.9.4 and Pydantic 2.13.5;
existing validation environment, with its bin directory first on PATH.

| Command / check | Observed result |
| --- | --- |
| Initial new execution test, `python -m pytest -q tests/test_mcp_execution.py -x` | Failed because `--execution-policy` / preparation were unrecognized; feature gap established before implementation |
| Focused execution/validation/scan/protocol/runtime-secret suite | 101 passed, 1 skipped before the final SDK test was added |
| Final `python -m pytest -q` | Exit 0; 513 passed, 9 Windows-specific skips, 83.97 seconds; includes 36 C2 parametrized tests |
| `python -m build` | Exit 0; final wheel and sdist built |
| Fresh venv: `python -m pip install --no-index --no-deps dist/fourgate-0.3.0-py3-none-any.whl` | Exit 0; no additional runtime pip dependency |
| `python fixtures/smoke_mcp_execution.py --python <fresh-venv-python>` | Exit 0; import from site-packages outside checkout; local PASS, 1 target start, 1 call; restarted replay had new_execution false and no extra target start/call |
| `python wrap/wrap.py --selfcheck` | Exit 0; existing local induced live-intercept self-check reported OK |
| `git diff --check` and local documentation-link check | Exit 0 |

Final locally smoked wheel SHA-256:
`1c04afeb25a46fdea586455c40cc1802bc7057ec5aea0ee98ae288e4858603c4`.
All five changed production modules in that wheel matched source bytes.
Package version remains 0.3.0; the candidate was not uploaded. The existing
setuptools license-table deprecation warning remains outside this change.
Local build/smoke output is under ignored `fourgate-output/phasec2-*` paths;
the reproducible smoke script is tracked and also runs in packaging CI.

The [initial hosted run](https://github.com/hifzabuildsai/fourgate/actions/runs/39908795627)
at `7aa8411792e1acbc9dea04b3699757acfbebdd55` found a Linux packaging-smoke
harness defect: resolving a venv Python symlink selected the base interpreter,
which could not import the installed wheel. Windows packaging and the Linux
test jobs passed. An explicitly symlinked local venv reproduced exit 1 before
the repair. Preserving the executable's absolute path instead of resolving
symlinks then produced exit 0, local PASS, one target start/call and no replay
write. Product modules were unchanged by this harness-only correction. The
full-suite result above predates it; installed-wheel smoke was repeated after
it. The [corrected-head hosted run](https://github.com/hifzabuildsai/fourgate/actions/runs/39909209441)
at `c0e06f0e500874eb493019f6be90128e15d0725c` was independently checked:
all seven jobs succeeded. Linux Python 3.10/3.12/3.13 each reported 513 passed,
9 skipped; Windows Python 3.12 reported 521 passed, 1 skipped. Both packaging
jobs passed fresh installed-wheel smoke. The initial harness defect is not an
outcome verification or natural silent-success finding.

## Behavioral evidence

| Fixture / induced control | Observed behavior |
| --- | --- |
| Healthy authoritative local state | PASS; exactly one contracted call; structural report retrieval/replay starts no new execution |
| Induced missing persistence | FAIL / record_missing despite successful MCP/client process |
| Induced unavailable verifier | UNKNOWN / verifier_error despite successful process |
| Persisted write with no response, two planned cases | UNKNOWN / TimeoutError; one call, both cases reserved; no second case or restarted replay |
| Adapter killed after observed persistence | Restarted run/report UNKNOWN / UNCERTAIN; trace still one call |
| Two processes held at the claim boundary | One shared grant wins; target trace records one call |
| Missing/corrupt state, changed policy or inconsistent AVAILABLE row | Refusal; no reconstructed authority or extra write |
| Missing credential, changed contract, insufficient budget, approval/path/URL/command overrides | NOT_RUN before target startup; no action verdict |
| Contract replaced after validated load | Existing pinned in-memory bytes executed; replacement not reopened |
| Report save failure or malformed/extra/private saved fields | UNKNOWN; grant remains consumed; no private sentinel returned |
| Verifier credentials | Declared custom read secret and HTTP Basic username/token absent from target environment; trusted verifier retained its credential |
| Real installed SDK client | Legacy 2024-11-05 discovery/run/report accepted; fresh-versus-cached flags and one target call checked |

One independent agent reviewed this bounded implementation and ran focused
fixtures. Review found a detectable corrupt-state replay, inconsistent saved
UNCERTAIN handling and boolean/integer schema issue. The root session reproduced
the relevant failures and repaired them with regression coverage. The reviewer
reported no remaining authority/correctness/privacy blocker; a policy-test
quality issue was then corrected to test rejection during explicit preparation.
These are review passes by one agent, not multiple independent reviews.

## Remaining acceptance and limits

- Hosted CI at the tested source head `c0e06f0e` passed as recorded above;
  any later PR head needs its own CI check. The local full suite is Linux
  evidence only; Windows test evidence comes from hosted CI.
- Actual installed Codex app-server execution/report acceptance for **C2** was
  subsequently [reported by the founder](windows-mcp-execution-2026-10-23.md)
  at `c0e06f0e`: local PASS, induced FAIL/UNKNOWN and saved-result replay without
  extra target/verifier calls. Those Windows artifacts were not independently
  inspected or rerun here. The original harness-blocked grant remained UNKNOWN;
  a separately approved replacement supplied PASS, without resetting state.
- Desktop UI reload/tool selection, customer workflows, customer CI, production
  reliability, buyer value and natural silent-success findings remain unvalidated.
- State assumes trusted local storage and preservation of grant history.
  Same-host tampering, restoring a valid old database, provider-side exactly-once
  behavior, rollback and mandatory agent obedience are not established.
- The call budget counts protected MCP attempts, not internal provider mutations,
  command-startup side effects, or verifier side effects. Cached PASS is a saved
  observation, not fresh read-back or proof of correct human intent.

Runtime shadow/enforce behavior, fail-open uncertainty and its two-second cap
are unchanged. The adjacent scanner credential-isolation repair is explicit:
read-back Basic username and declared custom-verifier secrets now join the
already excluded read token in the target-server environment filter.
