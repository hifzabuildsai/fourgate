"""One reviewed Issue update, exercised through the reusable local reference pack."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from fourgate import readback
from fourgate.scan import load_contract

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'examples' / 'github-issue'


def test_reference_expectations_come_from_the_reviewed_request():
    data = load_contract(PACK / 'scan.example.json', 'disposable-github-issue')
    case = data['cases'][0]
    assert len(data['cases']) == 1
    assert case['readback']['repository'] == case['arguments']['owner'] + '/' + case['arguments']['repo']
    assert case['readback']['missing_is_fail'] is False
    assert case['readback']['expected_fields'] == {
        'number': 'expected_number', 'title': 'title', 'body': 'body', 'state': 'state'}
    extract = case['outcome_contract']['extract']
    for field in case['readback']['expected_fields'].values():
        assert extract[field]['source'] == 'arguments'
    assert extract['expected_number']['path'] == 'issue_number'
    assert extract['returned_number']['source'] == 'result'


@pytest.mark.parametrize('observed_number,missing_number,expected', [
    (73, False, ('pass', 'postcondition_satisfied')),
    (74, False, ('fail', 'field_mismatch')),
    (73, True, ('unknown', 'readback_shape_invalid')),
])
def test_github_template_binds_approved_identity_not_tool_claims(monkeypatch, observed_number, missing_number, expected):
    case = load_contract(PACK / 'scan.example.json', 'disposable-github-issue')['cases'][0]
    case['readback'].update(repository='reference-owner/disposable', attempts=1)
    arguments = {**case['arguments'], 'owner': 'reference-owner', 'repo': 'disposable',
                 'issue_number': 73, 'title': 'Approved title', 'body': 'Approved body', 'state': 'open'}
    response = {'result': {'structuredContent': {'number': 73, 'title': 'Untrusted claimed title'}}}
    document = {'number': observed_number, 'title': arguments['title'], 'body': arguments['body'], 'state': 'open'}
    if missing_number:
        del document['number']
    requests = []

    def get(url, headers, timeout):
        requests.append(url)
        return 200, document

    monkeypatch.setattr(readback, '_get', get)  # No external GitHub request.
    monkeypatch.setenv('FOURGATE_GITHUB_READ_TOKEN', 'synthetic-reference-token')
    result = readback.evaluate(case['readback'], case['outcome_contract'], arguments, response)
    assert (result['status'], result['reason_code']) == expected
    assert requests == ['https://api.github.com/repos/reference-owner/disposable/issues/73']


def test_local_reference_pack_reports_real_verdicts_without_repeating_the_write(tmp_path):
    output = tmp_path / 'new-reference-evidence'
    completed = subprocess.run([sys.executable, '-B', str(PACK / 'run_local.py'), '--out', str(output)],
                               cwd=ROOT, capture_output=True, text=True, timeout=25)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    manifest = json.loads((output / 'acceptance.json').read_text())
    assert manifest['scope'] == 'LOCAL_SIMULATION_AND_INDUCED_CONTROLS'
    assert manifest['expectations_met'] is True
    assert manifest['protected_target_calls'] == 1
    assert manifest['external_workflow_requests'] == 0
    assert manifest['controls'] == [
        {'reference': 'healthy', 'status': 'PASS', 'reason_code': 'postcondition_satisfied', 'process_exit': 0},
        {'reference': 'wrong-expectation', 'status': 'FAIL', 'reason_code': 'field_mismatch', 'process_exit': None},
        {'reference': 'wrong-identity', 'status': 'FAIL', 'reason_code': 'field_mismatch', 'process_exit': None},
        {'reference': 'ambiguous-404', 'status': 'UNKNOWN', 'reason_code': 'readback_unconfirmed', 'process_exit': None},
        {'reference': 'unavailable-503', 'status': 'UNKNOWN', 'reason_code': 'readback_unconfirmed', 'process_exit': None},
        {'reference': 'missing-identity', 'status': 'UNKNOWN', 'reason_code': 'readback_shape_invalid', 'process_exit': None},
    ]
    trace = [json.loads(line) for line in (output / 'target-requests.jsonl').read_text().splitlines()]
    assert sum(r['method'] == 'tools/call' for r in trace) == 1
    assert trace[-1]['params']['arguments']['issue_number'] == 73
    assert manifest['readback_gets'] == 6
    assert manifest['authority_unchanged_by_controls'] is True
    initial = json.loads((output / 'initial-authority.json').read_text())
    current = json.loads((output / 'authority.json').read_text())
    assert initial['number'] == current['number'] == 73
    assert initial['state'] == 'closed' and current['state'] == 'open'
    assert initial['title'] != current['title']
    for control in manifest['controls']:
        directory = output / control['reference']
        report = json.loads((directory / 'fourgate-report.json').read_text())
        assert report['cases'][0]['status'] == control['status']
        assert report['cases'][0]['reason_code'] == control['reason_code']
        assert (directory / 'fourgate-report.html').is_file()
        if control['reference'] != 'healthy':
            assert 'repro_steps' not in report['cases'][0], 'Read-only controls must not recommend another write'
    # A fresh output path is mandatory: evidence must never be overwritten.
    before = (output / 'acceptance.json').read_bytes()
    again = subprocess.run([sys.executable, '-B', str(PACK / 'run_local.py'), '--out', str(output)],
                           cwd=ROOT, capture_output=True, text=True, timeout=5)
    assert again.returncode == 2
    assert (output / 'acceptance.json').read_bytes() == before
    assert (output / 'target-requests.jsonl').read_text().count('"method": "tools/call"') == 1
