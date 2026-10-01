"""`fourgate init`: write a scan contract, runtime contract and read-back config from flags.

Deterministic: no prompts, no LLM, no inference. init never starts the server,
never calls tools/list and never makes a network request. It never reads an
environment variable's value (only whether the name is present, for a NOTE),
and no flag takes a secret: the generated files carry env var names only.

Everything is built in memory, written to a temporary directory and validated
there with the same loaders scan, guard and doctor use. Only then are the
three files copied into --dir. Any usage or validation error exits 2 with a
one-line reason and writes nothing.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from wrap import outcome

from . import guard as guarding
from . import readback
from . import scan as scanning
from . import verify_http

USAGE = ("fourgate init --tool NAME --test-account LABEL "
         "(--id-path PATH | --id-regex PATTERN | --id-json-field FIELD) --readback-url URL_TEMPLATE "
         "--expect RESPONSE_PATH=ARG_NAME [--expect ...] --arg NAME=VALUE [--arg ...] [--arg-json NAME=JSON] "
         "[--token-env NAME] [--auth bearer|header|basic] [--auth-header HEADER] [--username-env NAME] "
         "[--missing-status CODE] [--server LABEL] [--dir DIR] [--force] -- <server command...>")
DESCRIPTION = ("Write readback.json, runtime.json and scan.json for one write tool. "
               "Does not start the server or contact any endpoint. "
               "Everything after the first -- is the server command.")
FILES = ("readback.json", "runtime.json", "scan.json")
RECORD_ID = "record_id"
TEXT_PATH = "result.content.0.text"
UNSAFE_NAME_CHAR = re.compile(r"[^A-Za-z0-9_]")


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def build_parser():
    parser = _Parser(prog="fourgate init", usage=USAGE, description=DESCRIPTION, allow_abbrev=False)
    parser.add_argument("--tool", required=True, metavar="NAME", help="The write tool to protect")
    parser.add_argument("--test-account", required=True, metavar="LABEL",
                        help="Label of the disposable test account the scan writes to")
    record = parser.add_mutually_exclusive_group(required=True)
    record.add_argument("--id-path", metavar="PATH",
                        help="Record id path in the JSON-RPC response, e.g. result.structuredContent.id")
    record.add_argument("--id-regex", metavar="PATTERN",
                        help="Regex with one capture group, applied to result.content.0.text")
    record.add_argument("--id-json-field", metavar="FIELD",
                        help="Field of the JSON object embedded in result.content.0.text")
    parser.add_argument("--readback-url", required=True, metavar="URL_TEMPLATE",
                        help="GET URL for the record; must contain {record_id}")
    parser.add_argument("--expect", action="append", required=True, metavar="RESPONSE_PATH=ARG_NAME",
                        help="Read-back response field that must equal a tool argument (repeatable)")
    parser.add_argument("--arg", action="append", default=[], metavar="NAME=VALUE",
                        help="String argument the scan sends (repeatable)")
    parser.add_argument("--arg-json", action="append", default=[], metavar="NAME=JSON",
                        help="Non-string argument the scan sends, as JSON (repeatable)")
    parser.add_argument("--token-env", metavar="NAME", help="Env var NAME holding the read credential")
    parser.add_argument("--auth", choices=("bearer", "header", "basic"),
                        help="How the read credential is sent (default bearer when --token-env is given)")
    parser.add_argument("--auth-header", metavar="HEADER", help="Header name for --auth header")
    parser.add_argument("--username-env", metavar="NAME", help="Env var NAME holding the username for --auth basic")
    parser.add_argument("--missing-status", action="append", type=int, default=[], metavar="CODE",
                        help="HTTP status that confirms the record is missing (repeatable), e.g. 404")
    parser.add_argument("--server", type=guarding._server_label, default="server", metavar="LABEL",
                        help="Server label for the printed guard/doctor commands (default: server)")
    parser.add_argument("--dir", default=os.path.join(".", "fourgate-config"), metavar="DIR",
                        help="Output directory (default: ./fourgate-config)")
    parser.add_argument("--force", action="store_true", help="Overwrite the three generated files if they exist")
    return parser


def _pairs(values, flag, shape="NAME=VALUE"):
    pairs = []
    for value in values:
        name, sep, rest = value.partition("=")
        if not sep or not name:
            raise UsageError(f"{flag} must be {shape} (got {value!r})")
        pairs.append((name, rest))
    return pairs


def _arguments(args):
    arguments = {}
    for name, value in _pairs(args.arg, "--arg"):
        if name in arguments:
            raise UsageError(f"argument {name!r} is given more than once")
        arguments[name] = value
    for name, raw in _pairs(args.arg_json, "--arg-json"):
        if name in arguments:
            raise UsageError(f"argument {name!r} is given more than once")
        try:
            arguments[name] = json.loads(raw)
        except ValueError:
            raise UsageError(f"--arg-json {name}: value is not valid JSON") from None
    return arguments


def _record_selector(args):
    if args.id_path is not None:
        if not args.id_path.startswith("result.") or any(not part for part in args.id_path.split(".")):
            raise UsageError("--id-path must be a dotted path into the response starting with 'result.' "
                             "(e.g. result.structuredContent.id)")
        return {"source": "result", "path": args.id_path}
    if args.id_regex is not None:
        return {"source": "result", "path": TEXT_PATH, "parse": "regex", "pattern": args.id_regex}
    return {"source": "result", "path": TEXT_PATH, "parse": "embedded_json", "field": args.id_json_field}


def _extract_and_expected(args, arguments):
    extract = {RECORD_ID: _record_selector(args)}
    expected = {}
    for response_path, arg_name in _pairs(args.expect, "--expect", "RESPONSE_PATH=ARG_NAME"):
        if not arg_name:
            raise UsageError(f"--expect {response_path}= needs an argument name after '='")
        if response_path in expected:
            raise UsageError(f"--expect response path {response_path!r} is given more than once")
        if arg_name.split(".")[0] not in arguments:
            raise UsageError(f"--expect {response_path}={arg_name}: {arg_name.split('.')[0]!r} is not "
                             "one of the --arg/--arg-json names, so the scan would not send it")
        if outcome._path_get(arguments, arg_name) is outcome.MISSING:
            raise UsageError(f"--expect {response_path}={arg_name}: path {arg_name!r} is not in the scan arguments")
        name = UNSAFE_NAME_CHAR.sub("_", arg_name)
        if name == RECORD_ID or name in extract:
            raise UsageError(f"--expect {response_path}={arg_name}: extracted name {name!r} is reserved or "
                             "already used")
        extract[name] = {"source": "arguments", "path": arg_name}
        expected[response_path] = name
    return extract, expected


def _readback(args, expected):
    if "{" + RECORD_ID + "}" not in args.readback_url:
        raise UsageError("--readback-url must contain {record_id}")
    if args.auth == "header" and not args.auth_header:
        raise UsageError("--auth header requires --auth-header HEADER")
    if args.auth_header and args.auth != "header":
        raise UsageError("--auth-header is only used with --auth header")
    if args.auth == "basic" and not args.username_env:
        raise UsageError("--auth basic requires --username-env NAME")
    if args.username_env and args.auth != "basic":
        raise UsageError("--username-env is only used with --auth basic")
    config = {"type": "http", "url_template": args.readback_url, "expected_fields": expected}
    if args.token_env is not None:
        config["token_env"] = args.token_env
    if args.auth == "bearer":
        config["auth"] = {"scheme": "bearer"}
    elif args.auth == "header":
        config["auth"] = {"scheme": "header", "header": args.auth_header}
    elif args.auth == "basic":
        config["auth"] = {"scheme": "basic", "username_env": args.username_env}
    if args.missing_status:
        config["missing_statuses"] = sorted(set(args.missing_status))
    config.update(attempts=3, interval_ms=250, timeout_ms=1500)
    return config


def _scan_command(target, cwd):
    """scan runs the server in the contract's directory: pin relative paths that exist here."""
    command, rewrites = [], []
    for token in target:
        if token and not os.path.isabs(token) and os.path.exists(os.path.join(cwd, token)):
            absolute = os.path.abspath(os.path.join(cwd, token))
            rewrites.append((token, absolute))
            token = absolute
        command.append(token)
    return command, rewrites


