# GitHub Issue reference outcome-check pack — Phase D1

One workflow: **update one human-selected, existing disposable GitHub Issue**.
The predicates and verdict handling already exist in Fourgate. This pack adds
a reviewed-request template and repeatable local evidence, without a new
verifier, runtime, adapter, report schema or release.

## Review the request and identity

[scan.example.json](scan.example.json) is an **inert source template**, not an
approved live configuration. Complete [the review card](review-card.example.md)
before adapting it. Issue number **73** is fictional local data, not a live
target or approval. The selected repository is fixed in `readback.repository`;
review that it exactly equals `arguments.owner + '/' + arguments.repo`.
Confirm that the chosen record is an Issue, not a pull request.

The template uses the official GitHub MCP Server v2.0.3 `issue_write` schema
documented in [the dated compatibility evidence](../../docs/evidence/github-mcp-compatibility-2026-10-31.md):
`method: "update"` plus the reviewed owner, repository, Issue number and fields.
That release returns a minimal `{id, url}` success object, so neither lookup
identity nor expected state is extracted from the tool response. The separately
reviewed request's `issue_number` selects the GET and is also the expected
observed number. Expected `title`, `body` and `state` likewise come only from
request arguments. Strings use exact equality; no normalization or body-null
substitution is implied. The illustrative contract checks current `open` state
because the reviewed update explicitly requests it.

The command remains intentionally unconfigured. Before adapting the template,
discover the actual authorized **local stdio** server and review its executable,
version, protocol, exposed tool schema and response shape. A later GitHub MCP
release may differ from v2.0.3. Do not send these arguments to an unreviewed
server or infer compatibility from the executable name alone.

The existing `github_issue` read-back constructs a static HTTPS API URL in the
reviewed repository, uses a separate `FOURGATE_GITHUB_READ_TOKEN`, and performs
bounded GETs. The scanner withholds that read credential from the target. A
test-account label is a confirmation label, not proof of account ownership or
write authority. Keep the real target's write credential separate.

## Reproduce entirely locally

From the source checkout with an existing Python environment (no installation
or model key needed):

```text
python -B examples/github-issue/run_local.py --out fourgate-output/github-issue-d1-001
```

On this Windows workspace, use `C:\Python314\python.exe` for `python`. Choose a
**new** output path for every run. An existing directory is refused with exit 2;
there is no force, cleanup or evidence-overwrite option. This demo uses no C2
grant or execution database and must not be pointed at old grant artifacts.

The command copies the template into a fresh local contract, supplies fictional
request values, seeds an existing local Issue with different title/body/state,
replaces the unconfigured server with
[the synthetic stdio fixture](stdio_fixture.py), and changes only the read-back
transport to an ephemeral `127.0.0.1` HTTP authority. Predicate/extraction maps
stay the same. Native `2026-07-28` fixture mode is explicit; this is not a full
GitHub MCP or native-protocol conformance test. No GitHub workflow-target
request, customer action, real credential or external write is used.

It makes **one local simulated update** through the real scanner, then exercises
five **read-only** controls through the same deterministic HTTP engine used by
the scanner and `fourgate.verify_http`:

| Stable local reference | Actual condition checked | Required outcome |
| --- | --- | --- |
| `healthy` | Approved number/title/body/state match persisted local state | PASS / postcondition_satisfied |
| `wrong-expectation` | Deliberately wrong expected title; authority unchanged | FAIL / field_mismatch |
| `wrong-identity` | Deliberately wrong expected number; title still matches | FAIL / field_mismatch |
| `ambiguous-404` | GET 404 without established authoritative absence | UNKNOWN / readback_unconfirmed |
| `unavailable-503` | Authority returns 503 | UNKNOWN / readback_unconfirmed |
| `missing-identity` | 200 response omits the required number | UNKNOWN / readback_shape_invalid |

Controls are simulations/induced conditions, not naturally occurring defects.
Each read uses one bounded GET. None repeats the target call or changes the
local authority. The fixture additionally caps delivery to one protected call.
Its minimal success result contains only synthetic `id` and `url` values; a
healthy PASS therefore cannot depend on copying tool-claimed saved fields.

`acceptance.json` records actual statuses/reasons, expected-outcome comparison,
request counts and contract hashes. Each reference directory contains JSON and
self-contained HTML evidence using the existing report renderer. Read-only
controls have no fresh action (`control_action_status: NOT_RUN`), no scanner
subprocess (`process_exit: null`), and no scan/write retry instructions. Their
read-back verdict can still be FAIL or UNKNOWN. `scan-command.json` records the
healthy scanner command/exit. `target-requests.jsonl`, `target-responses.jsonl`,
the approved request and local authority remain available for inspection.

