# spec.md — Fourgate Runtime Wrap (MVP)

Version: v2 (patch-list merge). Status: draft for Clarify. Behaviour only. No stack, schema, or file layout.

---

## Goal

Agents acting through third-party MCP servers regularly receive results that are protocol-successful and semantically wrong — no payload, a "done" with no effect, an auth failure wrapped in a 200, a payload too large to reason over. The agent then acts on that result as if it were true. Fourgate sits inline on the live `tools/call` path, host-side, and replaces the result the *model* reads with a structured verdict it can branch on.

The unit of value is the changed next model turn, not a record of the incident. A correct implementation changes what the agent does even with logging and alerting fully disabled and no network available.

Scope of the wrap for MVP: **command-configured local stdio MCP servers.** Extension-installed and remote/URL-configured servers are not covered.

---

## User scenarios

**S1 — Wrap a command-configured local stdio server (target: first protected `tools/call` in under 10 minutes).**
Hifza has a working third-party MCP server configured in her client as a local stdio server with an explicit command block. She installs Fourgate and edits only that server's existing configuration block so the server is launched under Fourgate. She restarts the client. The server's tools appear exactly as before — same names, same schemas, same descriptions. Nothing about the third-party server, its source, or its credentials is modified. Her next real tool call traverses Fourgate before the model sees the result.

**S2 — Prove the wrap is live without waiting for a real failure.**
A healthy session is byte-identical to an unwrapped one, so she cannot tell from normal use whether Fourgate is in the path. She runs a self-check that drives the *same* intercept-and-rewrite path a real call uses and surfaces the resulting verdict at the client/model boundary. A printed sample would not have told her anything; a verdict arriving through the real path does.

**S3 — Silent empty during a real task.**
The agent calls a document-fetch tool whose baseline declares that successful terminal responses contain payload. The server returns success with no interpretable content. The agent receives `{silent_empty, <tool>, <derived evidence>, stop}` and halts, reporting that the tool returned nothing, rather than summarizing nothing.

**S4 — Auth expires mid-task.**
Twenty calls in, the server begins returning success bodies whose control surface carries a re-authentication signal. The agent receives `{auth_expiry, …, ask_user}`. It stops the loop and asks Hifza to re-auth, instead of retrying eighteen times or reporting the task complete.

**S5 — A legitimate empty result.**
The agent searches for tickets matching a filter. There are genuinely none. The server returns a well-formed zero-result payload. Fourgate passes it through untouched. The agent correctly reports zero matches. **No verdict, no alert, no annotation.** This scenario failing is a more serious defect than S3 failing.

**S6 — Fourgate itself breaks.**
Its classification path errors or hangs. The tool result reaches the agent unchanged and within the latency budget. The session continues. Hifza notices nothing.

---

## Functional requirements

### Path and transparency

**FR-1 — Inline pass-through fidelity.** Fourgate MUST sit on the live path between the client and the wrapped local stdio server for every `tools/call`; when no verdict is emitted it MUST forward the upstream result byte-identically, and it MUST forward all non-`tools/call` traffic byte-identically in both directions.
*Fails if ignored:* a passive recorder alongside the path satisfies the requirement.

**FR-2 — Inline fail-open, bounded.** On the same live path used for verdict insertion, classification MUST complete within 100 ms wall-clock per result; on internal error, timeout, budget exhaustion, or unparseable result, Fourgate MUST deliver the original result unchanged no later than that budget. It MUST NOT drop, block, or partially mutate a result under any internal failure.

**FR-3 — In-band delivery.** A verdict MUST be delivered inside the tool result that the client feeds back to the model. It MUST NOT be delivered only to a log, file, terminal, webhook, or alert channel.
*Fails if ignored:* run with alerting disabled and network egress blocked; the model still receives the verdict, or the build is wrong.

**FR-4 — Attributed rewrite.** The model-visible verdict MUST identify Fourgate as its author, distinguishably from content the tool produced.
*Fails if ignored:* the agent tells the user "the API reported an authentication error" when the API reported nothing of the kind.

**FR-5 — Additive by default.** Where original content exists, the verdict MUST be attached alongside it, positioned to be read first. Fourgate MUST NOT discard tool content the agent could still use. (`silent_empty` is the degenerate case: there is no content to preserve.)

### Classification

**FR-6 — Deterministic model-visible decision.** The inline classification decision that determines whether and which verdict the model receives MUST be identical for a given result and valid baseline across repeated runs, with no inference call, embedding, sampled output, or outbound model traffic in that decision path.

