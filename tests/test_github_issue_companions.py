"""Doctor/guard companion files for the GitHub Issue pack stay loadable when configured."""
import json
from pathlib import Path

from wrap import outcome

from fourgate import readback, verify_http

PACK = Path(__file__).resolve().parents[1] / "examples" / "github-issue"


def test_runtime_and_readback_examples_validate_when_configured(tmp_path):
    runtime = json.loads((PACK / "runtime.example.json").read_text(encoding="utf-8"))
    config = json.loads((PACK / "readback.example.json").read_text(encoding="utf-8"))
    config["repository"] = "acme-test/disposable"
    extract = runtime["tools"]["issue_write"]["extract"]
    readback.validate(config, extract)
    path = tmp_path / "readback.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    verify_http.load_config(path, extract)
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    loaded = outcome.load_strict(runtime_path)
    assert loaded["tools"]["issue_write"]["verifier"]["timeout_ms"] == 2000
    assert loaded["tools"]["issue_write"]["verifier"]["secret_env"] == ["FOURGATE_GITHUB_READ_TOKEN"]


def test_runtime_example_keeps_verifier_budget_at_2000():
    runtime = json.loads((PACK / "runtime.example.json").read_text(encoding="utf-8"))
    assert runtime["tools"]["issue_write"]["verifier"]["timeout_ms"] == 2000
