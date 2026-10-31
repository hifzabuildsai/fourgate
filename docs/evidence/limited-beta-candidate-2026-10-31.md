# Limited-beta package candidate preparation — 2026-10-31

## Scope and source

This record prepares a reviewable candidate; it does not authorize publication.
Version remains `0.3.0` and maturity remains early/pre-alpha. The currently
published release and this source-built candidate must not be treated as the
same artifact.

The new branch started from freshly fetched main
`9107a48eea4b16beb269c0efd925c17e80782cbf`. Existing work and ignored evidence
were preserved. The [D4 closeout](github-issue-d4-hosted-2026-10-31.md) reconciles
the historical founder-owned hosted PASS and downloaded hashes. No live
workflow, external target, acceptance credential loader, grant reset or cleanup
was invoked for candidate preparation. D4's three mutations remain exhausted.
Customer-owned CI and complete Desktop UI execution remain separate gates.

Only demonstrated test-discovery and timing-dependent test problems were
changed. Product runtime, contracts, timeouts, write budgets, dependency
constraints and version are unchanged.

## Isolated environment and commands

Local checks used Windows and Python **3.12.14**, within the documented
Python 3.10–3.13 range. The checkout's Python 3.14 environment was not used.
Build, test and consumer environments were separate virtual environments.
Build tools were `build 1.6.1`, `setuptools 84.2.1`, `wheel 0.48.0` and
`twine 7.0.0`; test dependencies included `pytest 9.2.0`, `mcp 1.9.4` and
`pydantic 2.13.5`. Existing development constraints were retained.

The local runner passed an explicit environment allowlist, disabled user pip
configuration and plugin autoload, and did not inherit credential variables.
Dependencies came from public PyPI. Consumer commands ran in fresh working
directories under ignored `OUT`, away from the repository root, with no
source-tree import path; imported modules resolved to `site-packages`.
Token-like values were synthetic fixtures; consumer smoke checks used
`smoke-token-not-a-secret`.
HTTP observations used local loopback fixtures; the scaffold's
`https://api.example.test` URL was never fetched.

Normalized commands below expand `BUILD`, `TEST`, `WHEEL` and `SDIST` to the
corresponding isolated Python interpreter. `ROOT` is the checkout root; `BASE`
is the Python 3.12.14 interpreter used to create those environments. `OUT` is
the ignored local directory `fourgate-output/d4-rc-20261031-c82a91`; `REPORT`
is a fresh per-mode directory under it. Exact argv, working directory, exit,
stdout and stderr are retained there; generated runners are not tracked.

| Check | Command/result |
| --- | --- |
| Build tools | `BUILD -m pip install --index-url https://pypi.org/simple build "setuptools>=68" wheel twine`; exit 0 after a preserved sandbox DNS failure |
| Distribution build | `BUILD -m build --outdir OUT/dist-reviewed`; final result recorded below |
| Metadata | `BUILD -m twine check OUT/dist-reviewed/fourgate-0.3.0-py3-none-any.whl OUT/dist-reviewed/fourgate-0.3.0.tar.gz`; exit 0 |
| Test installation | `TEST -m pip install --index-url https://pypi.org/simple "OUT/dist/fourgate-0.3.0-py3-none-any.whl[dev]"`; exit 0; `TEST -m pip check` exit 0 |
| Full local suite | `TEST -B -m pytest -q --basetemp OUT/pytest-serial-reviewed`; final result recorded below |
| Consumer installation | Fresh virtual environments; `WHEEL -m pip install --index-url https://pypi.org/simple --no-deps <wheel>` and `SDIST -m pip install --index-url https://pypi.org/simple --no-deps <sdist>`; each exit 0 |

The default build first makes an sdist, then builds the wheel from that sdist.
The wheel contains the documented CLI, bundled demo and local MCP adapters.
Docs, skills, reference packs and checkout fixtures intentionally require a
source checkout; the supported setup guides already distinguish that path.

## Demonstrated blockers and retained failures

The first default `pytest -q` exited **2**, with **23 collection errors**: it
recursed into historical source snapshots under ignored `fourgate-output`.
No test bodies ran. Setting `testpaths = ["tests"]` makes the documented default
command select the canonical suite while preserving archived evidence. A
regression builds a temporary canonical suite and an archived source snapshot,
checks the actual default collection command, and verifies the archive bytes
remain unchanged. It failed before the configuration fix and passed after it.