**FR-7 — Exactly one in-band verdict.** Every `tools/call` result matching one or more kinds MUST receive exactly one model-visible verdict before model consumption, using fixed precedence `auth_expiry → fake_success → silent_empty → token_bloat`.
*Fails if ignored:* zero verdicts on a matching result is a pass, which is the observability-product loophole.

**FR-8 — `silent_empty` fires only on known-abnormal absence.** A successful terminal result with no interpretable payload MUST receive a `silent_empty` verdict only when the tool's baseline or declared output contract establishes that successful terminal responses contain payload. Explicit zero-result payloads and tools baselined as legitimately empty MUST pass through unchanged. An empty collection may count as shape regression only when the baseline marks the missing companion count/status field as **required**, not merely observed.

**FR-9 — `fake_success` uses only three structural failures.** A terminal successful result MUST receive `fake_success` only when a pre-existing baseline declares an effect witness as required and the current result violates it by exactly one of three conditions: (1) the required path is absent, (2) the required path is null where the baseline requires non-null, (3) the required path is empty where the baseline requires non-empty. No other rule, tool-name inference, verb inference, or value-semantic judgment may trigger `fake_success`.

**FR-10 — `auth_expiry` is in-band and signal-scoped.** A result MUST receive `auth_expiry` when an authentication/authorization failure signal occurs in the result's error, status, authentication, redirect, or equivalent control surface — including unstructured error text — but the same words or URLs appearing only inside ordinary returned user/tool data MUST NOT trigger it.

**FR-11 — `token_bloat` is explicit-budget-only for MVP.** A result MUST receive `token_bloat` only when its model-bound size exceeds an explicitly configured per-tool budget. No global, default, learned, or baseline-derived size budget may trigger the verdict. The verdict MUST report observed size against budget, and original content MUST remain intact with no truncation.

**FR-12 — Unbaselined degradation is fail-open.** Without a valid baseline, Fourgate MUST still emit in-band `auth_expiry` and explicitly budgeted `token_bloat` verdicts when they match, but MUST NOT emit `fake_success`, shape-regression `silent_empty`, or `silent_empty` for an otherwise ambiguous empty-success response lacking a declared non-empty output contract.

**FR-21 — Non-terminal exclusion.** A result explicitly reporting a non-terminal state such as accepted, queued, pending, running, processing, or in-progress in its status/control surface MUST NOT receive `fake_success`.

**FR-22 — Baseline authority.** Baseline-dependent classification may rely only on fields and constraints the baseline marks as **required**; a field merely observed in a previous successful result MUST NOT become a required witness or shape constraint.

**FR-23 — Baseline compatibility.** If the current tool identity or exposed tool contract no longer matches the baseline used to classify it, all baseline-dependent detections MUST degrade to pass-through until a compatible baseline exists.

**FR-25 — Bloat measurement contract.** `token_bloat` configuration, evidence, and acceptance tests MUST use one explicitly defined model-bound size unit, so the same result cannot be under-budget by one measurement and over-budget by another.

### Contract

**FR-13 — Fixed in-band contract.** Every matched classification MUST produce one model-visible verdict containing exactly `kind`, `tool`, `evidence`, and `recovery`, with `kind` restricted to `silent_empty | fake_success | auth_expiry | token_bloat`.

**FR-14 — Machine-readable in-band recovery.** Every model-visible verdict MUST carry `recovery` as one of `stop | ask_user | retry_once`, with no prose and no guarantee of resolution. Default mappings: `silent_empty → stop`, `fake_success → stop`, `auth_expiry → ask_user`, `token_bloat → retry_once`. `retry_once` is advisory only in MVP.
*Known weakness, deliberately shipped:* an identical retry can buy the same oversized result twice. If tests show agents act on `retry_once` literally for `token_bloat`, that mapping changes to `stop`.

**FR-15 — Redacted model-visible evidence.** Whenever a classification matches, the `evidence` placed in the model-visible verdict — and any optional log or alert derived from it — MUST contain only computed structural facts, and MUST contain no tool argument value, returned field value, credential, secret-bearing URL, or user content.

**FR-16 — In-band source identity.** Every model-visible verdict MUST identify the wrapped-server/tool pair unambiguously, so concurrent servers exposing identically named tools cannot be confused.

### Operation

**FR-17 — Command-configured stdio wrap.** Enabling Fourgate for an existing command-configured local stdio server MUST require editing only that server's existing client configuration block. After restart, every `tools/call` result for that server MUST traverse Fourgate before model consumption, while server source, credentials, prompts, tool names, schemas, and descriptions remain unchanged.