def build(args, target, cwd):
    """Return ({filename: document}, scan command rewrites). Raises UsageError."""
    if not args.tool:
        raise UsageError("--tool must not be empty")
    if not args.test_account.strip():
        raise UsageError("--test-account must not be empty")
    arguments = _arguments(args)
    extract, expected = _extract_and_expected(args, arguments)
    config = _readback(args, expected)
    secret_env = readback.credential_envs(config)
    reasons = ["field_mismatch"] + (["record_missing"] if args.missing_status else [])
    runtime = {"contract_version": 1, "tools": {args.tool: {
        "extract": extract,
        "verifier": {"command": ["{python}", "-m", "fourgate.verify_http", "readback.json"], "cwd": ".",
                     "timeout_ms": outcome.MAX_VERIFIER_TIMEOUT_MS, "secret_env": secret_env},
        "allowed_failure_reasons": reasons,
        "recovery": "stop",
    }}}
    command, rewrites = _scan_command(target, cwd)
    scan = {
        "scan_version": 1,
        "server": {"transport": "stdio", "command": command, "test_account": args.test_account,
                   "protocol_version": "2024-11-05", "call_timeout_ms": scanning.MAX_CALL_TIMEOUT_MS},
        "write_tools": [args.tool],
        "cases": [{"tool": args.tool, "arguments": arguments,
                   "outcome_contract": {"record_id_field": RECORD_ID, "extract": extract},
                   "readback": config}],
    }
    return {"readback.json": config, "runtime.json": runtime, "scan.json": scan}, rewrites


