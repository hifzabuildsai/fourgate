"""Operator-registered workflow configuration checks. No execution authority."""
import json
import os
import re
import stat
from pathlib import Path

from . import readback, scan

MAX_REGISTRY_BYTES = 1024 * 1024
WORKFLOW_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate registry field")
        result[key] = value
    return result


class WorkflowRegistry:
    """Snapshot IDs/paths/fingerprints at startup; revalidate each contract read."""

    def __init__(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            raise ValueError("registry must be a regular file")
        with path.open("rb") as handle:
            raw = handle.read(MAX_REGISTRY_BYTES + 1)
        if len(raw) > MAX_REGISTRY_BYTES:
            raise ValueError("registry exceeds 1 MiB")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if (not isinstance(data, dict) or set(data) != {"registry_version", "workflows"}
                or type(data["registry_version"]) is not int or data["registry_version"] != 1):
            raise ValueError("invalid registry schema")
        entries = data["workflows"]
        if not isinstance(entries, dict) or not 1 <= len(entries) <= 20:
            raise ValueError("registry needs 1..20 workflows")
        self._entries = {}
        self._root = path.parent
        for name, entry in entries.items():
            if not WORKFLOW_ID.fullmatch(name) or not isinstance(entry, dict):
                raise ValueError("invalid workflow entry")
            if set(entry) != {"contract", "sha256", "test_account"}:
                raise ValueError("invalid workflow entry fields")
            contract, digest, account = entry["contract"], entry["sha256"], entry["test_account"]
            if (not isinstance(contract, str) or not contract or Path(contract).is_absolute()
                    or not isinstance(digest, str) or not SHA256.fullmatch(digest)
                    or not isinstance(account, str) or not account.strip()):
                raise ValueError("invalid workflow registration")
            target = (self._root / contract).resolve()
            if not target.is_relative_to(self._root):
                raise ValueError("contract must resolve inside the registry directory")
            # Python 3.13+ leaves loops unresolved in non-strict resolve().
            if target.is_symlink():
                raise ValueError("contract symlink could not be resolved")
            try:
                info = target.stat()
                identity = (info.st_dev, info.st_ino) if stat.S_ISREG(info.st_mode) and info.st_ino else None
            except OSError:
                identity = None
            self._entries[name] = (target, digest, account, identity)

    @property
    def ids(self):
        return sorted(self._entries)

    def validate(self, workflow_id):
        result = {"readiness": "NOT_READY", "action_status": "NOT_RUN", "scope": "STATIC_CONFIG_ONLY"}
        if workflow_id not in self._entries:
            return {**result, "reason_code": "workflow_not_registered"}
        result["workflow_id"] = workflow_id
        path, digest, account, identity = self._entries[workflow_id]
        try:
            if identity is None or not path.resolve().is_relative_to(self._root) or not path.is_file():
                return {**result, "reason_code": "contract_unavailable"}
            # Check the opened file's identity before reading, including a swap
            # after the path check. Registry creation assumes a trusted, stable root.
            data = scan.load_contract(path, account, expected_sha256=digest, expected_file_identity=identity)
            credentials = set()
            for case in data["cases"]:
                credentials.update(readback.credential_envs(case.get("readback")))
                declared = (case["outcome_contract"]["verifier"].get("secret_env", [])
                            if "readback" not in case else [])
                if not isinstance(declared, list) or any(not isinstance(n, str) or not n for n in declared):
                    raise ValueError("invalid credential declarations")
                credentials.update(declared)
        except (OSError, RuntimeError):
            return {**result, "reason_code": "contract_unavailable"}
        except scan.RegisteredContractChangedError:
            return {**result, "reason_code": "contract_changed"}
        except (ValueError, RecursionError, TypeError, KeyError, AttributeError):
            return {**result, "reason_code": "contract_invalid"}
        except Exception:
            return {**result, "reason_code": "internal_validation_error"}
        missing = sum(not os.environ.get(name) for name in credentials)
        if missing:
            return {**result, "reason_code": "credential_missing", "missing_credential_count": missing}
        return {**result, "readiness": "CONFIG_VALID", "reason_code": "static_checks_satisfied",
                "planned_cases": len(data["cases"])}