**FR-18 — Path-verifying self-check.** The self-check MUST exercise the same live intercept-and-rewrite path used for real `tools/call` responses and surface the resulting verdict at the client/model boundary. Printing a standalone sample object, log entry, or dashboard preview does not satisfy this requirement.

**FR-19 — Suppression restores pass-through.** For a suppressed tool/kind pair, a result that would otherwise have received an in-band verdict MUST instead reach the client/model byte-identically, with no verdict, annotation, or alert.

**FR-20 — Alerting cannot affect model behavior.** Alerting MUST default off, and for the same captured matching result the client/model-visible output MUST be identical whether alerting is enabled, disabled, failing, or network-blocked.

**FR-24 — Call isolation.** Under concurrent, interleaved, cancelled, or out-of-order calls, a verdict MUST bind only to the originating server/tool call, and MUST NEVER be synthesized for a cancelled call or for a call that produced no result.

**FR-26 — Loud startup failure.** If Fourgate cannot start the wrapped server, the client MUST receive an explicit startup failure and MUST NOT observe a silently healthy server with zero tools.

---

## Edge cases & rules

- **Legitimate empty search (hard rule).** A zero-result payload is a correct answer, never flagged on shape alone. FR-8 and FR-12 govern. This is the highest-cost false positive in the product and the one that gets Fourgate uninstalled.
- **Unbaselined void success.** A valid notify or delete tool returning no content has no declared non-empty contract, so it passes through (FR-8, FR-12).
- **Optional zero-result metadata.** A payload omitting an optional field seen in a baseline is not shape regression; only a baseline-required field counts (FR-22).
- **Async success variant.** A valid asynchronous invocation returning a pending state is excluded from `fake_success` outright (FR-21).
- **Idempotent success variant.** A create/upsert returning an already-exists outcome is judged only against the three structural conditions in FR-9, never against value semantics.
- **Tool-version drift.** A baseline that no longer matches the exposed tool contract degrades to pass-through rather than condemning every call (FR-23).
- **Legitimate large export.** Size is never inferred from history; only an explicitly configured per-tool budget can fire `token_bloat` (FR-11).
- **Auth prose inside returned data.** Auth language inside ordinary tool data is data, not a control-surface signal (FR-10).
- **Non-text and binary content.** Absence of *text* is not `silent_empty` when non-text content is present. Size for these results is measured in the single unit defined under FR-25.
- **Client-cancelled calls and dead transports.** No verdict is synthesized (FR-24). A server crash mid-call is a hard failure the client's existing error path handles.
- **Fourgate cannot start.** Fail-open is a runtime property and cannot cover startup; startup failure is explicit and loud (FR-26).
- **Repeated identical failures in one session.** The model receives the verdict every time. Deduplicating repetition is an alert-channel concern only, never a reason to withhold an in-band verdict.

---

## Out of scope

Not in this MVP, and not deferred-but-implied:

- Gateway functions: routing, tool allowlisting, rate limiting, policy enforcement, approval gates, multi-server aggregation.
- Identity: SSO, OAuth termination, credential storage, token issuance, per-user authorization.
- A human dashboard, UI, or health-score product. Alerting is a single optional side-channel, not a surface.
- Identity-token leak scanning or secret detection as a product feature. Redaction under FR-15 constrains Fourgate's own output; it is not a scanner.
- Semantic correctness of tool results: whether returned data is right, current, or complete.
- Native file upload, hosted paste UI, web console.
- Node/TS server-side integration; remote, URL-configured, or extension-installed MCP servers; any transport beyond host-side command-configured local stdio.
- Team accounts, seats, shared workspaces, org-level policy.
- Replacing or deprecating the preflight CLI. It stays and remains free; the runtime wrap is the paid product.
- **Baseline-derived or learned `token_bloat` budgets.** Explicit configuration only (FR-11).
- **Live or session-learned baselines.** Baselines come from preflight only.
- **Truncation of oversized results,** including opt-in. Annotate-only.
- **Runtime feature gating by kind or call volume.** All four kinds behave identically in the paid runtime.
- **Token-cost prevention as a claim.** Annotate-only `token_bloat` detects a payload that has already occupied context; it does not reclaim it, and MUST NOT be described as if it does.

---

## Acceptance criteria

