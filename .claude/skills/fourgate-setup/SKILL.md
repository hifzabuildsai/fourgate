---
name: fourgate-setup
description: Set up Fourgate outcome verification for one supported local stdio MCP write tool. Use when asked to configure Fourgate, check an agent's persisted action outcome, or prepare a shadow-mode setup. Reuse init and doctor, obtain human approval of the outcome contract and disposable target, and report actual PASS, FAIL or UNKNOWN evidence.
---

# Fourgate setup in Claude Code

Read and follow the shared [setup workflow](../../../docs/agent-setup-workflow.md)
and [command reference](../../../docs/agent-setup-commands.md). Keep these files
available with this repository-scoped entry.

For client configuration, scopes, reload and acceptance, read
[Claude Code setup](../../../docs/claude-code-setup.md). Preserve the original
server entry and secret environment bindings. Do not change permission settings
or send a live write without current authorization for its exact target/budget.

Keep PASS, FAIL, UNKNOWN, readiness and NOT RUN distinct. Skill instructions
are not a mandatory completion gate.
