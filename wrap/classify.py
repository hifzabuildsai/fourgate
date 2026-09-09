#!/usr/bin/env python3
"""
Fourgate — classification (plan.md Step 5 / Step 5a)

Pure and deterministic: no I/O, no network, no randomness. The same
(result, tool, contract) triple classifies the same way every time (FR-6).

This step implements exactly one kind — `silent_empty` — and exactly its
narrow "total absence of interpretable payload" branch (D8), not shape
regression (an empty collection missing a baseline-required companion
field). Shape regression needs a real baseline generator and stays out of
this slice (plan.md Sec.1). Once other kinds exist, FR-7's fixed
precedence (auth_expiry -> fake_success -> silent_empty -> token_bloat)
governs which one wins when several match; with one kind implemented
there is nothing yet to arbitrate between.

Contract shape (per tool, from a loaded baseline — see wrap/baseline.py):

    {
      "required_fields": ["content"],
      "observed_fields": ["count", "results"]
    }

`required_fields` is the *only* thing this module ever reads (FR-22): a
field merely recorded in `observed_fields` — something seen in a past
successful call but never declared mandatory — can never constrain a
classification decision. "content" is the sentinel this step checks for:
its presence in `required_fields` is what "the baseline declares this
tool's successful terminal responses contain payload" (FR-8) means
structurally. A future shape-regression classifier would consult other
field names the same way; this step never needs to.
"""

PAYLOAD_FIELD = "content"

VALID_KINDS = ("silent_empty", "fake_success", "auth_expiry", "token_bloat")
RECOVERY_BY_KIND = {
    "silent_empty": "stop",
    "fake_success": "stop",
    "auth_expiry": "ask_user",
    "token_bloat": "retry_once",
}


def classify(result_obj, tool_name, contract):
    """Return a verdict dict, or `None` if nothing matches.

    FR-8 / FR-12: a `silent_empty` verdict is possible only when the
    baseline declares — via `"content"` appearing in this tool's
    `required_fields` — that its successful terminal responses contain
    payload. No baseline, no entry for this tool (`contract` is `None`),
    or a `required_fields` list that doesn't include `"content"`, all
    resolve to `None`: there is no established contract to violate.
    """
    if not contract:
        return None

    required_fields = contract.get("required_fields") or []
    if PAYLOAD_FIELD not in required_fields:
        return None

    if not _is_empty_result(result_obj):
        return None

    return {
        "kind": "silent_empty",
        "tool": tool_name,
        "evidence": _evidence(result_obj),
        "recovery": RECOVERY_BY_KIND["silent_empty"],
    }


def _is_empty_result(result_obj):
    """D8 — a successful terminal result counts as having no interpretable
    payload only when: `content` is absent or `[]`, AND no non-text
    content item exists (an image-only result is not empty), AND every
    text item strips to empty, AND `structuredContent` is absent or `{}`.

    Anything else — including a well-formed zero-result payload such as
    `{"results": [], "count": 0}` carried in a text item or in
    `structuredContent`, or a response merely omitting a field the
    baseline records as observed-not-required — is a payload, not an
    absence of one.
    """
    result = result_obj.get("result")
    if not isinstance(result, dict):
        return False
    if result.get("isError"):
        return False  # an error result is never a silent_empty candidate

    content = result.get("content")
    if content:
        if not isinstance(content, list):
            return False
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text":
                return False  # any non-text content item -> not empty
            if (item.get("text") or "").strip():
                return False  # non-empty text -> not empty

    if result.get("structuredContent"):
        return False

    return True


def _evidence(result_obj):
    """FR-15 — computed structural facts only, never a payload value,
    tool argument, credential, or user content."""
    result = result_obj.get("result") or {}
    content = result.get("content")
    return {
        "content_present": bool(content),
        "content_item_count": len(content) if isinstance(content, list) else 0,
        "structured_content_present": bool(result.get("structuredContent")),
    }