The first scoped suite exited **1** with **3 failed, 525 passed, 1 skipped**
while isolated build/install/consumer work overlapped. The failures were:

- The relative-output demo expected FAIL/`record_missing` but observed
  UNKNOWN/`gate_timeout_or_error`.
- The hanging verifier correctly preserved the wire response and recorded
  UNKNOWN, but its outer deadline won instead of the asserted inner
  `verifier_timeout` reason.
- The 500 ms custom-verifier fixture observed UNKNOWN/`verifier_timeout`.
  This is not evidence that a real credential was loaded or misrouted.

A serial focused run retained **1 failed, 2 passed**: demo and custom-verifier
cases passed; the hang reason assertion reproduced. The integration assertion
now accepts only the two legitimate timeout paths for the hang case and still
requires UNKNOWN, enforce mode and byte-identical wire output. Crash and
malformed-output reasons remain exact. Two deterministic checks separately
verify precise subprocess-timeout mapping and outer-gate UNKNOWN wire
preservation. No verifier cap or runtime deadline was raised.

The first run of those new checks had a test-input newline error (**1 failed,
6 passed**); the fixture was corrected without runtime changes. The final
focused run exited **0**, **7 passed**. The next full serial suite still exited
**1**, with **1 failed, 529 passed, 1 skipped**: the 500 ms custom-credential
verifier again timed out. Its real target marker recorded `read: false` and
`write: true`. Contention is not established as the sole cause.

That credential-routing test now uses the existing in-process registered
workflow runner with a real target subprocess and a controlled verifier
transport. It checks the exact launch environment, selected input, unchanged
`timeout == 0.5`, strict typed PASS and induced FAIL cases, one reserved/attempted
call, persisted authority, saved report and redaction. It does not claim to
execute a real verifier process. Unchanged guard/runtime tests separately
retain actual verifier-child inheritance checks, and the scanner timeout test
still requires UNKNOWN rather than PASS. The focused layered checks exited
**0**, **5 passed**.

These later passes do not erase earlier process-timeout evidence or establish
that a real verifier completes reliably within 500 ms on Windows. The demo and
short-verifier timing sensitivity remains a release gate to characterize or
explicitly bound before broader claims. No runtime deadline or fixture timeout
was raised, and no historical UNKNOWN was relabeled.

## Final candidate results

The final serial suite exited **0**: **531 passed, 1 skipped** in **317.57 s**
(319.109 s including runner overhead). The credential-boundary changes above
are part of that result; it must not be described as a runtime timeout fix.

The final default build and `twine check` both exited **0**. Fresh wheel and
direct-sdist consumer installs and both `pip check` commands exited **0**.
Inspection found **33 wheel members**, **73 sdist members**, **27 packaged
Python files matching checkout bytes**, the correct console entry point and
zero runtime dependencies. No local acceptance artifacts were packaged.
The final wheel's member bytes also matched the earlier consumer-tested wheel.
Archive hashes can differ despite identical member bytes; reproducible builds
are not claimed.

| Local candidate artifact | Bytes | SHA-256 |
| --- | --- | --- |
| `dist-reviewed/fourgate-0.3.0-py3-none-any.whl` | 83,471 | `8d34894930c59a1f8a85c150ec32bdb92952d606b18325e0e03a35a1efbba5c9` |
| `dist-reviewed/fourgate-0.3.0.tar.gz` | 143,932 | `cbc6c64c085f84b3f71a319aa9c16b32f2326139de5cc5738d07e51f078eed94` |

Both final consumer environments passed the import, CLI, demo, scaffold and MCP
checks below. `CONSUMER` is a fresh working directory under ignored `OUT`, away
from the repository root, and `PY` means each installed interpreter in turn.
The additional checkout demo, legacy self-check and scan controls used only
`WHEEL`, as marked. All commands in the table exited **0**, except the intentionally
broken scan.

