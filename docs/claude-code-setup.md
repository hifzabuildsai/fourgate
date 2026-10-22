# Agent-assisted setup in Claude Code (experimental)

This repository includes one project skill, `fourgate-setup`, that guides an agent
through Fourgate's existing `init`, `doctor`, `scan`, shadow guard and summary
commands. It prepares one supported local stdio MCP write workflow. It adds no
runtime verifier, model dependency, client hooks or permission grants.

**Validation status, 22 October 2026:** the underlying CLI has local executable
tests. One Codex execution of the instructions prepared configuration, discovered
the fixture tool and stopped at doctor NOT READY for a missing read credential;
no action verdict or live write occurred. That exercise prompted explicit
NOT RUN versus setup-result wording. Claude Code is not installed in the
implementation environment. Discovery, natural-language activation, client
configuration/reload and a developer's agent-driven live run remain **unverified**.
This is not completion of the M3 onboarding milestone.

## Make the skill available

In a checkout containing this change, start Claude Code at the repository root
and check that `fourgate-setup` is available. In another project, ask your coding
agent to copy the complete
[fourgate-setup directory](../.claude/skills/fourgate-setup/) into that project's
`.claude/skills/`, preserving an existing directory instead of overwriting it.
Include `references/commands.md`; copying `SKILL.md` alone omits the command guide.

This is a repository-distributed skill. Installing the PyPI package does not
install it into Claude Code. No marketplace/plugin package or installer is provided.
Keep the skill revision and installed Fourgate/client versions in evaluation notes.

Ask in ordinary language:

> Set up Fourgate for one of this project's local stdio MCP write tools. Inspect
> the actual schema, prepare the outcome contract for my approval, and tell me
> what access is missing before running any live write.

If the client does not select it, invoke `/fourgate-setup` directly. Record the
failure to activate and that manual intervention; do not count installation or
skill availability as a verified action outcome.

## Scope and human control

The agent inspects the installed interface, identifies one trusted server/tool,
and uses existing configuration loaders. It asks for approval of the intended
outcome, disposable target, mutation/cleanup budget and required client changes.
Credentials stay in the operator's secure launch environment. The agent sees
names/presence, not secret values.

A successful doctor result establishes readiness only; NOT READY is a setup
result, and an unexecuted action is NOT RUN. Scan and an agent-driven task each
consume their own authorized write. Shadow setup preserves the original
response. Runtime uncertainty fails open; enforce annotates confirmed failure
without undoing the write or guaranteeing the agent obeys.

The current scaffold maps read-back fields to approved tool arguments. More
complex identity, intent, freshness or completion requirements can need reviewed
contract edits or make the workflow unsuitable. A skill does not provide remote
MCP, UI-only verification, asynchronous scheduling or universal agent support.

## M3 acceptance procedure

Use an operator-controlled staging/disposable workflow and record interventions.
The operator supplies approval, intent and secure credential setup; the agent
should compose the Fourgate commands.

| Case | Evidence required |
| --- | --- |
| Existing install | Version/interpreter discovered, exact supported tool schema inspected, configuration prepared without overwriting existing work |
| Fresh install | Project-local installation from an approved source; package and skill availability recorded separately |
| Missing prerequisite | Clear blocked/prepared status; no guessed schema, secret disclosure or unauthorized write |
| Unsupported transport | Remote-only/UI-only route reported unsupported for this setup; no compatibility claim |
| Invalid configuration | Nonzero validation/doctor result reported; no write until corrected |
| Healthy workflow | Intended record/tenant and contracted fields independently observed; actual PASS evidence |
| Induced mismatch | Read-only replay where possible; confirmed contradiction is FAIL and explicitly labelled induced |
| Induced unavailable read | UNKNOWN, never PASS or bug proof; preserve the approved configuration |
| Shadow task | Approved client diff, no duplicate unwrapped route, actual guard log and independent final state; original response preserved |
| Ambiguous write | Stop further writes, inspect state; no blind retry |
| Cleanup | Only the run's approved records affected; cleanup independently checked |
| Repeat setup/use | Owner can rerun from the instructions; active setup time and every founder intervention recorded |

Run the client-dependent cases on the owner's installed Claude Code. Record
client/Fourgate/server versions, OS, project scope, exact predicate, approvals,
commands/exits, report paths, verdicts/reasons and unresolved limits. Test Windows
and Linux separately where available; repository CI cannot prove client behavior.
Never publish raw credentials, customer identifiers or unreviewed reports.

The local CLI simulation can establish mechanics. A real external developer's
authorized run is still required for the original M3 acceptance gate. Payment,
customer CI, production reliability and natural incidents are separate evidence.

## References

- [Skill instructions](../.claude/skills/fourgate-setup/SKILL.md)
- [Command reference](../.claude/skills/fourgate-setup/references/commands.md)
- [Engineering coverage audit](evidence/engineering-2026-10-22.md)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)

Official client documentation checked 22 October 2026. Future client changes
require a new run; documentation compatibility alone is not executable proof.
