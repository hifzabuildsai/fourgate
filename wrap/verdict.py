#!/usr/bin/env python3
"""
Fourgate — verdict rewrite (plan.md Step 6, D6)

Takes a classify() verdict and produces the bytes to write to the client
in place of the original line — the in-band delivery mechanism FR-3
requires (a verdict delivered only to a log/file/alert would not satisfy
it). This is the "rewrite" half of D6's "one classify+rewrite function":
wrap/classify.py decides WHETHER a result matches; this module decides
HOW the match reaches the model.

FR-4 — attribution: the verdict text carries a marker (`[FOURGATE]`)
identifying Fourgate as its author, distinguishable from anything the
wrapped tool produced. An agent that then tells its user "the tool
reported X" when X came from this marker is a build defect, not
ambiguity in the marker itself.

FR-5 — additive: "Where original content exists, the verdict MUST be
attached alongside it, positioned to be read first. Fourgate MUST NOT
discard tool content the agent could still use. (silent_empty is the
degenerate case: there is no content to preserve.)" For silent_empty
specifically, that parenthetical is load-bearing: the match condition
*is* the absence of any interpretable content, so there is nothing to
carry forward. The rewritten result is built fresh — content becomes
exactly one item, the verdict — rather than shallow-copying whatever
else the original result object happened to contain. This also means no
field of the original result (metadata, debug info, anything outside
`content`) can survive into what the client receives, which is what
keeps FR-15's redaction guarantee airtight end-to-end: even if some
other field an already-empty result carried held a value FR-15 would
forbid in the verdict itself, it never reaches the client either way.
"""

import json

ATTRIBUTION_MARKER = "[FOURGATE]"


def attach(result_obj, verdict):
    """Return a NEW JSON-RPC response dict with `verdict` delivered as
    the tool result's only content item, attributed to Fourgate. Does
    not mutate `result_obj`.

    `jsonrpc` and `id` are carried forward unchanged — the client must
    still be able to correlate this as the response to its request.
    """
    verdict_text = f"{ATTRIBUTION_MARKER} {json.dumps(verdict, sort_keys=True)}"
    rewritten = dict(result_obj)
    rewritten["result"] = {
        "content": [{"type": "text", "text": verdict_text}],
        "isError": False,
    }
    return rewritten


def to_line(rewritten_obj):
    """Serialize a rewritten response into the newline-terminated bytes
    wrap.py writes to the client."""
    return json.dumps(rewritten_obj).encode("utf-8") + b"\n"
