#!/usr/bin/env python3
"""
Fourgate — baseline loading (plan.md Step 5 / Step 5a)

Loads the hand-authored baseline JSON (format frozen in plan.md so a later
preflight-derived baseline is drop-in) and answers "what does the baseline
declare about this tool's successful terminal responses."

FR-12 — unbaselined degradation is fail-open: no baseline file, or no
entry for a given tool, means there is no established contract, and
wrap/classify.py must never emit a silent_empty verdict from either case.
A startup-time problem loading the baseline itself must not take down the
wrapped server either — it degrades to "no baseline" the same way.

This module only parses and looks up the baseline — it has no opinion on
what a tool's contract dict contains beyond "tools" mapping tool names to
dicts. wrap/classify.py decides which fields inside a contract matter.
"""

import json
import sys


def load(path):
    """Load the baseline JSON at `path`.

    Returns the parsed dict, or `None` if `path` is falsy, the file can't
    be read, or its contents aren't shaped like a baseline (FR-12's "no
    baseline" case — never raises).
    """
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print(
            f"fourgate: could not load baseline {path!r} ({exc}) — running unbaselined",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tools"), dict):
        print(
            f"fourgate: baseline {path!r} is not shaped like a baseline — running unbaselined",
            file=sys.stderr,
        )
        return None
    return data


def lookup(loaded_baseline, tool_name):
    """Return the tool's declared contract dict, or `None` if there is no
    baseline at all, or no entry for this tool — either way, FR-12: no
    established contract, no verdict.
    """
    if not loaded_baseline:
        return None
    return loaded_baseline.get("tools", {}).get(tool_name)
