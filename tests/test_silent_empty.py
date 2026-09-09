"""
plan.md Step 5a — silent_empty classifier against fixture baselines
(FR-8, FR-12, FR-22).

Pure unit tests against wrap.classify.classify() and wrap.baseline,
loading a hand-written baseline fixture from tests/fixtures/ rather than
building contract dicts inline — the same shape a real (future,
preflight-emitted) baseline would have. The gate in wrap.py still
discards every verdict it gets (that's Step 6), so there's nothing new
visible on the wire to assert on — what's real now is the classification
decision itself.

tests/fixtures/silent_server_baseline.json declares, per tool:
  - fetch_document: required_fields=["content"], nothing observed.
    A plain "successful responses always carry payload" tool.
  - search_tickets: required_fields=["content"],
    observed_fields=["results", "count"]. A search tool whose baseline
    still requires *some* content (even a zero-result answer is a
    structured response), with "results"/"count" recorded as merely
    observed — never required — companion fields.
  - list_items: required_fields=["content"],
    observed_fields=["next_page_token"]. Same shape, different observed
    field, to keep the "omits an optional field" case distinct from the
    "describes zero results" case above.
  - notify: absent from the baseline entirely (no entry) — the
    unbaselined-tool case.

Three blocking false-positive cases, each required to produce zero
verdicts (spec: "the highest-cost false positive in the product and the
one that gets Fourgate uninstalled"):

  - legitimate zero-result search: search_tickets' response structurally
    carries content (a well-formed empty-results payload) — D8's narrow
    definition of "no interpretable payload" excludes this even though
    the *content* describes zero results.
  - unbaselined void success: notify has no baseline entry at all, and
    returns genuinely empty content — no established contract, so FR-12
    forbids a verdict regardless of what the response looks like.
  - empty collection omitting an optional field: list_items' response
    carries structuredContent that omits next_page_token — a field the
    baseline only ever recorded as observed, never required (FR-22). The
    collection itself still isn't a total absence of payload, so this
    passes for the same D8 reason as the search case, demonstrating that
    the omitted field played no part in the decision either way.

One additional sanity check (not one of the three named cases) proves the
classifier isn't vacuously always None: the same total-absence shape,
against fetch_document (required_fields includes "content"), does fire.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "silent_server_baseline.json"


def _load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


classify_mod = _load("fourgate_classify", "wrap/classify.py")
baseline_mod = _load("fourgate_baseline", "wrap/baseline.py")


def _response(result):
    return {"jsonrpc": "2.0", "id": 1, "result": result}


EMPTY_RESULT = {"content": [], "isError": False}


def _load_fixture_baseline():
    loaded = baseline_mod.load(str(BASELINE_FIXTURE))
    assert loaded is not None, f"failed to load fixture baseline: {BASELINE_FIXTURE}"
    return loaded


def test_legitimate_zero_result_search_passes_through():
    """FR-8 / D8 — a well-formed zero-result payload is a payload, not an
    absence of one, even though search_tickets' baseline requires
    content."""
    loaded = _load_fixture_baseline()
    contract = baseline_mod.lookup(loaded, "search_tickets")
    assert contract["required_fields"] == ["content"]

    response = _response(
        {
            "content": [
                {"type": "text", "text": '{"results": [], "count": 0}'}
            ],
            "isError": False,
        }
    )

    verdict = classify_mod.classify(response, "search_tickets", contract)

    assert verdict is None


def test_unbaselined_void_success_passes_through():
    """FR-8 / FR-12 — notify has no entry in the baseline at all, so
    there's no established contract, and a genuinely empty response
    still gets no verdict."""
    loaded = _load_fixture_baseline()
    contract = baseline_mod.lookup(loaded, "notify")
    assert contract is None  # confirms notify really is absent from the fixture

    response = _response(EMPTY_RESULT)

    verdict = classify_mod.classify(response, "notify", contract)

    assert verdict is None


def test_empty_collection_omitting_optional_field_passes_through():
    """FR-8 / FR-22 — list_items' baseline records next_page_token as
    merely *observed*, never required. A response that omits it must not
    be constrained by that omission — only required_fields (here just
    "content") is ever consulted, and structuredContent is still
    present."""
    loaded = _load_fixture_baseline()
    contract = baseline_mod.lookup(loaded, "list_items")
    assert "next_page_token" in contract["observed_fields"]
    assert "next_page_token" not in contract["required_fields"]

    response = _response(
        {
            "content": [],
            "structuredContent": {"items": []},  # next_page_token omitted
            "isError": False,
        }
    )

    verdict = classify_mod.classify(response, "list_items", contract)

    assert verdict is None


def test_true_positive_still_fires():
    """Sanity check, not one of the three blocking cases: the same
    total-absence shape as the unbaselined case above, but against
    fetch_document (required_fields includes "content"), must still
    produce a verdict — otherwise the false-positive tests above would
    be vacuous."""
    loaded = _load_fixture_baseline()
    contract = baseline_mod.lookup(loaded, "fetch_document")
    assert contract["required_fields"] == ["content"]

    response = _response(EMPTY_RESULT)

    verdict = classify_mod.classify(response, "fetch_document", contract)

    assert verdict is not None
    assert set(verdict.keys()) == {"kind", "tool", "evidence", "recovery"}
    assert verdict["kind"] == "silent_empty"
    assert verdict["tool"] == "fetch_document"
    assert verdict["recovery"] == "stop"


def test_observed_fields_never_consulted():
    """FR-22, made explicit: a contract whose observed_fields contains
    something that would look alarming if it were treated as a shape
    constraint has zero effect on the outcome — classify() never reads
    it. Only required_fields matters."""
    contract = {
        "required_fields": ["content"],
        "observed_fields": ["this_field_is_never_checked"],
    }
    empty_response = _response(EMPTY_RESULT)
    non_empty_response = _response(
        {"content": [{"type": "text", "text": "hello"}], "isError": False}
    )

    assert classify_mod.classify(empty_response, "fetch_document", contract) is not None
    assert classify_mod.classify(non_empty_response, "fetch_document", contract) is None


def test_baseline_lookup_missing_tool_entry():
    """FR-12 via baseline.lookup(): a baseline exists but has no entry
    for this particular tool (notify) — same "no contract" outcome as no
    baseline at all."""
    loaded = _load_fixture_baseline()

    contract = baseline_mod.lookup(loaded, "notify")

    assert contract is None


def test_baseline_load_missing_file_degrades_to_none(tmp_path):
    """FR-12 — a bad --baseline path must fail open (no baseline), not
    raise and take the wrapped server down with it."""
    missing_path = str(tmp_path / "does_not_exist.json")

    loaded = baseline_mod.load(missing_path)

    assert loaded is None


def test_no_baseline_at_all_passes_through():
    """FR-12 — no baseline loaded (contract lookup itself yields None) is
    the same "no established contract" case as an unbaselined tool."""
    contract = baseline_mod.lookup(None, "fetch_document")
    response = _response(EMPTY_RESULT)

    verdict = classify_mod.classify(response, "fetch_document", contract)

    assert contract is None
    assert verdict is None
