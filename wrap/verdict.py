#!/usr/bin/env python3
import json

ATTRIBUTION_MARKER = "[FOURGATE]"


def _item(verdict):
    verdict_text = f"{ATTRIBUTION_MARKER} {json.dumps(verdict, sort_keys=True)}"
    return {"type": "text", "text": verdict_text}


def attach(result_obj, verdict):
    """Legacy silent_empty rewrite: replace the empty result entirely."""
    rewritten = dict(result_obj)
    rewritten["result"] = {
        "content": [_item(verdict)],
        "isError": False,
    }
    return rewritten


def attach_prepend(result_obj, verdict):
    """Outcome Guard rewrite: verdict first, original connector result preserved.

    This is deliberately different from ``attach``. Outcome Guard operates on
    useful success content (for example ``Created ISSUE-123``), so the model
    must see the deterministic Fourgate verdict *before* that content without
    losing the connector's own evidence or structuredContent.
    """
    rewritten = dict(result_obj)
    original_result = result_obj.get("result")
    if not isinstance(original_result, dict):
        original_result = {}
    new_result = dict(original_result)
    content = original_result.get("content")
    original_content = list(content) if isinstance(content, list) else []
    new_result["content"] = [_item(verdict)] + original_content
    rewritten["result"] = new_result
    return rewritten


def to_line(rewritten_obj):
    return json.dumps(rewritten_obj).encode("utf-8") + b"\n"
