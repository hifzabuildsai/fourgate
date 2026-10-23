# Shared agent-assisted Fourgate setup workflow

Read the sections in order: supported path, outcome approval, configuration checks, bounded validation, optional runtime entry, truthful handoff. Client entries reference this single procedure.

Prepare and validate one local stdio MCP workflow using Fourgate's existing CLI.
Read [the command reference](agent-setup-commands.md) before composing commands.
Work in the user's project and preserve its instructions, changes and MCP configuration.

## Establish the supported path

1. Record OS, project directory, coding client name/version if available, and the absolute
   Python interpreter used for Fourgate. Check `python -m fourgate --version` and
   the relevant `--help` output with that interpreter. Expect the v0.3.0 interface;
   inspect differences before using another version. If missing, prepare a local
   virtual environment and use the project's approved installation source. Do not
   purchase API access, upgrade a global installation or change the project's dependencies.
2. Identify one existing, trusted server's exact launch command and installed
   version. Support command-configured **local stdio** only. A remote HTTP/SSE URL,
   UI-only action or unavailable authoritative read is an unsupported route for
   this setup; report the blocker without inventing an adapter.
3. Inspect the actual tool input schema and a redacted result example or handler.
   Obtain them through existing discovery or source inspection. Discovery must not
   call write tools. Do not infer an ID selector from a generic example.
4. Inspect credential **names and presence only**. Do not print environment values,
   read credential files into model context, put credentials in arguments, or copy
   raw MCP configuration/results that may contain secrets. Keep read/write credential
   names distinct and preserve the original server's required environment mapping.

## Agree the outcome before execution

Build a short workflow card from available evidence:

- Owner and exact authorized disposable account/repository/tenant.
- Tool, argument shape, safe test arguments and result-ID selector.
- Human-approved intent and expected authoritative fields; correct record and tenant.
- Static-host read endpoint, authentication environment names, known read visibility,
  observation budget, and whether the predicate means accepted, current state or completion.
- Exact allowed write count, cleanup operations and who can perform them.
- Existing checking method and remaining burden, when this is an external evaluation.

Ask only for missing information that changes this card or its authorization. Ask
the operator to approve the expected outcome and target; reuse explicit approval
already given in the current session. A general request to install or set up
Fourgate does not authorize a live write. Never request secret values in chat.
Prepare configuration while live access is missing and label the result
**prepared, not live-validated**.

Derive expected values from approved intent, not the tool's claimed saved values.
Bind returned IDs to the intended record/account with authoritative predicates
where available. A title match alone does not prove tenant identity or causality.
Missing evidence is UNKNOWN; an explicit null follows the field's approved meaning.
Exclude stale/cached, concurrent or delayed outcomes the contract cannot establish.
Keep 404 uncertain unless the owner has established visibility and safe absence
semantics. Do not add a missing-status rule just to obtain FAIL.

## Prepare and check configuration

1. For supported HTTP read-back, use `fourgate init` in a new, project-local directory for the selected tool.
   Supply explicit selectors, argument-derived expectations and credential names.
   Preserve an existing setup; do not use `--force` automatically. Review the three
   generated JSON files, including `secret_env`, target paths and scan arguments.
   For a known custom-verifier workflow, reuse reviewed contract copies with
   correct paths instead. The HTTP scaffold cannot infer a file/database
   verifier; do not invent an HTTP endpoint to make a local fixture fit `init`.
2. If identity/predicates cannot be represented by the scaffold, state the gap.
   Prepare a reviewed contract edit only when its meaning is approved; do not
   silently omit a required property or develop a new verifier in this workflow.
3. Use absolute interpreter, config, log and server-script paths for client setup.
   Account for scan's contract-directory working directory. Preserve launch
   environment and working-directory requirements; stop if the client cannot.
4. Run `fourgate doctor` with the chosen server command only once its startup is
   authorized. Fourgate sends lifecycle discovery/tools-list only; the server may still
   have its own startup effects. Treat a nonzero exit as not ready. Investigate
   warnings, especially credential isolation and the two-second verifier budget.
   A successful doctor result proves setup readiness, not read access or an outcome.

## Validate within the approved boundary

1. If a known disposable record and read permission exist, establish independent
   read visibility before any new write. Treat an inaccessible record as UNKNOWN.
2. When writes are authorized, run one bounded scan of the approved contract.
   Inspect case statuses and reasons as well as the process exit. Exit 0 is a
   successful scan; exit 1 includes FAIL **or** UNKNOWN; exit 2 is configuration or
   report I/O failure. Do not report UNKNOWN as PASS or a confirmed business defect.
3. For negative controls, prefer read-only replay on the known record: an explicitly
   induced wrong expectation and an induced unavailable-read check. Keep temporary
   control copies separate; preserve the approved contract. Never manufacture a
   natural incident or spend an extra live write without authorization.
4. If a write times out or its outcome is ambiguous, stop writes and inspect state.
   Retry only bounded reads. Close/remove only the run's authorized test records
   and independently verify cleanup. Report unresolved cleanup explicitly.

## Prepare the selected client runtime entry (optional)

For an authorized runtime shadow task, use the selected client guide ([Codex](codex-setup.md) or [Claude Code](claude-code-setup.md)). CLI regression checks do not require a client MCP configuration change. Prepare a narrowly scoped configuration diff around the original server command:

`<absolute-python> -m fourgate guard --contracts <absolute-runtime.json> --mode shadow --log <absolute-outcomes.jsonl> -- <original-server-command...>`

Preserve other server entries, scopes, arguments and environment bindings. Keep
credential values out of the diff and use the client's supported environment
references/inherited environment. Ensure the **wrapper** receives the read credential;
`secret_env` then withholds it from the child server. Do not leave an unwrapped
duplicate enabled for the same task. Apply the diff only when client configuration
changes are authorized, and retain a way to restore the original entry.

Reload/reconnect using the installed client's supported procedure. Drive one
approved task only if the write budget includes it; a scan consumes its own write.
Use an isolated run log and serialized test task for attribution. The shape-only
log is not an operation receipt and cannot safely correlate concurrent calls.
Verify independent state and guard evidence, then run `fourgate summary` on that
log. Do not infer success from tool prose, installation, doctor, or an empty log.

Keep shadow mode for onboarding. Enforce adds an attributed verdict on confirmed
FAIL; it does not undo the write or guarantee agent behavior. Runtime UNKNOWN fails
open, and the verifier cap remains two seconds. A skill is instruction, not a
mandatory application completion gate or a guarantee it will be invoked.

## Return a truthful handoff

Report environment/versions, approved predicate, files/configuration changed,
commands and exits, actual case verdicts/reasons, cleanup, manual intervention,
setup time if measured, and the next unresolved input. Use distinct labels for
simulation, induced control and natural observation. An offline check or missing
access leaves live acceptance pending. If no protected action was executed, report
**NOT RUN**, not an outcome verdict. Doctor's NOT READY is a setup result, not a
FAIL or UNKNOWN verdict on an action. Never claim customer CI or production
reliability from a local or founder-controlled run.
