"""Runtime Outcome Guard verifier backed by the scan's HTTP read-back.

    python -m fourgate.verify_http <readback-config.json>

The config file is a ``readback`` object in the scan contract format. The
runtime wrapper sends the contract's extracted fields as one JSON object on
stdin. The same validation, URL construction, and bounded GET logic as
``fourgate scan`` decides the result. A confirmed result prints one typed
JSON line and exits 0:

    {"status": "pass"}
    {"status": "fail", "reason_code": "field_mismatch", "evidence": {...}}

Any uncertainty (401/403, an unconfigured status, timeout, network error,
missing credential, invalid config or input) prints nothing on stdout and
exits nonzero, which the runtime records as UNKNOWN. Evidence is structural
only: no URL, response body, field values, or token.
"""
import json
import sys

from wrap import outcome
from . import readback

EXIT_UNKNOWN = 1
EXIT_CONFIG = 2
MAX_INPUT_BYTES = 1024 * 1024


def load_config(path, extracted):
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    readback.validate(config, extracted)
    # The runtime caps the whole verifier process at this budget, so a longer
    # read-back budget could only ever end as a killed verifier.
    if config.get("timeout_ms", 5000) > outcome.MAX_VERIFIER_TIMEOUT_MS:
        raise ValueError(f"timeout_ms must be at most {outcome.MAX_VERIFIER_TIMEOUT_MS} for runtime verification")
    return config


def read_extracted(stream):
    raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("extracted fields input is too large")
    extracted = json.loads(raw)
    if not isinstance(extracted, dict) or not extracted:
        raise ValueError("extracted fields must be a nonempty JSON object")
    return extracted


def reply(evaluation):
    """Map a read-back evaluation to the typed verifier reply, or None for UNKNOWN."""
    status = evaluation.get("status")
    if status == "pass":
        return {"status": "pass"}
    if status != "fail":
        return None
    observed = evaluation.get("readback_evidence") or {}
    evidence = {"method": "GET", "status": observed.get("status"), "attempts": evaluation.get("attempts")}
    if evaluation.get("reason_code") == "field_mismatch":
        evidence["checked_fields"] = list(evaluation.get("checked_fields") or [])
        evidence["mismatched_fields"] = [m["path"] for m in evaluation.get("mismatched_fields") or []]
    return {"status": "fail", "reason_code": evaluation["reason_code"], "evidence": evidence}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m fourgate.verify_http <readback-config.json>", file=sys.stderr)
        return EXIT_CONFIG
    try:
        extracted = read_extracted(sys.stdin.buffer)
        config = load_config(argv[0], extracted)
    except (OSError, ValueError) as exc:
        print(f"fourgate.verify_http: configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        evaluation = readback.evaluate_extracted(config, extracted)
    except Exception as exc:
        print(f"fourgate.verify_http: unknown (internal_error: {type(exc).__name__})", file=sys.stderr)
        return EXIT_UNKNOWN
    typed = reply(evaluation)
    if typed is None:
        observed = evaluation.get("readback_evidence") or {}
        detail = f", GET status {observed['status']}" if "status" in observed else ""
        print(f"fourgate.verify_http: unknown ({evaluation.get('reason_code')}, "
              f"attempts {evaluation.get('attempts')}{detail})", file=sys.stderr)
        return EXIT_UNKNOWN
    print(json.dumps(typed, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