**Pass-through and inline placement**
- [ ] A healthy wrapped session's client-visible transcript is byte-identical to the unwrapped session's, including tool list and all non-`tools/call` traffic. *(FR-1, FR-17)*
- [ ] Fourgate is demonstrably on the path, not beside it: with Fourgate stopped, `tools/call` does not complete. *(FR-1)*
- [ ] With classification faults injected, every result still reaches the client unchanged within 100 ms. *(FR-2)*
- [ ] The self-check surfaces a verdict at the client/model boundary through the real intercept path. *(FR-18)*
- [ ] A user with a working command-configured local stdio server reaches that verdict in under 10 minutes, timed, without editing the server. *(FR-17, FR-18)*
- [ ] Fourgate failing to start the wrapped server produces an explicit client-visible failure, not a zero-tool healthy server. *(FR-26)*

**Detection — true positives**
- [ ] With alerting disabled and egress blocked, a baselined tool returning no interpretable payload yields `{silent_empty, …, stop}` to the model. *(FR-3, FR-8, FR-13, FR-14, FR-20)*
- [ ] A 200-wrapped expired-credential control surface yields `{auth_expiry, …, ask_user}`; an unstructured auth error string does too. *(FR-10)*
- [ ] A baseline-required witness that is absent, null, or empty yields `{fake_success, …, stop}` — and no other condition does. *(FR-9)*
- [ ] A result exceeding that tool's explicitly configured budget yields `{token_bloat, …, retry_once}` with original content intact and observed size stated against budget. *(FR-11, FR-25)*
- [ ] A result matching both auth and bloat conditions yields exactly one verdict: `auth_expiry`. *(FR-7)*

**Detection — blocking false-positive cases (each must produce zero verdicts)**
- [ ] Legitimate zero-result search on a baselined search tool. *(FR-8)* — **blocking**
- [ ] Unbaselined void success: a valid notify/delete returning no content. *(FR-8, FR-12)* — **blocking**
- [ ] Optional zero-result metadata: an empty collection omitting a field the baseline marks optional. *(FR-8, FR-22)* — **blocking**
- [ ] Async success variant: baseline requires an entity ID, the valid async call returns a processing state. *(FR-21)* — **blocking**
- [ ] Idempotent success variant: create/upsert returns an already-exists outcome instead of a new identifier. *(FR-9)* — **blocking**
- [ ] Tool-version drift: upstream renames a required field, stale baseline present. *(FR-23)* — **blocking**
- [ ] Legitimate large export with no configured budget for that tool. *(FR-11)* — **blocking**
- [ ] Auth prose inside returned data: a document or search result containing session-expired language and a login URL. *(FR-10)* — **blocking**
- [ ] Binary/image-heavy valid response measured under the FR-25 unit. *(FR-11, FR-25)* — **blocking**

**Contract and containment**
- [ ] Every emitted verdict carries exactly the four keys, with `kind` and `recovery` drawn from their closed sets. *(FR-13, FR-14)*
- [ ] A canary secret placed in tool arguments and result body appears in no verdict, log, or alert. *(FR-15)*
- [ ] Classifying one captured result 100 times yields one identical verdict, with zero outbound model calls. *(FR-6)*
- [ ] Two concurrently wrapped servers exposing identically named tools produce unambiguous verdicts. *(FR-16)*
- [ ] Under interleaved and cancelled calls, no verdict binds to the wrong call and none is synthesized for a cancelled call. *(FR-24)*
- [ ] Suppressing a kind for a tool returns an otherwise-matching result to byte-identical pass-through. *(FR-19)*
- [ ] For one captured matching result, model-visible output is identical across alerting enabled, disabled, failing, and network-blocked. *(FR-20)*
- [ ] A verdict is attributable to Fourgate by the model, not to the tool. *(FR-4)*
- [ ] Where original content exists, it survives the rewrite and the verdict reads first. *(FR-5)*

---

## Decisions closed (were Open Decisions 1–6)

| # | Decision | Effect on this spec |
|---|---|---|
| 1 | Contract versioning is **out-of-band**; the four-key verdict is frozen as v1 | No fifth key; `kind` enum uncorrupted (FR-13) |
| 2 | Truncation: **annotate-only** | FR-11; truncation moved to Out of scope |
| 3 | Baselines: **preflight-only** | FR-12, FR-22, FR-23; session learning moved to Out of scope |
| 4 | Packaging: **free preflight CLI, paid runtime wrap**, no free-runtime gating | No behavioural difference by tier; gating moved to Out of scope |
| 5 | `retry_once` is a **hint only**; Fourgate stays stateless | FR-14; no retry tracking |
| 6 | Latency budget: **100 ms wall-clock per result** | FR-2 |

No open decisions remain for Clarify.