"""The Fourgate command line interface."""
import argparse
import json
import sys

from .scan import scan
from . import report as reporting


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fourgate")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("scan", help="Exercise explicitly contracted writes in a test account")
    command.add_argument("contract", help="Per-server JSON scan contract")
    command.add_argument("--confirm-test-account", required=True,
                         help="Exact test account label in the contract; required to run writes")
    command.add_argument("--report-dir", help="Write private JSON and single-file HTML reports here")
    args = parser.parse_args(argv)
    if args.command == "scan":
        try:
            raw = scan(args.contract, args.confirm_test_account)
        except (OSError, ValueError) as exc:
            print(f"fourgate: scan configuration error: {exc}", file=sys.stderr)
            return 2
        # Both stdout and on-disk artifacts receive the same redacted copy.
        redacted = reporting.build(raw, args.contract)
        if args.report_dir:
            try:
                paths = reporting.write(redacted, args.report_dir)
            except OSError as exc:
                print(f"fourgate: could not write reports: {exc}", file=sys.stderr)
                return 2
            print(f"fourgate: reports written to {paths[0]} and {paths[1]}", file=sys.stderr)
        print(json.dumps(redacted, indent=2, sort_keys=True))
        return 1 if any(row["status"] != "PASS" for row in raw["cases"]) else 0
    return 2
