#!/usr/bin/env python3
"""Deterministic Outcome Guard contracts and verifier protocol.

The runtime blocking decision is never made by an LLM. A human-approved
per-tool contract selects a minimal set of named fields from the correlated
request/result. Those fields are sent to an authoritative verifier command,
which must return one small typed JSON object:

    {"status": "pass"}
    {"status": "fail", "reason_code": "record_missing"}

Anything else is UNKNOWN and therefore fail-open.
"""

import json
import os
import re
import subprocess
import sys
import time

VALID_RECOVERIES = {"stop", "retry_once", "ask_user"}
VALID_MODES = {"shadow", "enforce"}
MAX_VERIFIER_TIMEOUT_MS = 2000  # explicit per-contract cap for authoritative read-back
MAX_TEXT_SELECTOR_CHARS = 8192
MAX_REGEX_PATTERN_CHARS = 256


class _Missing:
    pass


MISSING = _Missing()


def load(path):
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"fourgate: could not load outcome contracts {path!r} ({exc}) — outcome guard disabled", file=sys.stderr)
        return None
    if (
        not isinstance(data, dict)
        or data.get("contract_version") != 1
        or not isinstance(data.get("tools"), dict)
    ):
        print(f"fourgate: outcome contracts {path!r} are invalid — outcome guard disabled", file=sys.stderr)
        return None
    data["_contract_dir"] = os.path.dirname(os.path.abspath(path))
    return data


def lookup(contracts, tool_name):
    if not contracts:
        return None
    contract = contracts.get("tools", {}).get(tool_name)
    if not isinstance(contract, dict):
        return None
    resolved = dict(contract)
    resolved["_contract_dir"] = contracts.get("_contract_dir")
    return resolved


def _path_get(value, path):
    current = value
    if path in (None, "", "."):
        return current
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdecimal() and int(part) < len(current):
            current = current[int(part)]
        else:
            return MISSING
    return current


def validate_text_selector(selector):
    """Reject invalid text parsing contracts before a scan can write."""
    mode = selector.get("parse")
    if mode is None:
        return
    if selector.get("source") != "result" or selector.get("path") != "result.content.0.text":
        raise ValueError("text parsing requires result.content.0.text")
    if mode == "regex":
        pattern = selector.get("pattern")
        group = selector.get("group", 1)
        if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_REGEX_PATTERN_CHARS:
            raise ValueError("regex pattern must be 1..256 characters")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ValueError("invalid text regex pattern") from exc
        if (type(group) is int and not 1 <= group <= compiled.groups) or (
                isinstance(group, str) and group not in compiled.groupindex) or (
                type(group) is not int and not isinstance(group, str)):
            raise ValueError("regex group must name a capture group")
    elif mode == "embedded_json":
        field = selector.get("field")
        if not isinstance(field, str) or not field or any(not part for part in field.split(".")):
            raise ValueError("embedded_json requires a nonempty field path")
    else:
        raise ValueError("parse must be regex or embedded_json")


def _select(selector, arguments, result_obj):
    source = selector.get("source")
    path = selector.get("path")
    if source == "arguments":
        value = _path_get(arguments, path)
    elif source == "result":
        value = _path_get(result_obj, path)
    else:
        return MISSING
    mode = selector.get("parse")
    if not mode or value is MISSING:
        return value
    if not isinstance(value, str) or len(value) > MAX_TEXT_SELECTOR_CHARS:
        return MISSING
    if mode == "regex":
        match = re.search(selector["pattern"], value)
        if not match:
            return MISSING
        return match.group(selector.get("group", 1)) or MISSING
    if mode == "embedded_json":
        decoder = json.JSONDecoder()
        for index, char in enumerate(value):
            if char != "{":
                continue
            try:
                document, _ = decoder.raw_decode(value, index)
            except json.JSONDecodeError:
                continue
            found = _path_get(document, selector["field"])
            if found is not MISSING:
                return found
    return MISSING


def _extract(contract, arguments, result_obj):
    selectors = contract.get("extract")
    if not isinstance(selectors, dict) or not selectors:
        return None, "contract_invalid"
    extracted = {}
    for name, selector in selectors.items():
        if not isinstance(name, str) or not isinstance(selector, dict):
            return None, "contract_invalid"
        if selector.get("source") not in ("arguments", "result"):
            return None, "contract_invalid"
        value = _select(selector, arguments, result_obj)
        if value is MISSING:
            return None, "required_field_missing"
        extracted[name] = value
    return extracted, None


