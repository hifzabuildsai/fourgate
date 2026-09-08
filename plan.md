# plan.md — Runtime Wrap, wedge slice

Implementation plan for the smallest slice of `specs/runtime-wrap.md` that proves the wedge: a real
tool result the model would have believed is replaced, on the live path, by a verdict it can branch on.

Nothing here is written yet. This document is the contract for what gets built and how it gets proven.

---

## 1. Slice boundary

**In scope (the four things that make the wedge real):**

| # | Thing | Spec |
|---|-------|------|
| 1 | Wrap a command-configured local stdio server, inline on `tools/call` | FR-1, FR-17 |
| 2 | Fail-open within a 100 ms wall-clock budget | FR-2, FR-6 |
| 3 | Path-verifying self-check | FR-18 |
| 4 | `silent_empty` only, plus byte-identical pass-through everywhere else | FR-3, FR-4, FR-5, FR-8, FR-12, FR-13, FR-14, FR-15, FR-16 |

**Deliberately not in this slice** (each is a later slice, not a hidden assumption):

- `fake_success` (FR-9), `auth_expiry` (FR-10), `token_bloat` (FR-11, FR-25). Precedence (FR-7) is
  scaffolded as an ordered constant but is trivially satisfied with one kind implemented.
- Shape-regression `silent_empty` — the "empty collection missing a baseline-**required** companion
  field" branch of FR-8. This slice fires only on *total absence of interpretable payload*. Shape
  regression is where the blocking false positives live (spec edge cases: legitimate empty search,
  optional zero-result metadata); it needs a real baseline generator, not a hand-authored file.
- Suppression (FR-19), alerting (FR-20), loud startup failure (FR-26), FR-21/FR-22 (both are
  `fake_success`-only concerns), full cancellation semantics (FR-24 — see §5 for the partial).
- Baseline **generation**. Baselines in this slice are hand-authored JSON with a format chosen to be
  what a preflight-derived baseline would later emit. `checker/preflight.py` is not modified and no
  preflight identity work is expanded.

**Constraints honoured:** no gateway (single server per wrap process, no routing/allowlist/policy), no
Supabase and no network in the critical path (the wrap imports no HTTP client at all), no LLM judge
(classification is a pure function), no dashboard.

---

## 2. Design decisions that shape the code

These are the non-obvious ones. Getting any of them wrong makes an acceptance criterion unprovable.

**D1 — Pass-through forwards the original bytes, never a re-serialization.**
`json.loads` → `json.dumps` changes key order and whitespace, so a "healthy session is byte-identical"
claim would fail on formatting alone. The proxy forwards the raw line it received and parses only a
*copy* for inspection. A re-serialized line is emitted **only** when a verdict is actually attached.

**D2 — Binary-mode stdio on both ends.**
Text-mode stdio on Windows translates `\n` → `\r\n`, which breaks byte-identity. Both directions read
and write `bytes`; JSON is decoded from a copy for inspection only. (Ties to D1.)

**D3 — Child stderr is inherited, not piped.**
Server logs keep reaching the client's log the way they did unwrapped, and there is no pipe for a
chatty server to deadlock on — the exact failure `checker/preflight.py` had to solve with a drain
thread. The wrap does not need that thread because it never owns the stderr pipe.

**D4 — Reader threads, not `selectors`.**
Same cross-platform reason documented in `checker/preflight.py:19` — `select()` on Windows does not
accept subprocess pipes. Two pump threads: client→server and server→client.

**D5 — The 100 ms budget is enforced by a real timeout, not by "it's fast."**
Classification runs in a worker thread with `future.result(timeout=0.1)`. Timeout, exception, or
unparseable result → forward the original bytes. The budget is measured from receipt of the upstream
line, so a slow classify cannot push total added latency past the budget.

**D6 — One classify+rewrite function, called by both the live path and the self-check.**
FR-18 is only satisfiable if there is exactly one such function and the self-check cannot reach a
different one. The self-check does not call it directly at all — it drives a real wrapped server over
real stdio (see §4, step 7).

