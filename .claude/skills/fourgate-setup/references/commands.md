# Fourgate v0.3.0 command reference

Use the selected Python interpreter for every invocation. `python` below is a
placeholder for its absolute path, not a requirement for the user to type commands.
Read the installed command's `--help` before adapting these examples. Compose
argument arrays or quote for the actual shell; never interpolate untrusted values
into shell command text. Preserve Windows paths with spaces and the original
server command/working directory.

## Discover and scaffold

```text
python -m fourgate --version
python -m fourgate init --help
python -m fourgate doctor --help
python -m fourgate guard --help
```

After schema inspection and approval, adapt this **non-executable placeholder**:

```text
python -m fourgate init --tool TOOL --test-account APPROVED-LABEL --id-path result.structuredContent.ACTUAL-ID --readback-url https://APPROVED-HOST/records/{record_id} --expect FIELD=ARGUMENT --arg ARGUMENT=APPROVED-TEST-VALUE --token-env READ_TOKEN_ENV --dir NEW-CONFIG-DIR -- ORIGINAL-SERVER-COMMAND
```

- `--id-path` starts at the JSON-RPC `result`; choose the actual response path.
  For text results, use `--id-json-field` for embedded JSON or `--id-regex` with
  one capture group, only after inspecting that server's actual output.
- `--expect RESPONSE_PATH=ARG_NAME` compares a read-back field with an approved
  tool argument. Repeat it for the required properties. Use `--arg-json` for
  approved non-string arguments. Do not silently drop identity or business intent.
- `--readback-url` uses `{record_id}` on a static HTTPS host. Loopback HTTP is
  allowed for a clearly labelled local fixture. Do not guess a provider endpoint.
- Supply only read credential **environment names**. Bearer is the default with
  `--token-env`; header auth uses `--auth header --auth-header HEADER`; Basic uses
  `--auth basic --username-env NAME`. Keep write credentials in the original
  server's secure launch environment, under distinct names.
- Omit `--missing-status` by default. Read visibility and absence semantics need
  evidence before authorizing one, particularly for GitHub's ambiguous 404.
- `init` writes `readback.json`, `runtime.json`, and `scan.json`, validates them
  with the existing loaders, and does not start the server or contact the target.
  It refuses existing files unless `--force` is explicitly used.
- `init` normally needs no JSON edits for supported argument-derived predicates.
  It does not independently approve the contract or infer the correct intent.

## Check, scan, wrap, summarize

```text
python -m fourgate doctor --contracts ABS-RUNTIME-JSON --log ABS-LOG -- ORIGINAL-SERVER-COMMAND
python -m fourgate scan ABS-SCAN-JSON --confirm-test-account APPROVED-LABEL --report-dir ABS-REPORT-DIR
python -m fourgate guard --contracts ABS-RUNTIME-JSON --mode shadow --log ABS-LOG -- ORIGINAL-SERVER-COMMAND
python -m fourgate summary ABS-LOG --out ABS-SUMMARY-HTML
```

`doctor` does not execute a verifier or prove the read credential's validity or
scope. With a command after `--`, it starts the server for handshake/discovery;
that process's startup behavior is outside Fourgate's control. Scan can perform
real writes; missing read credentials can stop a case before its write.

For an authorized **read-only** check, pass extracted fields as JSON on stdin to:

```text
python -m fourgate.verify_http ABS-READBACK-JSON
```

Both `{"status":"pass"}` and `{"status":"fail",...}` exit **0**. Parse the
typed status; process success alone is not PASS. Nonzero, empty/malformed stdout
or a status outside the protocol is unconfirmed, never PASS. The runtime guard
normalizes unavailable verification to UNKNOWN. Never interpret stderr as a
confirmed verdict. Keep extracted identifiers/values and raw responses private;
review reports before sharing.

## Claude Code configuration

Follow the installed client's `claude mcp --help` and existing configuration
scope. A stdio entry uses `command` plus an argument array. Replace only the
selected server's executable/arguments with the shadow wrapper; preserve its
environment references and the original launch arguments after `--`. Add no
hooks, permission bypasses, credential literals or alternate unwrapped write path.

Claude Code project skills load from `.claude/skills/<name>/SKILL.md`. Copy this
whole `fourgate-setup` directory, including this reference, into another project's
`.claude/skills/` without overwriting an existing skill. This skill is distributed
in the source repository; `pip install fourgate` does not install it into a client.

Official client references, checked 22 October 2026:

- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/mcp