| Supported check | Actual normalized command/result |
| --- | --- |
| Imports and entry points | Assert `fourgate.__file__` is in `site-packages` and module/metadata version is `0.3.0`; `PY -m fourgate --version` and the installed `fourgate.exe --version` agree |
| CLI surface | `PY -m fourgate COMMAND --help`, separately for `scan`, `guard`, `doctor`, `init`, `demo`, `summary`, `mcp` |
| Bundled demo | `PY -m fourgate demo --out CONSUMER/demo`; all five scenes and the HTML summary succeeded |
| Scaffold and doctor | Exact setup sequence below; generated configuration then local discovery, no verifier GET |
| Installed C2 fixture | `BASE -B ROOT/fixtures/smoke_mcp_execution.py --python PY`; fresh/saved local PASS and restarted replay, one target start/call, no added execution |
| Installed modern C1 fixture | `PY -B OUT/installed_static_smoke.py --out CONSUMER/modern-static`; CONFIG_VALID / STATIC_CONFIG_ONLY / NOT_RUN, zero target starts/calls/HTTP GETs, no grant prepared |
| Checkout Outcome Guard demo | `WHEEL -B ROOT/demo_outcome.py`; exit 0 |
| Checkout legacy self-check | `WHEEL -B ROOT/wrap/wrap.py --selfcheck`, cwd `ROOT`; exit 0 |
| Installed CLI with checkout scan fixture | `WHEEL -B -m fourgate scan ROOT/fixtures/contracts/scan_demo.json --confirm-test-account disposable-demo --report-dir REPORT`; fresh stores, broken exit **1 / FAIL / record_missing**, healthy exit **0 / PASS / postcondition_satisfied**; JSON and HTML present |

The scaffold sequence, run once with each consumer interpreter, was:

```text
PY -m fourgate init --tool create_issue --test-account disposable-demo
  --id-path result.structuredContent.issue_id
  --readback-url https://api.example.test/issues/{record_id}
  --expect title=title --arg title=FOURGATE-SCAN-TEST
  --token-env FOURGATE_SMOKE_READ_TOKEN --dir CONSUMER/config
  -- PY -m fourgate.demo.server
PY -m fourgate doctor --contracts CONSUMER/config/runtime.json
  --log CONSUMER/outcomes.jsonl -- PY -m fourgate.demo.server
```

Line wrapping above is for readability; exact argv are in the local JSON logs.
The existing repository CI was inspected: its test matrix, package job and scan
template use local fixtures. No live acceptance workflow was dispatched.

An additional exploratory `WHEEL -B -m wrap.wrap --selfcheck` from the ignored
consumer directory exited **1**, reporting no intercept verdict. That legacy
diagnostic
requires `fixtures/silent_server.py` and `tests/fixtures/silent_server_baseline.json`
relative to its repository root; those are intentionally absent from the wheel.
README/HANDOFF document it in the checkout development path, not as an
installed-module command. This failure remains recorded, and the documented
checkout command passed separately. No fixtures were injected into the installed
package and no runtime expansion was made to mask this limitation. The public
installed `fourgate demo` self-check passed in both consumer environments.

## Release checklist and remaining gates

- [x] Reconcile historical D4 typed fresh/saved PASS, counters, consumed state,
  three mutations and downloaded hashes without rerunning live acceptance.
- [x] Preserve D3 historical evidence and HTTP 401 preflight NOT_RUN records.
- [x] Fix default test discovery with a failing-before/passing-after regression.
- [x] Keep runtime behavior, timeout budgets, version and maturity unchanged.
- [x] Complete and record the final serial suite and exact-artifact checks,
  including the checkout-only legacy self-check limitation.
- [ ] Characterize the retained Windows demo/verifier timing failures;
  passing isolated checks alone does not close this reliability question.
- [ ] Review the new-head Linux/Windows and Python 3.10/3.12/3.13 fixture-only
  CI results. Local evidence here covers Windows/Python 3.12 only; no live
  acceptance workflow dispatch or rerun is authorized.
- [ ] Choose an approved release version and review the publication artifacts
  before any later release. The unchanged `0.3.0` candidate is not publishable
  as a replacement for the existing release; no version was chosen here.
- [x] Keep customer CI, complete Desktop execution and production reliability
  outside the proven acceptance scope until separately authorized evidence exists.

The build also warns that setuptools' legacy TOML license table is deprecated,
with a stated removal deadline of **2027-02-18**. It does not fail this build;
metadata migration is a bounded follow-up before that deadline. No speculative
packaging migration was included.

No merge, tag, package upload, GitHub release, deployment or maturity upgrade
was performed. Credentials, encrypted files, raw logs, databases, archives and
generated harnesses remain ignored/local. Private D4 links require access.
