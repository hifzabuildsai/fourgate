# Agent-operated checks in Codex (experimental)

Use the existing Fourgate CLI and deterministic verifier. This repository adds
a Codex skill entry, not a new MCP server, model dependency or permission grant.
The selected beta direction is **agent-operated outcome regression checks for
consequential writes**. An agent prepares a reviewed contract; authoritative
state determines the verdict; CI can rerun the approved checks.

**Status, 23 October 2026:** the founder reports Windows acceptance at source
commit `b2bfaaa3ee2ed1490ca62eedc482774f5f1fed96`: repository skill discovery,
explicit activation, no-write doctor checks and three local scan controls.
Automatic activation was **not observed**; the regression exercise used manual
skill selection. See the [dated operator report](evidence/windows-codex-2026-10-23.md)
for provenance and exact limits. Windows artifacts were not independently read
in the implementation environment. Client configuration/reload, runtime shadow
routing and external workflows remain unvalidated. The CLI changes are included
in the `0.4.0b1` limited-beta package; the repository skill is distributed
separately and complete Desktop UI protected execution remains unvalidated.

## Discover the skill without a live write

Open the checkout containing this change in the installed Codex Desktop client.
Record its actual version, OS, project path and Git ref. Check for
`fourgate-setup` from `.agents/skills/fourgate-setup/SKILL.md`. Official guidance
documents repository `.agents/skills` discovery and automatic change detection;
restart the client if needed and record that intervention. Do not assume the
Claude `.claude/skills` entry is discovered by Codex.

First request:

> Use $fourgate-setup. Inspect this checkout and the bundled local fixture.
> Prepare one regression check in a new local directory and run doctor only.
> Do not run scan, a verifier, an external request or a protected write. Show
> the proposed outcome contract and remaining acceptance steps.

Then try the equivalent ordinary-language request in a fresh client thread.
Record explicit versus natural activation separately. Read the shared
[workflow](agent-setup-workflow.md) and [commands](agent-setup-commands.md).
Keep these shared files with the repo entry; copying SKILL.md alone into another
project breaks its references. No standalone skill installer is supplied.

Use the selected project-local Python for CLI checks. Reuse an appropriate
existing environment; if installing, use the approved checkout and preserve
project dependencies. No model API key is needed by the deterministic CLI.
Doctor can start the trusted fixture for discovery, but sends no tools/call
and runs no verifier. READY is readiness; the protected action remains NOT RUN.

## Optional shadow configuration

CLI regression execution does not require editing the client's MCP config.
For a separately approved runtime task, inspect the existing stdio entry and
prepare a diff replacing only that server's launch command with the shadow
wrapper. Official Codex guidance uses `~/.codex/config.toml`, or project
`.codex/config.toml` for trusted projects. Preserve the installed client's scope.

Illustrative TOML only; replace placeholders after source/schema inspection:

```toml
[mcp_servers.EXISTING_SERVER_NAME]
command = 'C:/ABS/project/.venv/Scripts/python.exe'
args = ['-m', 'fourgate', 'guard', '--contracts', 'C:/ABS/config/runtime.json', '--mode', 'shadow', '--log', 'C:/ABS/log/outcomes.jsonl', '--', 'C:/ABS/original-server.exe', 'ORIGINAL-ARGUMENT']
cwd = 'C:/ABS/project'
env_vars = ['ORIGINAL_WRITE_TOKEN_ENV', 'INDEPENDENT_READ_TOKEN_ENV']
```

`env_vars` forwards named variables from the client's launch environment. Ensure
the wrapper receives the independent read credential and `secret_env` withholds
it from the child. Preserve all original server bindings and working directory;
never paste secret values into TOML/chat. If the installed Desktop environment
cannot supply them securely, stop at prepared status. Preserve tool approval
policy. Do not add an unwrapped duplicate or replace unrelated servers.

Apply only an authorized config diff and reconnect using the installed client's
supported procedure. Plugin-managed server commands may not be replaceable by
this user-config path: report that limitation rather than inventing an override.
Do not imply the scanner's modern protocol fixtures validate the runtime guard
or the installed client's native 2026 lifecycle.

## Acceptance record

| Gate | Required observation |
| --- | --- |
| Discovery | Installed client lists the repo skill; version/ref recorded |
| Explicit activation | `$fourgate-setup` reads the shared workflow and composes valid commands |
| Ordinary-language activation | Fresh thread selects it, or manual invocation recorded |
| No-write preparation | New configs reviewed; doctor result recorded; zero tools/call/verifier executions |
| Approved local simulation | Separate authorization to scan the disposable local fixture; actual PASS and induced FAIL/UNKNOWN labelled |
| External workflow | Exact target, predicates, read visibility, write/cleanup budget approved; credentials stay local |
| Optional shadow task | Authorized config, actual guard log, independent state and same-call response preservation |
| Rerun/CI | Approved checks rerun from the recorded revision; actual case statuses parsed |

A scan and a client-driven write consume separate budget. An ambiguous result
stops further writes; retry reads only. Do not upgrade client readiness to an
action PASS or claim customer CI, production reliability or natural findings.
Human review controls shipping. The next MCP-interface phase is a separate
implementation decision after this acceptance evidence.

## Official references

Checked 23 October 2026:

- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

These establish documented mechanisms, not an observed result from the
founder's installed Desktop version.
