#!/usr/bin/env python3
"""
Fourgate — permanent observation mode (--observe PATH)

Optional, off-by-default side channel. It can never change what the
model sees: wrap.py always writes the client-visible bytes (rewritten or
original) before calling into this module, so a slow or failing observe
write cannot add latency to, or otherwise affect, the live response —
the same principle FR-20 states for alerting, extended here to this
side-channel too.

For every resolved `tools/call` result — a response whose request id was
bound to a tool name by wrap.py's CallTracker, the same binding
wrap/classify.py's gate uses (D7) — append exactly one JSON line to the
path given by `--observe` recording SHAPE ONLY:

    timestamp, server label, tool name, isError, content block count,
    whether any content text is non-empty, whether structuredContent is
    present, total payload size in bytes, and whether FR-8 (silent_empty)
    would have fired against the loaded baseline.

This is the permanent replacement for a temporary debug hook that logged
actual field values and was deleted for exactly that reason. The
distinction is enforced structurally here, not just documented:
`build_record` is never passed a tool argument at all, never reads a
result field's VALUE (only counts, booleans, and byte lengths derived
from it), never reads a file path or URL, and never reads user content.
`fr8_would_fire` is computed by the caller from the real classify gate's
own verdict — this module never imports wrap/classify.py itself, so it
cannot independently reach into any field this record isn't allowed to
carry.

See specs/runtime-wrap.md FR-15 (the redaction discipline this module
extends to every observed result, not only matching ones) and FR-2 /
FR-20 (why this can never affect the live path).
"""

import json
import time


def build_record(line_bytes, result_obj, tool_name, server_label, fr8_would_fire):
    """Compute one shape-only observation record for a resolved
    `tools/call` result.

    `line_bytes` — the raw response line as received (read only for its
    length: `payload_bytes` is the size of what actually crossed the
    wire for this result, not a re-serialization).

    `result_obj` — the parsed response, read only for counts and
    booleans:
      - `content_block_count` — number of items in `result.content`.
      - `content_text_nonempty` — whether any `content` item of type
        "text" has non-whitespace text. The text's *value* is never
        read into the record, only whether it's blank.
      - `structured_content_present` — whether `result.structuredContent`
        is truthy (present and non-empty), matching wrap/classify.py's
        own D8 definition of "present" so this field means the same
        thing here as it does in the live classify decision.
      - `is_error` — `result.isError`, a control-surface flag, not tool
        data.

    `fr8_would_fire` — supplied by the caller (wrap.py), which already
    ran the real classify gate for this exact result under the loaded
    baseline; this module trusts that boolean rather than recomputing it.
    """
    result = result_obj.get("result")
    if not isinstance(result, dict):
        result = {}

    content = result.get("content")
    content_list = content if isinstance(content, list) else []
    content_text_nonempty = any(
        isinstance(item, dict)
        and item.get("type") == "text"
        and bool((item.get("text") or "").strip())
        for item in content_list
    )

    return {
        "timestamp": time.time(),
        "server": server_label,
        "tool": tool_name,
        "is_error": bool(result.get("isError")),
        "content_block_count": len(content_list),
        "content_text_nonempty": content_text_nonempty,
        "structured_content_present": bool(result.get("structuredContent")),
        "payload_bytes": len(line_bytes),
        "fr8_would_fire": bool(fr8_would_fire),
    }


def append_record(path, record):
    """Append one JSON line to `path`. Best-effort and silent on any
    failure: an unwritable observe path must never affect the live
    pass-through or fail-open guarantees (FR-2) — the same reasoning that
    makes a classify failure resolve to `None` rather than raise.
    """
    try:
        line = json.dumps(record, sort_keys=True) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
