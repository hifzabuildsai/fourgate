# Founder-controlled Codex Desktop acceptance — 31 October 2026

## Provenance and scope

This note records a bounded Windows Codex Desktop exercise against source
revision `47037ce6acd4d59eaefaaa035e7b7263ed9d6de0`. The founder ran the
Desktop client and local helper in an isolated worktree. The documentation
review inspected the supplied preflight, discovery, authority lifecycle,
stop-result and cleanup-verification artifacts. It did not independently
control the Windows processes or rerun the protected workflow.

All configured targets were founder-controlled local simulations. No external
workflow request, customer action, production system or live GitHub mutation
was attempted. The exercise does not establish customer CI, production
reliability, buyer value, a natural silent-success finding or a release.

## Static Desktop acceptance

Before this execution attempt, the founder reported one installed Desktop
request to the isolated static server:

```json
{
  "readiness": "CONFIG_VALID",
  "scope": "STATIC_CONFIG_ONLY",
  "action_status": "NOT_RUN",
  "reason_code": "static_checks_satisfied",
  "isError": false,
  "planned_cases": 1
}
```

The reported lifecycle contained one delivered `tools/call` with a matching
response. No target or verifier ran. This establishes static configuration
readiness in that Desktop environment, not an outcome PASS and not full
Desktop execution compatibility.

## Reviewed execution boundary

The later execution proposal was limited to workflow `reference-issue` and
single-use run `desktop-2a2c042c-once`. Its reviewed maximum was four Desktop
MCP calls in order: validate once, run once, retrieve the report once, restart
Desktop once, then retrieve the saved report once. The protected budget was
one local update and one loopback authoritative GET. Retry, grant replacement,
state restoration and external requests were prohibited.

The supplied preflight recorded:

- the exact source revision and reviewed helper hash;
- matching contract, policy, adapter, target and state fingerprints;
- grant state `AVAILABLE`, `reserved_calls: 0`, `report: null`;
- authority stopped and zero MCP calls before discovery.

The forward configuration change replaced only the isolated static server
entry with the reviewed three-tool execution entry. Hot reload still exposed
only the static tool, so the allowed initial full Desktop restart was consumed.

## Stopped attempt

After restart, the local authority helper emitted a ready event for
`127.0.0.1:65005` and the single reviewed route. Its ready record identified
PID 17960 and a hard deadline. The operator's subsequent listener observation
did not confirm that endpoint, so the attempt stopped under the no-retry rule
before invoking any MCP tool.

The helper then closed with `stop_requested` and `get_count: 0`. The
reviewed stop record preserves these counts:

| Observation | Recorded value |
| --- | ---: |
| Client tool invocations | 0 |
| Delivered `tools/call` requests | 0 |
| Target starts | 0 |
| Protected target calls | 0 |
| Authoritative GETs | 0 |
| Retry performed | false |
| Grant state | AVAILABLE |
| Reserved calls | 0 |
| Saved report | null |

The endpoint observation mismatch remains unexplained. The ready event and
clean stop do not prove that a usable listener remained available to the
Desktop execution path, while the observer's failure to see it is not proof
that the listener never existed. No Fourgate product defect or environmental
root cause is established.

Because `run_workflow` was not invoked, this attempt has action status
**NOT RUN**. It produced no PASS, FAIL or UNKNOWN outcome. UNKNOWN is not used
as a substitute for missing execution evidence.

## Cleanup result

The first cleanup logs contained zero stdout and stderr bytes and therefore did
not themselves establish restoration. A separate read-only verification found
the execution server entry still present and the static entry absent. The
founder then applied the reviewed inverse patch with `git apply --check`
followed by `git apply`.

The supplied post-cleanup verification records:

- inverse patch applied;
- static server entry present;
- execution server entry absent;
- no recorded cleanup or authority stderr.

The final full-file configuration SHA-256 differs from the pre-execution
configuration hash. The reviewed evidence therefore establishes restoration of
the intended Fourgate block, but not byte-for-byte restoration of the entire
configuration file or an independent comparison of every unrelated setting.
No Desktop restart or MCP call was used to claim cleanup success.

Selected reviewed artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| Authority helper | `61975661c27fb66b52bc95f059c0dccc40b30d4c7a585b971cf75d61f0b4a40c` |
| Authority event log | `46198cb07efbd548613c7875d84e72ec0af0c6c498d3ba70e08f7b34d67305c1` |
| Stop result | `48cd227711c2c9a269adef3b16a4482056273e69875c26ae5fdce89d2c2ed7c1` |
| Post-cleanup verification | `37cc19fd3e78e791fe6ce9282d4fb7e820056de7a43279c5184945b97a1fe6e7` |

## What remains unvalidated

The installed Desktop path has not yet demonstrated the complete protected
sequence: validate, one local write, independent GET, fresh report, Desktop
restart and saved report retrieval without additional target or verifier
activity. That gate remains open.

Existing scripted local D1/D2 simulations and hosted repository CI retain their
documented results. This stopped Desktop attempt neither upgrades nor
invalidates them. Live GitHub schema compatibility for the beta reference pack,
customer CI, production reliability and a natural read-back-proven
silent-success incident remain separate gaps.

This documentation change modifies no runtime, protocol, report schema,
dependency, test, release version or product maturity label.