**D7 — Verdict binds to `(server_label, tool_name)` resolved from the request id.**
The wrap records `id → tool name` when a `tools/call` request passes client→server, and consumes it
when the matching response passes server→client. No result, no verdict; unknown id, no verdict. This
is what makes FR-16 and the routing half of FR-24 fall out for free.

**D8 — "No interpretable payload" is defined structurally and narrowly.**
A success response (`result` present, no `error`, `result.isError` not true) counts as empty only when:
`content` is absent or `[]`, **and** no non-text content item exists (an image-only result is not
empty — spec edge case), **and** every text item strips to empty, **and** `structuredContent` is
absent or `{}`. Anything else — including `{"results": [], "count": 0}` — is a payload and passes
through. This is the rule that keeps the highest-cost false positive off the table.

**D9 — Baseline compatibility check is minimal but present.**
The wrap snoops `tools/list` responses (read-only, still forwarded raw) to compute a contract hash per
tool from `name` + `inputSchema`. If the baseline's recorded hash differs, all baseline-dependent
detection degrades to pass-through (FR-23). ~20 lines, and it prevents a stale baseline condemning a
renamed tool on every call.

---

## 3. Files to add / change

### Add — `wrap/` (flat scripts, matching the existing `checker/` convention; no packaging)

| File | Contents |
|------|----------|
| `wrap/wrap.py` | Entry point + proxy. Parses `--server-label`, `--baseline`, `--selfcheck`, then `-- <original command…>`. Spawns the target, runs both pump threads, tracks `id → tool`, snoops `tools/list`, calls the classify/rewrite gate on `tools/call` responses under the 100 ms budget. |
| `wrap/classify.py` | Pure, deterministic. `classify(result_obj, tool_ctx) -> Verdict | None`. Implements D8 + FR-8/FR-12 gating. Imports nothing that touches the network. Holds the FR-7 precedence tuple. |
| `wrap/baseline.py` | Loads/validates the baseline JSON; `lookup(tool_name)` returns the tool's contract or `None`; contract-hash comparison for FR-23. |
| `wrap/verdict.py` | Builds the fixed four-key verdict (FR-13), maps `kind → recovery` (FR-14), and does the additive rewrite: verdict content item prepended, original items preserved (FR-4, FR-5). Single source of the `[FOURGATE]` attribution marker. |
| `wrap/selfcheck.py` | FR-18. Spawns `wrap.py` over `fixtures/silent_server.py` and speaks real JSON-RPC to it as a client would. Contains a minimal Windows-safe line reader copied from `checker/preflight.py` (copied, not refactored out — see §6 R3). |

### Add — fixtures & baselines

| File | Contents |
|------|----------|
| `fixtures/silent_server.py` | Small stdio MCP server. `fetch_document` returns success with no content (drives S3 and the self-check). `search_tickets` returns a well-formed zero-result payload (drives the blocking false-positive test). `notify` returns void success (unbaselined case). |
| `fixtures/baselines/silent_server.json` | Hand-authored. Declares `payload_required: true` for `fetch_document`, `payload_required: false` for `search_tickets`, and **no entry** for `notify`. Includes per-tool `contract_hash`. |

Baseline format (frozen here so a later preflight-derived baseline is drop-in):

```json
{
  "baseline_version": 1,
  "server": "silent-demo-server",
  "tools": {
    "fetch_document": { "contract_hash": "sha256:…", "payload_required": true }
  }
}
```

### Add — `tests/` (pytest)

`tests/test_passthrough.py`, `tests/test_failopen.py`, `tests/test_classify.py`,
`tests/test_verdict_contract.py`, `tests/test_selfcheck.py`, `tests/test_isolation.py`.
Mapping in §4.

### Change

