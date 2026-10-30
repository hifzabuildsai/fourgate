# Review card: one GitHub Issue update

Status: **UNCONFIGURED / NOT_RUN**. Fictional sample number 73 and template
strings confer no authority. Complete this card and review the exact copied
scan bytes before authorizing a target call. Keep credential values out of it.

| Review item | Required operator decision |
| --- | --- |
| Owner / disposable account | Name the human owner and authorized disposable repository |
| Record identity | Exact owner/repo and positive Issue number; confirm this is not a PR |
| Request intent | Exact approved title, body and requested state; why this update is wanted |
| Target mapping | Reviewed executable/version, stdio protocol, `issue_write` update schema and actual `{id,url}` success shape |
| Repository binding | Review arguments.owner/repo against the fixed readback.repository; neither is inferred from result prose |
| Read identity | Separate read credential name, known-record visibility and independently established permissions; no secret values |
| Predicate | GET uses the approved request issue_number; observed number/title/body/state equal approved request arguments |
| Evidence budget | Review 1 attempt / 1500 ms in the template; choose bounded GET retries if separately needed |
| Write budget | Exact approved target-call count, target startup effects, disposable scope and separately approved cleanup |
| 404 semantics | Ambiguous by default; missing_is_fail remains false without a reviewed visibility/absence basis |
| Freshness / causality | Record what is independently known; this pack checks neither updated_at nor causal receipt |
| Evidence handling | New output directory, source revision, reviewed contract SHA-256, access/retention and local report review |
| Execution authorization | Human approval of exact target/request/budget; schema readiness is not approval |

If these inputs are unavailable, prepare/review configuration only. Do not
execute the placeholder command or substitute a guessed real server/tool.
