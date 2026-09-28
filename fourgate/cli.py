"""The Fourgate command line interface."""
import argparse
import json
import sys

from .scan import scan


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fourgate")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("scan", help="Exercise explicitly contracted writes in a test account")
    command.add_argument("contract", help="Per-server JSON scan contract")
    command.add_argument("--confirm-test-account", required=True,
                         help="Exact test account label in the contract; required to run writes")
    args = parser.parse_args(argv)
    if args.command == "scan":
        try:
            report = scan(args.contract, args.confirm_test_account)
        except (OSError, ValueError) as exc:
            print(f"fourgate: scan configuration error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if any(row["status"] != "PASS" for row in report["cases"]) else 0
    return 2
