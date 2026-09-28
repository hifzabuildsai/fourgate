# Security and data flow

Fourgate scan **executes the contracted write tools** on the MCP server you
configure. Run it only against disposable test accounts with the exact account
label confirmation. It does not inspect whether an account is really a test
account. It never selects extra tools from discovery or retries a timed-out
write, because the write may already have happened.

Fourgate launches the configured local stdio MCP server and passes the exact
contracted test arguments. The scanner reads its discovery and tool responses.
The legacy runtime wrap stays on the same local stdio path. Verifier commands
run locally, receive only contract-selected fields, and inherit the current
environment. A configured HTTP/GitHub read-back makes outbound **GET requests
to that configured endpoint**, carrying an env-supplied token if requested.
The MCP server itself may also make outbound requests according to its own
implementation. Therefore, "nothing leaves the machine" is true only for a
fully local test fixture, not for HTTP/GitHub verification.

Fourgate has **no telemetry, analytics, or Fourgate-hosted endpoint**. It does
not upload scans. JSON/HTML reports are written locally only when
`--report-dir` is set. They contain the contracted tool request, tool response,
and read-back evidence for failures. Named secret fields, recognized token
patterns, and secret-looking environment-variable values are redacted before
stdout or disk output. Redaction is best effort: an arbitrary secret embedded
in an unmarked text field may remain. Review reports before sharing. On POSIX,
files are created with mode 0600; account-level file permissions on Windows
depend on the directory ACL.

HTTP read-back rejects dynamic hosts, non-HTTPS URLs outside loopback, and
redirects. An HTTP 401/403 is UNKNOWN. GitHub 404 is UNKNOWN by default because
missing access and a missing record can look alike. If you explicitly opt a
missing status into FAIL, first confirm that the read-only identity can see
the relevant test-account records.

Use a separate, least-privilege read token where the provider permits it.
Pass credentials through environment variables, never in a contract file or
chat. Do not commit generated reports, tokens, or customer data.
