# Fourgate scan contract v1

`scan` intentionally invokes writes. Use **disposable test accounts only**.
The operator must repeat the contract's `server.test_account` label with
`--confirm-test-account`. Fourgate cannot independently attest that an account
is a test account; this is an explicit operator safety gate, not a sandbox.

See `fixtures/contracts/scan_demo.json` for a runnable local example and
`fixtures/contracts/scan_github_issue.example.json` for an **unconfigured**
GitHub template. The latter needs a real test server, repository, and verified
output selectors before it can run; it is not an end-to-end validation claim.

- `scan_version`: exactly `1`.
- `server`: `transport: "stdio"`, a command array (no shell), a nonempty
  `test_account` label, optional `protocol_version` (`2024-11-05` or
  `2025-11-25`) and `call_timeout_ms` (1–10000, default 5000). The command
  runs with the contract directory as its working directory. `{python}` in a
  command selects the current Python interpreter.
- `write_tools`: unique explicit MCP tool names that may be called.
- `cases`: each case names a tool in `write_tools`, exact test `arguments`,
  and an `outcome_contract` with `extract` selectors. Optional
  `record_id_field` names a result selector for the created record. When it is
  absent, the configured read-back or verifier runs directly using the other
  extracted fields (for example, a static test URL or request correlation key).
  The case uses either
  the existing Outcome Guard `verifier` and `allowed_failure_reasons` command
  protocol or a `readback` object. A case is never
  synthesized from `tools/list`, and no malformed/edge calls are generated.

To extract an ID from MCP text at `result.content[0].text`, use a result
selector with `path: "result.content.0.text"` and one of:

```json
{"source":"result","path":"result.content.0.text","parse":"embedded_json","field":"id"}
```

```json
{"source":"result","path":"result.content.0.text","parse":"regex","pattern":"\"id\"\\s*:\\s*\"(?P<id>[^\"]+)\"","group":"id"}
```

The embedded JSON selector can read `Email sent successfully! {"id":"..."}`;
the regex captures its `id` value. The text is limited to 8192 characters and
the regex pattern to 256 characters. Configure these selectors for a known
test server response; text alone never confirms delivery or persistence.

For `readback`, use:

- `type: "http"` with a static-host `url_template` containing `{extracted_name}`
  placeholders in path/query, `expected_fields` mapping response JSON dot paths
  to extracted field names, and optional explicit `missing_statuses` (e.g.
  `[404]`). Only HTTPS is allowed off loopback. A 404 is UNKNOWN unless the
  operator explicitly authorizes it as evidence of absence; ensure the
  read-back identity can see the record before doing that.
- `type: "github_issue"` with a fixed `repository` (`owner/name`),
  `issue_number_field` from the extractor, `token_env`, and `expected_fields`.
  The endpoint is GitHub's issue GET API. A 404 is UNKNOWN by default because
  missing permissions and missing records can look alike. Set
  `missing_is_fail: true` only after confirming read access independently.
- Both support `token_env` (environment variable name, never a token in JSON),
  `attempts` (1–5), `interval_ms` (0–2000), and a total `timeout_ms` (1–10000).
  The read-back sends GET requests only and never retries the write. HTTP
  redirects are rejected so a token cannot follow one to another host.

The scanner validates every case before launching the MCP server. It initializes
and lists tools, then calls only contracted names discovered on that server.
Verifier PASS maps to `PASS`, confirmed postcondition failure to `FAIL`, and
every failed call, timeout, or verifier fault to `UNKNOWN`. If
`record_id_field` is configured but its ID is absent or text extraction fails,
the verdict is `UNKNOWN / success_without_record_id` with zero read-back
attempts. It does not prove whether a write occurred.
After a timed-out write the scan stops: retrying the write may duplicate an
action that already happened. Scan exits 0 only when all cases pass, 1 for a
FAIL/UNKNOWN, and 2 for invalid configuration.

This slice supports local stdio MCP servers and either the existing bounded
command verifier or a bounded HTTP/GitHub read-back. It does **not** claim
end-to-end GitHub MCP integration without a supplied test account. Read-back
traffic goes to the explicitly configured endpoint; no telemetry is sent to
Fourgate. The implemented JSON and single-file HTML reports include redacted
evidence for each case.
