# Local MCP static validation — 23 October 2026

## Scope and provenance

Phase C1 source work starts from merged main
`28ce78a9353a954daafbb37c37423f9c9ca2a040` (PR #49). Remote main was rechecked
before publishing the branch. This is a local Linux engineering check, not a
customer evaluation, natural silent-success finding or new PyPI release.

The new local stdio interface exposes only `validate_workflow`. An operator
registers reviewed scan file bytes and an account label; the tool reuses
`scan.load_contract` and checks declared credential presence. Readiness is
CONFIG_VALID or NOT_READY, with STATIC_CONFIG_ONLY and action NOT_RUN.
It never produces an action PASS, FAIL or UNKNOWN. Existing scanner/runtime
verdict semantics are unchanged.

`run_workflow` and `get_run_report` are not implemented. Execution grants,
mutation budgets and replay/restart controls remain subsequent Phase C work.
See [usage and limitations](../local-mcp-validation.md).

## Executed checks

Environment: Python 3.12.14, pytest 9.1.1, MCP Python SDK 1.9.4 and Pydantic
2.13.5. The existing development environment was used, with its bin directory
first on PATH for installed-console tests.

| Command / check | Observed result |
| --- | --- |
| `python -m pytest -q tests/test_mcp_validation.py tests/test_scan.py tests/test_protocol_compatibility.py` | Exit 0; 57 passed |
| `python -m pytest -q` | Exit 0; 477 passed, 9 skipped, 71.67 seconds; skipped cases are Windows-specific |
| `python -m build` | Exit 0; wheel and sdist built using isolated build tooling |
| Fresh venv: `python -m pip install --no-index --no-deps <built-wheel>` | Exit 0; import confirmed from that venv's site-packages outside the checkout |
| Installed `fourgate mcp --help` | Exit 0 |
| Installed wheel: legacy 2024-11-05 and raw modern 2026-07-28 discovery/list/call | Both CONFIG_VALID / STATIC_CONFIG_ONLY / NOT_RUN; target/verifier marker absent |
| Installed `fourgate demo --out <isolated-directory>` | Exit 0; bundled local simulation and HTML output |
| `python wrap/wrap.py --selfcheck` | Exit 0; existing live intercept self-check reported OK; this is a local induced control |
| `git diff --check` | Exit 0 |

The isolated wheel smoke used SHA-256
`62f4b24dbc47528498397b44cfbd3e8441e5aa55e0cc107de123d0b8206e78d5`.
It retains package version 0.3.0; it was not uploaded to PyPI. Build output also
reported the existing setuptools license-table deprecation warning; no unrelated
packaging migration was included.

The initial [PR #50 CI run](https://github.com/hifzabuildsai/fourgate/actions/runs/39902858583)
at `0dc5a88fd5300e063257bbd2759b19d82cc2ed39` exposed a Python 3.13.16
startup inconsistency: the symlink-loop control returned exit 0 instead of 2
(476 passed, 1 failed, 9 skipped). Python 3.13 changed non-strict
[`Path.resolve`](https://docs.python.org/3.13/library/pathlib.html#pathlib.Path.resolve)
to leave loops unresolved. Startup now explicitly rejects an unresolved symlink.
The 477-pass local full-suite result predates this narrow correction; the
57-test focused suite, build and installed-wheel smoke were repeated successfully
after it. The fingerprint above identifies the rebuilt wheel. Hosted acceptance
must use the corrected head, not the initial run or the earlier local result.

The MCP tests exercise actual subprocess wire traffic, legacy SDK discovery and
invocation, modern metadata/result shapes, invalid registries/arguments,
missing credentials, changed fingerprints, malformed read-back configuration,
symlink/FIFO replacement and bounded request size. An audit hook in the actual
server subprocess denies process execution, network connections and file writes
while validation still succeeds. No credentials or external targets are needed.

An independent agent reviewed this bounded code and executed focused checks and
SDK interoperability. Its malformed-input, file-identity, symlink-loop and FIFO
findings were repaired and regression-checked. It reported no remaining material
issue in C1. The integrated full-suite/build results above were run by the
implementing session; they are not multiple independent reviews.

Local command details, wheel-smoke JSON and build output are retained under
the checkout's ignored `fourgate-output/` directory. They are not hosted
customer evidence or durable CI artifacts.

## Hosted checks and reported client acceptance

The [corrected-head hosted run](https://github.com/hifzabuildsai/fourgate/actions/runs/39903314477)
at `dde4e1a987235e3d702aa5725cf028efcfa6fd3b` completed successfully: all
seven jobs passed. Linux Python 3.10/3.12/3.13 each reported 477 passed,
9 skipped; Windows Python 3.12 reported 485 passed, 1 skipped. Both packaging
jobs and the CI template check also passed. Run status/head and job logs were
independently retrieved; this is hosted project CI, not customer CI.

The later [operator-reported app-server observation](windows-mcp-validation-2026-10-23.md)
at that same source revision adds discovery and one explicit call with
CONFIG_VALID / STATIC_CONFIG_ONLY / NOT_RUN. The raw Windows artifacts were
not accessed here. Later documentation-only changes must be checked separately
from the run above; the executable client exercise is still bound to `dde4e1a9`.

## Remaining acceptance

- Codex Desktop UI tool selection/reload: **NOT RUN**. The reported direct
  app-server discovery/call does not establish that separate client layer.
- Automatic skill selection remains unobserved; an optional MCP call is not a
  mandatory application completion gate.
- Target startup, verifier execution, remote writes and customer workflows via
  this interface: **NOT RUN / not supported by C1**.
- Token scope, visibility, fresh authoritative state, correct human intent,
  production reliability, customer CI and paid customer value remain unvalidated.

The registry root must be trusted and stable during startup. File identity and
byte pins detect the tested replacements; they do not provide isolation from an
actor who can rewrite local code, registry, environment or startup directories.
Referenced verifier behavior is not recursively inspected or executed.
