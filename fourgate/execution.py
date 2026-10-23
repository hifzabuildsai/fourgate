"""Opt-in, single-use operator grants over the existing scanner.

The local state file is prepared explicitly, never recreated by serving tools.
A committed reservation precedes target startup. Uncertain reservations are
never resumed. This is not a sandbox or an exactly-once provider guarantee.
"""
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from . import __version__, scan
from .workflows import MAX_REGISTRY_BYTES, SHA256, WORKFLOW_ID, _unique_object

MAX_CALLS = 20
MAX_REPORT_BYTES = 16 * 1024
MAX_STATE_BYTES = 2 * 1024 * 1024
SAFE_REASONS = frozenset({"postcondition_satisfied", "record_missing", "field_mismatch",
    "verifier_error", "verifier_malformed", "verifier_timeout", "contract_invalid", "internal_error",
    "credential_missing", "not_success_result", "readback_selector_invalid", "readback_timeout",
    "readback_error", "readback_shape_invalid", "readback_unconfirmed", "readback_internal_error",
    "success_without_record_id", "tool_not_discovered", "incomplete_tool_result",
    "missing_result_type", "unsupported_result_type", "TimeoutError", "OSError", "RuntimeError"})


def not_run(reason):
    return {"report_version": 1, "run_state": "NOT_STARTED", "action_status": "NOT_RUN",
            "reason_code": reason, "new_execution": False}