The **demo command's exit 0 means the expected controls were observed**, not
that every case passed: induced FAIL and UNKNOWN are required outcomes. A real
scan exits 0 only when all cases PASS, 1 on FAIL/UNKNOWN, and 2 on invalid
configuration/report I/O. `CONFIG_VALID` is static readiness; it is not a verified
action, and `NOT_RUN` is not PASS. Review reports before sharing; redaction is
best effort. No runtime report metadata is added: one case per contract plus
the pack's reference directories and hash manifest identify these observations.

## Visibility, freshness and causality limits

- Keep `missing_is_fail: false`. A GitHub 404 can reflect invisibility or an
  unavailable record. Neither a 404 nor omission from an issue list establishes
  authoritative absence. Do not add 404-as-FAIL just to obtain a negative result.
- A 200 body missing a required identity/expected field is insufficient evidence,
  not a confirmed contradiction. Authentication, network, malformed-response
  and timeout failures remain UNKNOWN. Required fields that are present but
  contradict approved values can produce FAIL.
- A matching read-back establishes configured equalities at observation time,
  subject to the selected read identity's visibility. The fixed repository and
  requested issue number bind this narrow lookup; they do not enumerate or prove
  token scopes, universal tenant isolation or trust in an arbitrary authority.
- No current implementation predicate proves the update was caused by this call.
  Preexisting matching state, cached/stale reads, a concurrent update, delayed
  convergence and a tool that echoes another matching record remain limits.
  The pack does not check `updated_at`, actor, operation receipt or freshness.
  An Issue update is chosen to make preapproved identity explicit, not to claim
  fresh-create causality or exactly-once provider behavior.
- Recheck real read visibility on a known disposable record before any separately
  authorized write. If a live outcome is uncertain, stop writes; do not retry
  them to make evidence green. Cleanup is a separate authorized action.

## CI and future adaptation

### Reference pack through local MCP (Phase D2)

The additional [integration check](../../tests/test_github_issue_mcp.py) configures
this same template and tracked stdio fixture for a loopback authority, pins the
exact contract bytes in a registry, and prepares one fresh single-use C2 grant:

```text
python -c "from pathlib import Path; Path('fourgate-output').mkdir(exist_ok=True)"
python -B -m pytest -q -s tests/test_github_issue_mcp.py --basetemp fourgate-output/github-issue-d2-001
```

The first command creates the output parent on a fresh checkout and preserves
an existing directory's contents. Pytest requires that parent to exist when
using the nested `--basetemp` path above.

Choose a **new** basetemp path: pytest may clear an existing one. Never point it
at prior evidence, a consumed grant or an existing execution database. The test
records `D2_COUNTS` and `d2-counts.json` inside its fresh fixture directory.
Static validation must start no target and perform no read-back. Fresh
`run_workflow` must make one simulated update and one GET, returning typed PASS.
Report retrieval, repeated run requests and a restarted scripted stdio
client/server must return saved results with `new_execution: false`, adding no
target starts, calls or GETs. Structural payloads are checked for allowed fields,
size and absence of private fixture values/paths; saved PASS is not fresh
read-back. This is a scripted local wire integration check, not installed Codex
app-server/Desktop acceptance or live GitHub schema validation. It does not
repeat D1's induced controls. Existing pytest CI collection includes this test;
no CI change is required. See
[D2 evidence and per-command counts](../../docs/evidence/github-issue-mcp-2026-10-23.md).

The normal repository pytest job runs
[`tests/test_github_issue_reference.py`](../../tests/test_github_issue_reference.py)
on its existing matrix. To reproduce manually in an already prepared CI source
checkout, run the same local command with a unique `$RUNNER_TEMP` output path.
No live secrets or new CI permissions are required for these local checks.

For a separately authorized external check, first discover and pin the actual
official server version. The template is shaped for GitHub MCP Server v2.0.3
`issue_write`; use [the existing manual-only CI example](../ci/fourgate-scan.yml)
with the reviewed template and its separate write/read credentials,
report-privacy and concurrency guidance. That example can perform real writes;
**it was not executed for D1**. This pack does not
authorize or validate an external server, workflow or customer CI. If opting
into C2 later, follow [the existing execution guide](../../docs/local-mcp-execution.md)
with fresh, separately approved grants; never reset or reuse consumed state.

See [D1 local evidence](../../docs/evidence/github-issue-reference-2026-10-23.md)
and [historical live Issue evidence](../../docs/evidence/github-validation-2026-10-12.md).
Historical creation/title checks do not establish this update pack's live
acceptance. This source pack is not included in the existing PyPI release.
