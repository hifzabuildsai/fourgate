# Fourgate scan contract v1

`scan` intentionally invokes writes. Use **disposable test accounts only**.
The operator must repeat the contract's `server.test_account` label with
`--confirm-test-account`. Fourgate cannot independently attest that an account
is a test account; this is an explicit operator safety gate, not a sandbox.

See `fixtures/contracts/scan_demo.json` for a runnable example.

- `scan_version`: exactly `1`.
- `server`: `transport: "stdio"`, a command array (no shell), a nonempty
  `test_account` label, optional `protocol_version` (`2024-11-05` or
  `2025-11-25`) and `call_timeout_ms` (1–10000, default 5000). The command
  runs with the contract directory as its working directory. `{python}` in a
  command selects the current Python interpreter.
- `write_tools`: unique explicit MCP tool names that may be called.
- `cases`: each case names a tool in `write_tools`, exact test `arguments`,
  and an `outcome_contract` using the existing Outcome Guard `extract`,
  `verifier`, and `allowed_failure_reasons` structure. A case is never
  synthesized from `tools/list`, and no malformed/edge calls are generated.

The scanner validates every case before launching the MCP server. It initializes
and lists tools, then calls only contracted names discovered on that server.
Verifier PASS maps to `PASS`, confirmed postcondition failure to `FAIL`, and
every missing result, failed call, timeout, or verifier fault to `UNKNOWN`.
After a timed-out write the scan stops: retrying the write may duplicate an
action that already happened. Scan exits 0 only when all cases pass, 1 for a
FAIL/UNKNOWN, and 2 for invalid configuration.

This first slice supports local stdio servers only. It reuses the existing
deterministic, bounded command verifier. Generic HTTP/GitHub read-back and
redacted evidence reports follow in the next milestones.
