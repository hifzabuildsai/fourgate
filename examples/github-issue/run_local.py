"""Reproduce reference outcomes with one local update and read-only controls."""
import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PACK = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from fourgate import readback, report  # noqa: E402


def save(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='Fresh evidence directory; never overwritten')
    args = parser.parse_args()
    output = args.out.absolute()
    try:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        parser.error('--out must not already exist')
    template = json.loads((PACK / 'scan.example.json').read_text())
    approved = {'owner': 'reference-owner', 'repo': 'disposable', 'issue_number': 73,
                'title': 'HUMAN-REVIEWED LOCAL TITLE', 'body': 'HUMAN-REVIEWED LOCAL BODY', 'state': 'open'}
    save(output / 'approved-request.json', approved)
    initial = {'number': 73, 'title': 'PREEXISTING LOCAL TITLE',
               'body': 'PREEXISTING LOCAL BODY', 'state': 'closed'}
    save(output / 'initial-authority.json', initial)
    save(output / 'authority.json', initial)
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_GET(self):
            seen.append(self.path)
            parts = self.path.split('/')
            reference = parts[2] if len(parts) > 2 else ''
            expected = '/controls/' + reference + '/repos/reference-owner/disposable/issues/73'
            status = 200
            if self.path != expected or reference == 'ambiguous-404':
                status = 404
            elif reference == 'unavailable-503':
                status = 503
            document = json.loads((output / 'authority.json').read_text()) if status == 200 else {}
            if reference == 'missing-identity':
                document.pop('number', None)
            body = json.dumps(document).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    prefix = 'http://127.0.0.1:' + str(httpd.server_port)
    # No inherited proxy or real read token can redirect this local demonstration.
    env = {k: v for k, v in os.environ.items() if k.upper() not in
           ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')}
    env.update(FOURGATE_GITHUB_READ_TOKEN='synthetic-local-reference-token',
               NO_PROXY='*', PYTHONDONTWRITEBYTECODE='1')
    local = copy.deepcopy(template)
    local['server']['command'] = [sys.executable, '-B', str(PACK / 'stdio_fixture.py'), '--directory', str(output)]
    local['cases'][0]['arguments'] = approved
    config = local['cases'][0]['readback']
    # Only the authority transport changes; predicates/extraction remain the template's.
    config.pop('repository')
    config.pop('issue_number_field')
    config.pop('missing_is_fail')
    config.update(type='http', url_template=prefix + '/controls/healthy/repos/reference-owner/disposable/issues/{returned_number}')
    save(output / 'scan-local.json', local)
    command = [sys.executable, '-B', '-m', 'fourgate', 'scan', str(output / 'scan-local.json'),
               '--confirm-test-account', 'disposable-github-issue', '--report-dir', str(output / 'healthy')]
    controls = []
    try:
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
        save(output / 'scan-command.json', {'command': command, 'exit': completed.returncode,
             'stdout': completed.stdout, 'stderr': completed.stderr})
        healthy = json.loads(completed.stdout)['cases'][0]
        assert completed.returncode == 0 and healthy['status'] == 'PASS', healthy
        controls.append({'reference': 'healthy', 'status': healthy['status'],
                         'reason_code': healthy['reason_code'], 'process_exit': completed.returncode})
        authority = (output / 'authority.json').read_bytes()
        assert json.loads(authority) != initial
        response = json.loads((output / 'target-responses.jsonl').read_text().splitlines()[-1])
        # The result selects the lookup; all expected values come from the reviewed request.
        extracted = {'returned_number': response['result']['structuredContent']['number'],
                     'expected_number': approved['issue_number'], **{
                         field: approved[field] for field in ('title', 'body', 'state')}}
        assert response['result']['structuredContent']['title'] != extracted['title']
        # Reuse the deterministic HTTP engine for read-only controls, with proxies disabled.
        previous_opener = readback.OPENER
        readback.OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), readback._NoRedirect())
        try:
            for reference in ['wrong-expectation', 'wrong-identity', 'ambiguous-404', 'unavailable-503', 'missing-identity']:
                values = dict(extracted)
                if reference == 'wrong-expectation':
                    values['title'] = 'INDUCED WRONG EXPECTATION'
                if reference == 'wrong-identity':
                    values['expected_number'] = 74
                replay_config = {**config, 'url_template': config['url_template'].replace('/healthy/', '/' + reference + '/')}
                # Local control needs no credential: the live template still requires a separate token.
                replay_config.pop('token_env')
                readback.validate(replay_config, values)
                evaluation = readback.evaluate_extracted(replay_config, values)
                directory = output / reference
                directory.mkdir()
                save(directory / 'readback.json', replay_config)
                save(directory / 'extracted.json', values)
                row = {'tool': 'update_issue', 'status': evaluation['status'].upper(),
                       'reason_code': evaluation['reason_code'], 'attempts': evaluation['attempts']}
                for key in ('checked_fields', 'mismatched_fields'):
                    if key in evaluation:
                        row[key] = evaluation[key]
                if 'readback_evidence' in evaluation:
                    row['evidence'] = {'readback': evaluation['readback_evidence']}
                rendered = report.build({'scan_version': 1, 'test_account': 'disposable-github-issue',
                                         'cases': [row]}, output / 'scan-local.json')
                # A read-only replay is not a new scan: suppress scan/write retry instructions.
                rendered['cases'][0].pop('repro_steps', None)
                report.write(rendered, directory)
                controls.append({'reference': reference, 'status': row['status'],
                                 'reason_code': row['reason_code'], 'process_exit': None})
        finally:
            readback.OPENER = previous_opener
        assert (output / 'authority.json').read_bytes() == authority
        requests = [json.loads(line) for line in (output / 'target-requests.jsonl').read_text().splitlines()]
        calls = sum(r['method'] == 'tools/call' for r in requests)
        assert calls == 1 and len(seen) == 6
        manifest = {'scope': 'LOCAL_SIMULATION_AND_INDUCED_CONTROLS', 'protected_target_calls': calls,
                    'external_workflow_requests': 0, 'readback_gets': len(seen), 'controls': controls,
                    'authority_unchanged_by_controls': True,
                    'template_sha256': hashlib.sha256((PACK / 'scan.example.json').read_bytes()).hexdigest(),
                    'local_contract_sha256': hashlib.sha256((output / 'scan-local.json').read_bytes()).hexdigest(),
                    'readback_paths': seen, 'control_action_status': 'NOT_RUN',
                    'control_execution': 'read-only readback.evaluate_extracted; process_exit null means no subprocess'}
        expected = [
            ('PASS', 'postcondition_satisfied'), ('FAIL', 'field_mismatch'), ('FAIL', 'field_mismatch'),
            ('UNKNOWN', 'readback_unconfirmed'), ('UNKNOWN', 'readback_unconfirmed'),
            ('UNKNOWN', 'readback_shape_invalid')]
        manifest['expectations_met'] = [(c['status'], c['reason_code']) for c in controls] == expected
        save(output / 'acceptance.json', manifest)
        print(json.dumps(manifest, indent=2))
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
    return 0 if manifest['expectations_met'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