def _expand_command(command):
    if not isinstance(command, list) or not command or not all(isinstance(p, str) for p in command):
        return None
    return [sys.executable if part == "{python}" else part for part in command]


def evaluate(result_obj, arguments, qualified_tool, contract):
    """Return a structural evaluation dict. Never raises.

    status is ``pass``, ``fail``, or ``unknown``. Only ``fail`` contains a
    model-visible verdict. ``unknown`` is always fail-open at the caller.
    """
    try:
        result = result_obj.get("result")
        if not isinstance(result, dict) or result.get("isError"):
            return {"status": "unknown", "reason_code": "not_success_result"}

        extracted, extraction_error = _extract(contract, arguments or {}, result_obj)
        if extraction_error:
            return {"status": "unknown", "reason_code": extraction_error}

        verifier = contract.get("verifier")
        if not isinstance(verifier, dict):
            return {"status": "unknown", "reason_code": "contract_invalid"}
        command = _expand_command(verifier.get("command"))
        if command is None:
            return {"status": "unknown", "reason_code": "contract_invalid"}

        timeout_ms = verifier.get("timeout_ms")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0 or timeout_ms > MAX_VERIFIER_TIMEOUT_MS:
            return {"status": "unknown", "reason_code": "contract_invalid"}

        cwd = verifier.get("cwd")
        if cwd is not None:
            if not isinstance(cwd, str):
                return {"status": "unknown", "reason_code": "contract_invalid"}
            base_dir = contract.get("_contract_dir") or os.getcwd()
            cwd = os.path.abspath(os.path.join(base_dir, cwd))

        completed = subprocess.run(
            command,
            input=json.dumps(extracted).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout_ms / 1000.0,
            env=os.environ.copy(),
            cwd=cwd,
            check=False,
        )
        if completed.returncode != 0:
            return {"status": "unknown", "reason_code": "verifier_error"}
        if len(completed.stdout) > 1024 * 1024:
            return {"status": "unknown", "reason_code": "verifier_malformed"}
        try:
            reply = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"status": "unknown", "reason_code": "verifier_malformed"}
        if not isinstance(reply, dict) or reply.get("status") not in {"pass", "fail"}:
            return {"status": "unknown", "reason_code": "verifier_malformed"}
        if reply["status"] == "pass":
            return {
                "status": "pass",
                "reason_code": "postcondition_satisfied",
                "checked_fields": sorted(extracted.keys()),
            }

        reason_code = reply.get("reason_code")
        allowed = contract.get("allowed_failure_reasons")
        if not isinstance(allowed, list) or reason_code not in allowed:
            return {"status": "unknown", "reason_code": "verifier_malformed"}

        recovery = contract.get("recovery", "stop")
        if recovery not in VALID_RECOVERIES:
            return {"status": "unknown", "reason_code": "contract_invalid"}

        verdict = {
            "kind": "outcome_failed",
            "tool": qualified_tool,
            "evidence": {
                "reason_code": reason_code,
                "checked_fields": sorted(extracted.keys()),
            },
            "recovery": recovery,
        }
        evaluation = {
            "status": "fail",
            "reason_code": reason_code,
            "checked_fields": sorted(extracted.keys()),
            "verdict": verdict,
        }
        # Scan reports may retain an approved verifier's read-back evidence.
        # The runtime verdict and shape-only logs never include these values.
        if isinstance(reply.get("evidence"), dict):
            evaluation["readback_evidence"] = reply["evidence"]
        return evaluation
    except subprocess.TimeoutExpired:
        return {"status": "unknown", "reason_code": "verifier_timeout"}
    except Exception:
        return {"status": "unknown", "reason_code": "internal_error"}


def record(server_label, tool_name, mode, evaluation):
    """Shape-only record: no arguments, extracted values, or raw payload."""
    return {
        "timestamp": time.time(),
        "server": server_label,
        "tool": tool_name,
        "mode": mode,
        "status": evaluation.get("status", "unknown"),
        "reason_code": evaluation.get("reason_code", "internal_error"),
        "checked_fields": list(evaluation.get("checked_fields") or []),
    }


def append_record(path, item):
    line = json.dumps(item, sort_keys=True)
    if not path:
        print(f"[FOURGATE_OUTCOME] {line}", file=sys.stderr)
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        print(f"[FOURGATE_OUTCOME] {line}", file=sys.stderr)
