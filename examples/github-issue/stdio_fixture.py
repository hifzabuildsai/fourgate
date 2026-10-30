"""Local synthetic Issue update only; not a GitHub MCP implementation."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    directory = parser.parse_args().directory
    for raw in sys.stdin:
        request = json.loads(raw)
        with (directory / 'target-requests.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(request) + '\n')
        method = request['method']
        params = request.get('params', {})
        meta = params.get('_meta', {})
        if meta.get('io.modelcontextprotocol/protocolVersion') != '2026-07-28':
            raise ValueError('fixture requires explicit native protocol')
        if method == 'server/discover':
            result = {'supportedVersions': ['2026-07-28'], 'capabilities': {'tools': {}}}
        elif method == 'tools/list':
            result = {'tools': [{'name': 'issue_write', 'inputSchema': {'type': 'object'}}]}
        elif method == 'tools/call' and params['name'] == 'issue_write':
            # Independently cap the entire local demonstration to one protected call.
            with (directory / 'write.claim').open('x') as handle:
                handle.write('one local simulated update\n')
            arguments = params['arguments']
            approved = json.loads((directory / 'approved-request.json').read_text())
            if arguments != approved:
                raise ValueError('request differs from local review card')
            if arguments.get('method') != 'update':
                raise ValueError('reference pack permits only issue_write update')
            existing = json.loads((directory / 'authority.json').read_text())
            if existing['number'] != arguments['issue_number']:
                raise ValueError('preselected local Issue is unavailable')
            document = {'number': arguments['issue_number'], **{
                field: arguments[field] for field in ('title', 'body', 'state')}}
            (directory / 'authority.json').write_text(json.dumps(document), encoding='utf-8')
            # Mirror the official issue_write minimal success shape. The
            # approved Issue number and expected fields never come from it.
            result = {'structuredContent': {'id': 'synthetic-node-73',
                      'url': 'https://github.example/reference-owner/disposable/issues/73'},
                      'content': [], 'isError': False}
        else:
            raise ValueError('unapproved fixture method')
        result['resultType'] = 'complete'
        if method != 'tools/call':
            result.update(ttlMs=0, cacheScope='private')
        response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        with (directory / 'target-responses.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(response) + '\n')
        print(json.dumps(response), flush=True)


if __name__ == '__main__':
    main()
