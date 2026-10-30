"""D2: the reviewed D1 Issue pack through C2, without repeating D1's negative controls."""
import copy
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sqlite3
import sys
import threading

from _support import ScriptedSession
from test_mcp_execution import ROOT, call, command, prepare, writes

PACK = ROOT / 'examples' / 'github-issue'


def test_reference_pack_single_use_mcp_execution_and_restart(tmp_path):
    template = json.loads((PACK / 'scan.example.json').read_text(encoding='utf-8'))
    approved = {**template['cases'][0]['arguments'], 'owner': 'reference-owner', 'repo': 'disposable',
                'title': 'PRIVATE-D2-TITLE-SENTINEL', 'body': 'PRIVATE-D2-BODY-SENTINEL'}
    initial = {'number': approved['issue_number'], 'title': 'Before update', 'body': 'Before body', 'state': 'closed'}
    authority, trace = tmp_path / 'authority.json', tmp_path / 'target-requests.jsonl'
    starts, state = tmp_path / 'target-starts.txt', tmp_path / 'execution.sqlite3'
    registry, policy, contract = [tmp_path / name for name in ('registry.json', 'policy.json', 'scan.json')]

    def save(path, value):
        with path.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2)

    save(tmp_path / 'approved-request.json', approved)
    save(authority, initial)
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append(self.path)
            with (tmp_path / 'readback-requests.jsonl').open('a', encoding='utf-8') as handle:
                handle.write(json.dumps({'method': 'GET', 'path': self.path}) + '\n')
            assert self.path == '/repos/reference-owner/disposable/issues/73'
            body = authority.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    # Observe process starts as well as calls; run the unchanged tracked D1 fixture.
    target = (
        "import runpy,sys\nfrom pathlib import Path\n"
        "with Path(sys.argv[2], 'target-starts.txt').open('a') as f: f.write('START\\n')\n"
        "sys.argv=[sys.argv[1],'--directory',sys.argv[2]]\n"
        "runpy.run_path(sys.argv[0],run_name='__main__')\n")
    local = copy.deepcopy(template)
    local['server']['command'] = [sys.executable, '-B', '-c', target, str(PACK / 'stdio_fixture.py'), str(tmp_path)]
    case = local['cases'][0]
    case['arguments'] = approved
    case['readback'] = {key: value for key, value in case['readback'].items()
                        if key not in ('repository', 'issue_number_field', 'missing_is_fail')}
    case['readback'].update(type='http', url_template=(
        f'http://127.0.0.1:{httpd.server_port}/repos/reference-owner/disposable/issues/{{lookup_number}}'))
    assert case['outcome_contract'] == template['cases'][0]['outcome_contract']
    assert case['readback']['expected_fields'] == template['cases'][0]['readback']['expected_fields']
    save(contract, local)
    digest = hashlib.sha256(contract.read_bytes()).hexdigest()
    save(registry, {'registry_version': 1, 'workflows': {'reference-issue': {
        'contract': 'scan.json', 'sha256': digest, 'test_account': local['server']['test_account']}}})
    save(policy, {'policy_version': 1, 'state_file': 'execution.sqlite3', 'grants': {'d2-once': {
        'workflow_id': 'reference-issue', 'contract_sha256': digest, 'max_tool_calls': 1}}})
    env = {k: v for k, v in os.environ.items() if k.upper() not in
           ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')}
    token = 'D2-SYNTHETIC-READ-CREDENTIAL'
    env.update(FOURGATE_GITHUB_READ_TOKEN=token, NO_PROXY='*', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT))
    adapter_calls, exits, phases = [], [], []
    completed = False

    def counts():
        return {'target_starts': len(starts.read_text().splitlines()) if starts.exists() else 0,
                'target_calls': len(writes(trace)), 'readback_gets': len(seen), 'adapter_calls': len(adapter_calls)}

    @contextmanager
    def client():
        session = ScriptedSession(command(registry, policy), env=env)
        try:
            yield session
        finally:
            session.close()
            exits.append(session.proc.returncode)
            assert session.proc.returncode == 0

    def invoke(session, name, arguments):
        response = session.send_request('tools/call', call(name=name, arguments=arguments)['params'])
        assert response is not None and 'error' not in response, response
        result = response['result']
        payload = result['structuredContent']
        assert result['resultType'] == 'complete' and result['isError'] is False
        assert json.loads(result['content'][0]['text']) == payload
        assert len(json.dumps(payload).encode()) <= 16384
        for private in (approved['title'], approved['body'], token, str(tmp_path),
                        '127.0.0.1', 'UNTRUSTED TOOL CLAIM'):
            # Windows paths are JSON-escaped on the wire; compare encoded values.
            assert json.dumps(private)[1:-1] not in json.dumps(response)
        if name != 'validate_workflow':
            assert set(payload) == {'report_version', 'run_id', 'workflow_id', 'contract_sha256',
                'fourgate_version', 'run_state', 'action_status', 'verdict', 'reason_code',
                'reserved_tool_calls', 'call_attempts', 'cases', 'new_execution'}
            assert payload['cases'] == [{'case_index': 1, 'status': 'PASS', 'reason_code': 'postcondition_satisfied'}]
        adapter_calls.append(name)
        phases.append({'after': name, **counts()})
        return payload

    run_args = {'workflow_id': 'reference-issue', 'run_id': 'd2-once'}
    try:
        assert not state.exists()
        prepared = prepare(registry, policy, env)
        before_validation = state.read_bytes()
        with client() as session:
            ready = invoke(session, 'validate_workflow', {'workflow_id': 'reference-issue'})
            assert ready == {'workflow_id': 'reference-issue', 'readiness': 'CONFIG_VALID',
                             'action_status': 'NOT_RUN', 'scope': 'STATIC_CONFIG_ONLY',
                             'reason_code': 'static_checks_satisfied', 'planned_cases': 1}
        assert counts() == {'target_starts': 0, 'target_calls': 0, 'readback_gets': 0, 'adapter_calls': 1}
        assert authority.read_text() == json.dumps(initial, indent=2)
        assert state.read_bytes() == before_validation
        with client() as session:
            fresh = invoke(session, 'run_workflow', run_args)
            assert fresh['new_execution'] is True and fresh['verdict'] == 'PASS'
            assert fresh['run_state'] == 'COMPLETED' and fresh['action_status'] == 'ATTEMPTED'
            assert fresh['reserved_tool_calls'] == fresh['call_attempts'] == 1
            assert fresh['contract_sha256'] == digest
            assert counts() == {'target_starts': 1, 'target_calls': 1, 'readback_gets': 1, 'adapter_calls': 2}
            assert json.loads(authority.read_text()) == {'number': approved['issue_number'], **{
                key: approved[key] for key in ('title', 'body', 'state')}}
            after_run = {'authority': authority.read_bytes(), 'state': state.read_bytes(), 'trace': trace.read_bytes()}
            saved = {**fresh, 'new_execution': False}
            assert invoke(session, 'get_run_report', {'run_id': 'd2-once'}) == saved
            assert invoke(session, 'run_workflow', run_args) == saved
        # New serving process/client; original prepared and consumed state stays in place.
        with client() as session:
            assert invoke(session, 'run_workflow', run_args) == saved
            assert invoke(session, 'get_run_report', {'run_id': 'd2-once'}) == saved
        assert counts() == {'target_starts': 1, 'target_calls': 1, 'readback_gets': 1, 'adapter_calls': 6}
        assert all((phase['target_starts'], phase['target_calls'], phase['readback_gets']) == (1, 1, 1)
                   for phase in phases[1:])
        assert {'authority': authority.read_bytes(), 'state': state.read_bytes(), 'trace': trace.read_bytes()} == after_run
        assert hashlib.sha256(contract.read_bytes()).hexdigest() == digest
        with sqlite3.connect(state.as_uri() + '?mode=ro', uri=True) as db:
            assert db.execute('SELECT state,reserved_calls FROM runs').fetchall() == [('COMPLETED', 1)]
            assert json.loads(db.execute('SELECT report FROM runs').fetchone()[0]) == fresh
        assert exits == [0, 0, 0]
        completed = True
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        evidence = {'scope': 'LOCAL_REFERENCE_PACK_MCP_INTEGRATION', 'fixture': str(tmp_path),
                    'completed': completed, **counts(), 'phases': phases,
                    'adapter_tools': adapter_calls, 'server_process_exits': exits,
                    'prepare_process_exit': prepared.returncode if 'prepared' in locals() else None,
                    'external_workflow_requests': 0}
        save(tmp_path / 'd2-counts.json', evidence)
        print('D2_COUNTS ' + json.dumps(evidence, sort_keys=True))