class ExecutionPolicy:
    def __init__(self, path, registry):
        path = Path(path).resolve()
        if not path.is_file():
            raise ValueError("policy unavailable")
        with path.open("rb") as handle:
            raw = handle.read(MAX_REGISTRY_BYTES + 1)
        if len(raw) > MAX_REGISTRY_BYTES:
            raise ValueError("policy too large")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if (not isinstance(data, dict) or set(data) != {"policy_version", "state_file", "grants"}
                or type(data["policy_version"]) is not int or data["policy_version"] != 1):
            raise ValueError("invalid execution policy")
        state_file = data["state_file"]
        if not isinstance(state_file, str) or not state_file or Path(state_file).is_absolute():
            raise ValueError("invalid state path")
        self.state_path = (path.parent / state_file).resolve()
        if (not self.state_path.is_relative_to(path.parent) or not self.state_path.parent.is_dir()
                or self.state_path == path or self.state_path.is_symlink()):
            raise ValueError("invalid state path")
        grants = data["grants"]
        if not isinstance(grants, dict) or not 1 <= len(grants) <= MAX_CALLS:
            raise ValueError("invalid grants")
        total = 0
        for run_id, grant in grants.items():
            if (not WORKFLOW_ID.fullmatch(run_id) or not isinstance(grant, dict)
                    or set(grant) != {"workflow_id", "contract_sha256", "max_tool_calls"}):
                raise ValueError("invalid grant")
            workflow, digest, budget = grant["workflow_id"], grant["contract_sha256"], grant["max_tool_calls"]
            if (not isinstance(workflow, str) or registry.fingerprint(workflow) is None
                    or not isinstance(digest, str) or not SHA256.fullmatch(digest)
                    or digest != registry.fingerprint(workflow)
                    or type(budget) is not int or not 1 <= budget <= MAX_CALLS):
                raise ValueError("grant does not match reviewed configuration")
            total += budget
        if total > MAX_CALLS:
            raise ValueError("total call budget exceeds 20")
        self.grants = grants
        self.fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class ExecutionState:
    def __init__(self, policy):
        self.policy = policy
        info = policy.state_path.stat()
        if not stat.S_ISREG(info.st_mode) or not info.st_ino:
            raise ValueError("state must be a regular file with usable identity")
        self.identity = (info.st_dev, info.st_ino)
        with self.connection() as db:
            rows = db.execute("SELECT run_id, state, reserved_calls, report FROM runs").fetchall()
            if {row[0] for row in rows} != set(policy.grants):
                raise ValueError("prepared grants missing or changed")
            for run_id, *row in rows:
                self._check_row(run_id, row)

    def _check_row(self, run_id, row):
        state, reserved, raw = row
        if type(reserved) is not int or not 0 <= reserved <= self.policy.grants[run_id]["max_tool_calls"]:
            raise ValueError("invalid reserved count")
        if state == "AVAILABLE" and reserved == 0 and raw is None:
            return
        if state == "RESERVED" and reserved > 0 and raw is None:
            return
        if state == "COMPLETED" and reserved > 0 and isinstance(raw, str):
            return
        raise ValueError("inconsistent execution state")

    @staticmethod
    def prepare(policy):
        # Refuse overwrite/reset. The operator must preserve this state for the
        # full lifetime of the grant, including across client/server restarts.
        fd = os.open(policy.state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(str(policy.state_path), isolation_level=None)) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE metadata (policy_hash TEXT NOT NULL)")
            db.execute("INSERT INTO metadata VALUES (?)", (policy.fingerprint,))
            db.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
                       "reserved_calls INTEGER NOT NULL, report TEXT)")
            db.executemany("INSERT INTO runs VALUES (?, 'AVAILABLE', 0, NULL)",
                           [(name,) for name in policy.grants])
            db.execute("COMMIT")

    @contextmanager
    def connection(self, write=False):
        path = self.policy.state_path
        info = path.stat()
        if ((info.st_dev, info.st_ino) != self.identity or not stat.S_ISREG(info.st_mode)
                or info.st_size > MAX_STATE_BYTES):
            raise ValueError("execution state changed")
        # mode=rw/ro never creates a missing database. No network filesystem or
        # hostile local directory is supported by this execution boundary.
        with closing(sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                     uri=True, timeout=1, isolation_level=None)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            if write:
                db.execute("PRAGMA synchronous=FULL")
            if db.execute("SELECT policy_hash FROM metadata").fetchall() != [(self.policy.fingerprint,)]:
                raise ValueError("execution policy changed")
            yield db

    def read(self, run_id):
        with self.connection() as db:
            row = db.execute("SELECT state, reserved_calls, report FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError("prepared grant missing")
            self._check_row(run_id, row)
            return row

    def claim(self, run_id, count):
        with self.connection(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE runs SET state='RESERVED', reserved_calls=? "
                                 "WHERE run_id=? AND state='AVAILABLE' AND reserved_calls=0 AND report IS NULL",
                                 (count, run_id)).rowcount
            db.execute("COMMIT")
        return changed == 1

    def finish(self, run_id, payload):
        text = json.dumps(payload, sort_keys=True)
        if len(text.encode()) > MAX_REPORT_BYTES:
            raise ValueError("report exceeds bound")
        with self.connection(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE runs SET state='COMPLETED', report=? "
                                 "WHERE run_id=? AND state='RESERVED'", (text, run_id)).rowcount
            if changed != 1:
                raise ValueError("reservation unavailable")
            db.execute("COMMIT")


class WorkflowRunner:
    def __init__(self, registry, policy):
        self.registry, self.policy = registry, policy
        self.state = ExecutionState(policy)

    @property
    def ids(self):
        return sorted(self.policy.grants)

    def _base(self, run_id):
        grant = self.policy.grants[run_id]
        return {"report_version": 1, "run_id": run_id, "workflow_id": grant["workflow_id"],
                "contract_sha256": grant["contract_sha256"], "fourgate_version": __version__}

    def _uncertain(self, run_id, reason="execution_uncertain", reserved=0, new_execution=False):
        return {**self._base(run_id), "run_state": "UNCERTAIN", "action_status": "UNCERTAIN",
                "verdict": "UNKNOWN", "reason_code": reason, "reserved_tool_calls": reserved,
                "cases": [], "new_execution": new_execution}

    def _saved_report(self, run_id, raw, reserved):
        payload = json.loads(raw)
        base = self._base(run_id)
        required = set(base) | {"run_state", "action_status", "verdict", "reason_code",
                               "reserved_tool_calls", "cases", "new_execution"}
        if (not isinstance(payload, dict) or not required <= set(payload)
                or set(payload) - required - {"call_attempts"}
                or any(payload.get(k) != v for k, v in base.items())
                or type(payload["report_version"]) is not int
                or type(payload["reserved_tool_calls"]) is not int
                or payload["reserved_tool_calls"] != reserved or payload["new_execution"] is not True):
            raise ValueError("invalid saved report")
        rows = payload["cases"]
        if not isinstance(rows, list) or len(rows) > reserved:
            raise ValueError("invalid report cases")
        for index, row in enumerate(rows, 1):
            if (not isinstance(row, dict) or set(row) != {"case_index", "status", "reason_code"}
                    or type(row["case_index"]) is not int or row["case_index"] != index
                    or row["status"] not in ("PASS", "FAIL", "UNKNOWN")
                    or row["reason_code"] not in SAFE_REASONS | {"contract_failure", "verification_unknown"}):
                raise ValueError("invalid report case")
        if payload["run_state"] == "UNCERTAIN":
            if payload != self._uncertain(run_id, "execution_error", reserved, True):
                raise ValueError("invalid uncertain report")
        elif payload["run_state"] == "COMPLETED":
            count = payload.get("call_attempts")
            if (type(count) is not int or not 0 <= count <= reserved
                    or payload["action_status"] != ("ATTEMPTED" if count else "NOT_RUN")
                    or payload["reason_code"] != "scan_completed"
                    or payload["verdict"] != _overall(rows, reserved, count)):
                raise ValueError("invalid completed report")
        else:
            raise ValueError("invalid report state")
        return payload

    def get_report(self, run_id):
        if run_id not in self.policy.grants:
            return not_run("grant_not_registered")
        try:
            state, reserved, raw = self.state.read(run_id)
            if state == "AVAILABLE":
                return {**self._base(run_id), **not_run("not_started")}
            if state == "RESERVED":
                return self._uncertain(run_id, reserved=reserved)
            if state != "COMPLETED" or not isinstance(raw, str) or len(raw.encode()) > MAX_REPORT_BYTES:
                raise ValueError("invalid saved report")
            return {**self._saved_report(run_id, raw, reserved), "new_execution": False}
        except (OSError, ValueError, sqlite3.Error, RuntimeError, TypeError, KeyError):
            return self._uncertain(run_id, "execution_state_unavailable")

    def run(self, workflow_id, run_id):
        grant = self.policy.grants.get(run_id)
        if grant is None:
            return not_run("grant_not_registered")
        if workflow_id != grant["workflow_id"]:
            return not_run("grant_workflow_mismatch")
        prior = self.get_report(run_id)
        if prior["run_state"] != "NOT_STARTED":
            return prior
        data, readiness = self.registry.validated_contract(workflow_id)
        if data is None:
            return not_run(readiness["reason_code"])
        planned = len(data["cases"])
        if planned > grant["max_tool_calls"]:
            return not_run("budget_exceeded")
        try:
            if not self.state.claim(run_id, planned):
                return self.get_report(run_id)
        except (OSError, ValueError, sqlite3.Error, RuntimeError):
            return self._uncertain(run_id, "execution_state_unavailable")
        attempted = 0

        def before_call():
            nonlocal attempted
            if attempted >= planned:
                raise RuntimeError("reserved call budget exhausted")
            attempted += 1

        try:
            raw = scan._scan_loaded_contract(data, before_call=before_call)
            rows = []
            for index, row in enumerate(raw["cases"][:MAX_CALLS], 1):
                status = row.get("status") if row.get("status") in ("PASS", "FAIL", "UNKNOWN") else "UNKNOWN"
                reason = row.get("reason_code")
                if reason not in SAFE_REASONS:
                    reason = "contract_failure" if status == "FAIL" else "verification_unknown"
                rows.append({"case_index": index, "status": status, "reason_code": reason})
            verdict = _overall(rows, planned, attempted)
            payload = {**self._base(run_id), "run_state": "COMPLETED",
                "action_status": "ATTEMPTED" if attempted else "NOT_RUN", "verdict": verdict,
                "reason_code": "scan_completed", "reserved_tool_calls": planned,
                "call_attempts": attempted, "cases": rows, "new_execution": True}
        except Exception:
            payload = self._uncertain(run_id, "execution_error", planned, True)
        try:
            self.state.finish(run_id, payload)
        except (OSError, ValueError, sqlite3.Error, RuntimeError):
            return self._uncertain(run_id, "report_persistence_error", planned, True)
        return payload


def _overall(rows, planned, attempted):
    """Conservative summary of existing scanner verdicts, not another verifier."""
    if not rows or len(rows) != planned or attempted != planned or any(r["status"] == "UNKNOWN" for r in rows):
        return "UNKNOWN"
    return "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