| File | Change |
|------|--------|
| `requirements.txt` | Add `pytest` (dev). Runtime stays dependency-free — the wrap uses stdlib only. |
| `README.md` | One section: how to edit a single client config block to wrap a server, and how to run the self-check. Written last, after the self-check demonstrably passes. |
| `checker/preflight.py` | **No change.** |

Config edit the README documents (FR-17 — only the server's own block changes):

```json
{ "command": "python3", "args": ["wrap/wrap.py", "--baseline", "…json", "--", "python3", "server.py"] }
```

---

## 4. Order of work

Each step ends with its tests green before the next starts.

**Step 1 — Raw byte proxy.**
`wrap/wrap.py` spawns the target and pumps both directions as bytes (D1–D4). No parsing yet.
→ `test_passthrough.py::test_healthy_session_byte_identical`, `::test_tool_list_unchanged`.

**Step 2 — On-path proof.**
Confirm the wrap is load-bearing: with the wrap process killed, `tools/call` does not complete.
→ `test_passthrough.py::test_call_does_not_complete_without_wrap`.

**Step 3 — Request/response correlation.**
Parse a copy of each line; record `id → tool` on `tools/call` requests, resolve on responses (D7).
Still zero rewrites. → `test_isolation.py::test_interleaved_ids_bind_to_correct_tool`,
`::test_no_verdict_for_call_with_no_result`.

**Step 4 — Fail-open gate.**
Insert the classify gate as a no-op returning `None`, wrapped in the 100 ms future + `except
Exception` (D5). Add `FOURGATE_FAULT=raise|hang` (test-only env hook) to inject faults.
→ `test_failopen.py::test_raise_passes_through`, `::test_hang_passes_through_within_budget`.

**Step 5 — Baseline + classifier.**
`wrap/baseline.py`, `wrap/classify.py`, the `tools/list` contract-hash snoop (D8, D9). Pure-unit
tested first, then in-process. → all of `test_classify.py`.

**Step 6 — Verdict + rewrite.**
`wrap/verdict.py`, wired into the gate. First end-to-end `silent_empty` through the live path.
→ `test_verdict_contract.py`, `test_classify.py::test_silent_empty_end_to_end`.

**Step 7 — Self-check.**
`wrap/selfcheck.py`, reachable as `python3 wrap/wrap.py --selfcheck`. Spawns the wrap over
`fixtures/silent_server.py`, sends `initialize` / `tools/list` / `tools/call` over real stdio, and
prints the verdict **as received back from the wrap's stdout**. Non-zero exit if no verdict arrives.
→ `test_selfcheck.py`.

**Step 8 — README section + manual timing run.**
Time a cold setup against the 10-minute acceptance bar (§5, manual).

---

## 5. Test plan, mapped to acceptance criteria

Spec criteria this slice claims. Anything not listed is out of slice per §1.

### Pass-through and inline placement

| Acceptance criterion | Test | Spec |
|---|---|---|
| Healthy wrapped session byte-identical to unwrapped, tool list and non-`tools/call` traffic included | `test_passthrough.py::test_healthy_session_byte_identical` — same scripted JSON-RPC session run against `fixtures/clean_server.py` directly and through the wrap; compare raw stdout bytes | FR-1, FR-17 |
| On the path, not beside it | `::test_call_does_not_complete_without_wrap` — wrap killed mid-session, assert the pending `tools/call` never returns | FR-1 |
| Injected classification faults still deliver the original result unchanged within 100 ms | `test_failopen.py::test_raise_passes_through`, `::test_hang_passes_through_within_budget` — `FOURGATE_FAULT` injects an exception and a 5 s sleep; assert bytes identical to unwrapped **and** wall-clock delta < 100 ms | FR-2 |
| Self-check surfaces a verdict at the client/model boundary through the real intercept path | `test_selfcheck.py::test_verdict_arrives_over_real_stdio` — asserts the verdict text appears in the bytes the wrap wrote to its own stdout, not merely in a printed sample | FR-18 |
| Under 10 minutes to first protected call, without editing the server | **Manual**, recorded in the README. Not automatable; the automatable half (server files unmodified) is `test_passthrough.py::test_server_files_untouched` | FR-17, FR-18 |

### Detection — true positive

| Acceptance criterion | Test | Spec |
|---|---|---|
| Baselined tool returning no interpretable payload yields `{silent_empty, …, stop}`, with alerting disabled and egress blocked | `test_classify.py::test_silent_empty_end_to_end` — through the live wrap against `fixtures/silent_server.py`; egress proven by `test_classify.py::test_no_outbound_sockets` (monkeypatched `socket.socket` raises; classification still succeeds) | FR-3, FR-8, FR-13, FR-14, FR-20 |

### Detection — blocking false-positive cases (each must produce **zero** verdicts and byte-identical output)

| Case | Test | Spec |
|---|---|---|
| Legitimate zero-result search on a baselined tool | `test_classify.py::test_zero_result_payload_passes_through` | FR-8 |
| Unbaselined void success (`notify` with no baseline entry) | `::test_unbaselined_void_success_passes_through` | FR-8, FR-12 |
| Baseline present but `payload_required: false` | `::test_payload_not_required_passes_through` | FR-8, FR-12 |
| Non-text/binary-only content, zero text items | `::test_binary_only_result_is_not_empty` | FR-8 (edge case) |
| Tool-version drift — live `inputSchema` no longer matches the baseline hash | `::test_contract_drift_degrades_to_passthrough` | FR-23 |

### Contract and containment

| Acceptance criterion | Test | Spec |
|---|---|---|
| Exactly four keys; `kind` and `recovery` from their closed sets | `test_verdict_contract.py::test_exactly_four_keys`, `::test_closed_enums` | FR-13, FR-14 |
| Canary secret in tool arguments and result body appears in no verdict | `::test_canary_absent_from_verdict` — canary planted in both, asserted absent from the full serialized verdict | FR-15 |
| One captured result classified 100× yields one identical verdict, zero outbound model calls | `test_classify.py::test_deterministic_100_runs` + `::test_no_outbound_sockets` | FR-6 |
| Verdict identifies the server/tool pair unambiguously | `test_verdict_contract.py::test_tool_field_is_server_qualified` — `tool` is `"<server_label>/<tool_name>"`; two wrap instances with different labels exposing the same tool name produce distinguishable verdicts | FR-16 |
| Verdict attributable to Fourgate, not the tool | `::test_attribution_marker_present` | FR-4 |
| Where original content exists, it survives and the verdict reads first | `::test_rewrite_is_additive_and_first` — unit test on `verdict.attach()` with content present (`silent_empty` is the degenerate no-content case) | FR-5 |
| No verdict binds to the wrong call; none synthesized for a call with no result | `test_isolation.py::test_interleaved_ids_bind_to_correct_tool`, `::test_no_verdict_for_call_with_no_result` | FR-24 (partial — cancellation semantics deferred) |

---

## 6. Risks

**R1 — Byte-identity is easy to lose accidentally.** Any future "just normalize the JSON" change breaks
the strongest acceptance criterion. D1/D2 are load-bearing; `test_healthy_session_byte_identical`
compares raw bytes so a regression fails loudly rather than subtly.

**R2 — The hand-authored baseline is a stub, and the slice must not pretend otherwise.** It exists to
prove the runtime path, not to prove baseline quality. Because shape-regression `silent_empty` is out
of slice, a wrong baseline can at worst cause a false verdict on a tool the author explicitly marked
`payload_required: true`.

**R3 — Duplicated JSON-RPC client code in `wrap/selfcheck.py`.** Refactoring the reader out of
`checker/preflight.py` would touch the shipped free tool for no benefit to this slice. Accept ~40
duplicated lines; revisit if a third caller appears.

**R4 — Deferred FR-26 (loud startup failure).** If the wrapped command is wrong, the client currently
sees whatever the failure looks like by default. Cheap to add and the natural next slice, but not
required to prove the wedge.
