"""The operator guide's contract templates must stay loadable as shipped."""
from pathlib import Path

import pytest

from fourgate.scan import load_contract

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "contracts"


@pytest.mark.parametrize("name, label", [
    ("text-id-readback.example.json", "<disposable test account label>"),
    ("invalid-credential-check.example.json", "<invalid-credential check label>"),
])
def test_example_contract_passes_validation(name, label):
    path = EXAMPLES / name
    # Templates are written without a BOM; a BOM makes json.loads reject them.
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    data = load_contract(path, label)
    case = data["cases"][0]
    assert case["tool"] in data["write_tools"]
    assert case["outcome_contract"]["record_id_field"] == "record_id"
    assert case["readback"]["type"] == "http"


def test_invalid_credential_template_needs_no_readback_credential():
    data = load_contract(EXAMPLES / "invalid-credential-check.example.json", "<invalid-credential check label>")
    assert "token_env" not in data["cases"][0]["readback"]
