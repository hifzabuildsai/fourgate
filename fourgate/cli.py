"""The Fourgate command line interface."""
import argparse
import json
import sys

from .scan import scan
from . import report as reporting
from . import summary as summarizing


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fourgate")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("scan", help="Exercise explicitly contracted writes in a test account")
    command.add_argument("contract", help="Per-server JSON scan contract")
    command.add_argument("--confirm-test-account", required=True,
                         help="Exact test account label in the contract; required to run writes")
    command.add_argument("--report-dir", help="Write private JSON and single-file HTML reports here")
    summary_cmd = sub.add_parser("summary", help="Summarize runtime outcome logs into a local HTML page")
    summary_cmd.add_argument("logs", nargs="+", help="One or more outcomes.jsonl files written by wrap.py")
    summary_cmd.add_argument("--out", default="fourgate-summary.html", help="HTML output path")
    summary_cmd.add_argument("--json", action="store_true", help="Print the summary as JSON instead of text")
    args = parser.parse_args(argv)
    if args.command == "summary":
        return _summary(args)
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


def _summary(args):
    try:
        records, skipped = summarizing.load(args.logs)
    except OSError as exc:
        print(f"fourgate: could not read outcome log: {exc}", file=sys.stderr)
        return 2
    if not records:
        print(f"fourgate: no outcome records found ({skipped} malformed line(s) skipped)", file=sys.stderr)
        return 2
    result = summarizing.summarize(records, skipped)
    try:
        reporting.write_private_file(args.out, summarizing.render_html(result))
    except OSError as exc:
        print(f"fourgate: could not write summary: {exc}", file=sys.stderr)
        return 2
    print(f"fourgate: summary written to {args.out}", file=sys.stderr)
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else summarizing.text(result))
    return 0
