---
name: fourgate-setup
description: Prepare agent-operated Fourgate outcome regression checks for one consequential local stdio MCP write workflow, using existing init, doctor, scan and deterministic verification. Use for Fourgate setup or an approved regression rerun. Do not use for remote MCP, UI-only actions, unrestricted tool probing or automatic live writes.
---

# Fourgate setup in Codex

Read and follow the shared [setup workflow](../../../docs/agent-setup-workflow.md)
and [command reference](../../../docs/agent-setup-commands.md). They contain the
authorization, authoritative predicate, credential isolation and verdict rules.
Use the [Codex client guide](../../../docs/codex-setup.md) for discovery,
configuration and acceptance; inspect the installed client's actual behavior.

Prepare configuration and run safe local checks while access is missing. An
external action requires the exact approved target and mutation/cleanup budget.
Keep credentials in the operator environment; inspect names/presence only.
CLI regression checks do not require a new Fourgate MCP server or client config
change. If wrapping an existing server, use shadow and preserve its environment.

Return actual commands, exits, typed case statuses, manual intervention and
remaining blockers. READY is not PASS; an unexecuted action is NOT RUN. A
verifier process exiting 0 is not automatically PASS. UNKNOWN is never proof
of a defect. Skill discovery/activation in an installed client needs observation.