def _dump(document):
    return json.dumps(document, indent=2) + "\n"


def validate(documents, test_account):
    """Write the files to a temporary directory and load them with the real loaders."""
    with tempfile.TemporaryDirectory(prefix="fourgate-init-") as staging:
        for name, document in documents.items():
            with open(os.path.join(staging, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(_dump(document))
        try:
            extract = documents["scan.json"]["cases"][0]["outcome_contract"]["extract"]
            readback.validate(documents["readback.json"], extract)
            verify_http.load_config(os.path.join(staging, "readback.json"), extract)
            outcome.load_strict(os.path.join(staging, "runtime.json"))
            scanning.load_contract(os.path.join(staging, "scan.json"), test_account)
        except (ValueError, OSError) as exc:
            raise UsageError(str(exc)) from None


def _quote(tokens):
    return subprocess.list2cmdline(tokens) if os.name == "nt" else shlex.join(tokens)


def _ascii(text):
    return text.encode("ascii", "backslashreplace").decode("ascii")


def _say(text=""):
    print(_ascii(text), flush=True)


def main(argv):
    own, target = guarding.split_argv(list(argv))
    parser = build_parser()
    try:
        args = parser.parse_args(own)
        if target is None:
            raise UsageError("missing '--' before the server command")
        if not target or not target[0]:
            raise UsageError("no server command after '--'")
        cwd = os.getcwd()
        documents, rewrites = build(args, target, cwd)
        out_dir = os.path.normpath(args.dir)
        if os.path.exists(out_dir) and not os.path.isdir(out_dir):
            raise UsageError(f"--dir {out_dir} exists and is not a directory")
        existing = [name for name in FILES if os.path.exists(os.path.join(out_dir, name))]
        if existing and not args.force:
            raise UsageError(f"{', '.join(existing)} already exist in {out_dir}; pass --force to overwrite")
        validate(documents, args.test_account)
    except UsageError as exc:
        print(_ascii(f"fourgate init: error: {exc}"), file=sys.stderr)
        return 2
    try:
        os.makedirs(out_dir, exist_ok=True)
        for name in FILES:
            with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(_dump(documents[name]))
    except OSError as exc:
        print(_ascii(f"fourgate init: error: could not write {out_dir}: {exc.strerror or type(exc).__name__}"),
              file=sys.stderr)
        return 2
    _report(args, out_dir, target, rewrites, documents)
    return 0


def _report(args, out_dir, target, rewrites, documents):
    runtime_path = os.path.join(out_dir, "runtime.json")
    scan_path = os.path.join(out_dir, "scan.json")
    server = _quote(target)
    _say("fourgate init: wrote")
    for name in FILES:
        _say(f"  {os.path.join(out_dir, name)}")
    for token, absolute in rewrites:
        _say(f"scan.json: server command argument {token} -> {absolute} (scan runs the server in {out_dir})")
    _say()
    _say("Next steps:")
    _say(f"  fourgate doctor --contracts {_quote([runtime_path])} --server {args.server} "
         f"--log outcomes.jsonl -- {server}")
    _say(f"  fourgate scan {_quote([scan_path])} --confirm-test-account {_quote([args.test_account])} "
         "--report-dir fourgate-report")
    _say(f"  fourgate guard --contracts {_quote([runtime_path])} --mode shadow --server {args.server} "
         f"--log outcomes.jsonl -- {server}")
    _say("  fourgate summary outcomes.jsonl")
    _say()
    _say("CAUTION: scan performs real writes: use a disposable test account only.")
    for name in readback.credential_envs(documents["readback.json"]):
        if name not in os.environ:
            _say(f"NOTE: {name} is not set in this shell; set it before doctor, scan or guard.")
    if not args.missing_status:
        _say("NOTE: a missing record will be UNKNOWN, not FAIL, until you confirm the read credential can see "
             "records and add --missing-status 404.")
