"""`fourgate guard`: run a local stdio MCP server behind the runtime Outcome Guard.

Startup fails closed: the contracts are validated strictly and the server is
not launched if anything is wrong. Per call, the existing runtime in
wrap/wrap.py is unchanged: verifier faults are UNKNOWN and fail open.
stdout carries only the server's MCP traffic; everything Fourgate says goes
to stderr.
"""
import argparse
import os
import re
import sys

from wrap import outcome

from . import __version__

USAGE = "fourgate guard --contracts PATH [--mode shadow|enforce] [--server LABEL] [--log PATH] -- <server command...>"
SERVER_LABEL = re.compile(r"[A-Za-z0-9._-]{1,64}")
MODE_NOTES = {
    "shadow": "responses are never modified; outcomes are recorded only",
    "enforce": "confirmed FAILs prepend an outcome_failed verdict; UNKNOWN always passes through",
}


def _server_label(value):
    if not SERVER_LABEL.fullmatch(value):
        raise argparse.ArgumentTypeError("must be 1-64 characters from A-Z a-z 0-9 . _ -")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fourgate guard", usage=USAGE, allow_abbrev=False,
        description="Run a local stdio MCP server behind the runtime Outcome Guard. "
                    "Everything after the first -- is the server command, passed through verbatim.")
    parser.add_argument("--contracts", required=True, metavar="PATH", help="Runtime outcome contracts JSON")
    parser.add_argument("--mode", choices=("shadow", "enforce"), default="shadow",
                        help="shadow (default) records outcomes only; enforce prepends a verdict on confirmed FAIL")
    parser.add_argument("--server", type=_server_label, default="server", metavar="LABEL",
                        help="Server label used in records and verdicts as LABEL/tool (default: server)")
    parser.add_argument("--log", metavar="PATH",
                        help="Append outcome records (JSONL) here; default is stderr as [FOURGATE_OUTCOME] lines")
    return parser


def main(argv):
    parser = build_parser()
    # Split on the first "--" ourselves: every later token belongs to the server.
    if "--" in argv:
        split = argv.index("--")
        own, target = argv[:split], argv[split + 1:]
    else:
        own, target = argv, None
    args = parser.parse_args(own)
    if target is None:
        parser.error("missing '--' before the server command")
    if not target:
        parser.error("no server command after '--'")
    try:
        contracts = outcome.load_strict(args.contracts)
    except ValueError as exc:
        print(f"fourgate guard: contract error: {exc}", file=sys.stderr)
        return 2
    log_path = os.path.abspath(args.log) if args.log else None
    _banner(args, contracts, log_path, target)
    # Imported late: wrap.py adds wrap/ to sys.path for its own bare imports.
    from wrap import wrap as runtime
    try:
        rc = runtime.run_proxy(target, None, args.server, None, contracts, args.mode, log_path)
    except OSError as exc:
        print(f"fourgate: failed to start wrapped server: {exc}", file=sys.stderr)
        return 1
    return rc if rc is not None else 1


def _banner(args, contracts, log_path, target):
    """Startup summary on stderr. Never prints env values or target arguments."""
    names = sorted(outcome.secret_env_names(contracts))
    missing = [name for name in names if name not in os.environ]
    withheld = ", ".join(
        f"{name} (NOT SET - read-back will likely be UNKNOWN)" if name in missing else f"{name} (set)"
        for name in names) or "none"
    lines = [
        f"fourgate guard {__version__}",
        f"  mode: {args.mode} - {MODE_NOTES[args.mode]}",
        f"  server label: {args.server}",
        f"  contracts: {os.path.abspath(args.contracts)}",
        f"  protected tools: {', '.join(sorted(contracts['tools']))}",
        f"  withheld from server env: {withheld}",
        f"  outcome log: {log_path or 'stderr ([FOURGATE_OUTCOME] lines)'}",
        f"  target: {os.path.basename(target[0])} (+{len(target) - 1} args)",
    ]
    lines += [f"fourgate guard: WARNING: {name} is not set; read-back will likely be UNKNOWN" for name in missing]
    print("\n".join(lines), file=sys.stderr, flush=True)
