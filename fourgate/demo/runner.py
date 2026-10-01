"""`fourgate demo`: a one-command, zero-credential walk through the Outcome Guard.

Every scene is a real MCP session against the bundled demo connector
(fourgate.demo.server); scenes 2-5 run it behind a real `fourgate guard`
subprocess with the bundled verifier (fourgate.demo.verifier). Nothing is
reimplemented here: each narrated status is read from the actual response, the
actual demo store or the actual outcome log line for that scene, and a
self-check compares them with what the scene is meant to show.

Local only: no API keys, no network, no change to the user's environment. The
demo store and runtime contract live in a temporary directory; --out receives
exactly two files, demo-outcomes.jsonl and fourgate-demo-summary.html.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from wrap import outcome

from .. import report as reporting
from .. import summary as summarizing
from ..scan import StdioClient

USAGE = "fourgate demo [--out DIR] [--pace SECONDS]"
DESCRIPTION = ("Run a local, zero-credential demo of the Outcome Guard: five real MCP sessions against a "
               "simulated connector, then a summary page. No API keys, no network.")
HEADER = "FOURGATE DEMO - local only: no API keys, no network, nothing leaves this machine"
HONESTY = "Simulated connector; a local file stands in for the system of record."
LOG_NAME = "demo-outcomes.jsonl"
PAGE_NAME = "fourgate-demo-summary.html"
SERVER_LABEL = "demo-crm"
TOOL = "create_issue"
TITLE = "Q3 renewal follow-up"
PROTOCOL = "2024-11-05"
MARKER = "[FOURGATE]"
CALL_TIMEOUT_MS = 15000
MAX_PACE = 10.0

# Each scene's expectation is what the self-check holds the real run to.
# "verdict": reason code of the [FOURGATE] outcome_failed item expected first, or None for an unchanged response.
# "issues": issues expected in the system of record afterwards.
# "log": (mode, status, reason_code) of the outcome record the scene must append, or None for no record.
SCENES = [
    {"id": "S1", "title": "Without Fourgate: broken connector, called directly",
     "setup": "The connector reports success but never saves the issue. No Fourgate in the path.",
     "guard": None, "connector": "broken", "verifier": "normal",
     "expect": {"verdict": None, "issues": 0, "log": None},
     "takeaway": "The agent believes the issue exists. It does not."},
    {"id": "S2", "title": "Fourgate enforce: broken connector",
     "setup": "Same broken connector, now behind `fourgate guard --mode enforce`.",
     "guard": "enforce", "connector": "broken", "verifier": "normal",
     "expect": {"verdict": "record_missing", "issues": 0, "log": ("enforce", "fail", "record_missing")},
     "takeaway": "The agent is told the write did not land, before it can report success."},
    {"id": "S3", "title": "Fourgate enforce: healthy connector",
     "setup": "A healthy connector that really saves the issue, behind `fourgate guard --mode enforce`.",
     "guard": "enforce", "connector": "healthy", "verifier": "normal",
     "expect": {"verdict": None, "issues": 1, "log": ("enforce", "pass", "postcondition_satisfied")},
     "takeaway": "A real success passes through untouched."},
    {"id": "S4", "title": "Fourgate shadow: broken connector",
     "setup": "The broken connector behind `fourgate guard --mode shadow` (the default mode).",
     "guard": "shadow", "connector": "broken", "verifier": "normal",
     "expect": {"verdict": None, "issues": 0, "log": ("shadow", "fail", "record_missing")},
     "takeaway": "The agent is unaffected; you still learn the write did not land."},
    {"id": "S5", "title": "Fourgate enforce: broken connector, system of record unreachable",
     "setup": "The broken connector in enforce mode, but the read-back cannot reach the system of record.",
     "guard": "enforce", "connector": "broken", "verifier": "crash",
     "expect": {"verdict": None, "issues": 0, "log": ("enforce", "unknown", "verifier_error")},
     "takeaway": ("Fourgate could not confirm either way: recorded UNKNOWN, never PASS, "
                  "and the call is not blocked.")},
]


def _pace(value):
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a number of seconds") from None
    if not 0 <= seconds <= MAX_PACE:
        raise argparse.ArgumentTypeError(f"must be from 0 to {MAX_PACE:g}")
    return seconds


def build_parser():
    parser = argparse.ArgumentParser(prog="fourgate demo", usage=USAGE, description=DESCRIPTION, allow_abbrev=False)
    parser.add_argument("--out", default="fourgate-demo", metavar="DIR",
                        help=f"Directory for {LOG_NAME} and {PAGE_NAME} (default: ./fourgate-demo); "
                             "no other file there is touched")
    parser.add_argument("--pace", type=_pace, default=0.0, metavar="SECONDS",
                        help="Pause between narrated steps (twice as long between scenes), for screen recording "
                             "(default 0, max 10)")
    return parser


def runtime_contract():
    """The demo's runtime contract; written to a temporary directory and loaded with outcome.load_strict."""
    return {
        "contract_version": 1,
        "tools": {
            TOOL: {
                "extract": {
                    "issue_id": {"source": "result", "path": "result.structuredContent.issue_id"},
                    "title": {"source": "arguments", "path": "title"},
                },
                "verifier": {"command": ["{python}", "-m", "fourgate.demo.verifier"], "timeout_ms": 2000},
                "allowed_failure_reasons": ["record_missing", "field_mismatch"],
                "recovery": "stop",
            }
        },
    }


def write_contract(directory):
    path = Path(directory) / "demo-contracts.json"
    path.write_text(json.dumps(runtime_contract(), indent=2), encoding="utf-8")
    return path


def server_command():
    return [sys.executable, "-m", "fourgate.demo.server"]


def package_root():
    """Directory containing the `fourgate` and `wrap` packages (site-packages or a source checkout)."""
    return str(Path(__file__).resolve().parent.parent.parent)


def child_env(store, connector, verifier):
    env = os.environ.copy()
    env["FOURGATE_DEMO_STORE"] = str(store)
    env["FOURGATE_DEMO_MODE"] = connector
    env["FOURGATE_DEMO_VERIFIER"] = verifier
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = package_root() + (os.pathsep + existing if existing else "")
    return env


def _say(text=""):
    # ASCII only: Windows code pages garble anything else.
    print(text.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


class Demo:
    def __init__(self, out_dir, pace, work_dir):
        self.log_path = out_dir / LOG_NAME
        self.page_path = out_dir / PAGE_NAME
        self.pace = pace
        self.work_dir = work_dir
        self.contracts = None
        self.baseline = None  # S1's content: what the connector itself says
        self.problems = []  # (scene id, title, message)

    def beat(self):
        if self.pace:
            time.sleep(self.pace)

    # --- running a scene -------------------------------------------------------

    def _command(self, scene):
        if scene["guard"] is None:
            return server_command()
        return [sys.executable, "-m", "fourgate", "guard", "--contracts", str(self.contracts),
                "--mode", scene["guard"], "--server", SERVER_LABEL, "--log", str(self.log_path),
                "--", *server_command()]

    def _session(self, command, env):
        """initialize + tools/list, then one tools/call create_issue. Returns the response object."""
        client = StdioClient(command, str(self.work_dir), env)
        try:
            tools = client.initialize(PROTOCOL)
            if TOOL not in tools:
                raise RuntimeError(f"{TOOL} is not advertised")
            _, response = client.request("tools/call", {"name": TOOL, "arguments": {"title": TITLE}},
                                         CALL_TIMEOUT_MS)
            return response
        finally:
            # Close stdin first so guard and server exit on their own; close() then reaps or kills.
            try:
                client.proc.stdin.close()
                client.proc.wait(timeout=5)
            except Exception:
                pass
            client.close()

    def run_scene(self, number, scene):
        store = self.work_dir / f"store-{scene['id'].lower()}.json"
        before = _read_log(self.log_path)
        response, error = None, None
        try:
            response = self._session(self._command(scene), child_env(store, scene["connector"], scene["verifier"]))
        except Exception as exc:
            error = f"MCP session failed ({type(exc).__name__}: {exc})"
        records = _read_log(self.log_path)[len(before):]
        observed = {"response": response, "error": error, "issues": _count_issues(store), "records": records}
        if scene["id"] == "S1" and response is not None:
            self.baseline = _content(response)
        self.narrate(number, scene, observed)
        return observed

    # --- narration and self-check -----------------------------------------------

    def narrate(self, number, scene, observed):
        problems = []
        expect = scene["expect"]
        _say(f"[{number}/{len(SCENES)}] {scene['id']}  {scene['title']}")
        _say(f"  {scene['setup']}")
        self.beat()

        response = observed["response"]
        if response is None:
            problems.append(observed["error"] or "no response")
            _say("  Agent receives:  no response")
        else:
            problems += self._narrate_response(scene, response)
        self.beat()

        issues = observed["issues"]
        _say(f"  System of record: {issues} issue{'' if issues == 1 else 's'} saved")
        if issues != expect["issues"]:
            problems.append(f"system of record: expected {expect['issues']} issue(s), found {issues}")
        self.beat()

        records = observed["records"]
        got = [_log_tuple(r) for r in records]
        for mode, status, reason in got:
            _say(f"  Outcome log:      {str(status).upper()} {reason}  (mode: {mode})")
        if not got:
            _say("  Outcome log:      no record (Fourgate is not in the path)" if scene["guard"] is None
                 else "  Outcome log:      no record")
        wanted = [expect["log"]] if expect["log"] else []
        if got != wanted:
            problems.append(f"outcome log: expected {_describe(wanted)}, got {_describe(got)}")
        self.beat()

        if problems:
            for problem in problems:
                _say(f"  SELF-CHECK MISMATCH: {problem}")
                self.problems.append((scene["id"], scene["title"], problem))
        else:
            _say(f"  -> {scene['takeaway']}")
        _say()
        # A longer pause between scenes than between steps.
        self.beat()
        self.beat()

    def _narrate_response(self, scene, response):
        problems = []
        expect = scene["expect"]
        result = response.get("result")
        if not isinstance(result, dict):
            return [f"response has no result ({_describe_error(response)})"]
        content = result.get("content") if isinstance(result.get("content"), list) else []
        is_error = result.get("isError")
        texts = [_item_text(item) for item in content]
        verdict = _parse_verdict(texts[0]) if texts and texts[0].startswith(MARKER) else None

        if verdict is not None:
            evidence = verdict.get("evidence") if isinstance(verdict.get("evidence"), dict) else {}
            reason = evidence.get("reason_code")
            _say(f"  Agent receives, first:  {MARKER} {verdict.get('kind')} "
                 f"(reason: {reason}, recovery: {verdict.get('recovery')})")
            for text in texts[1:]:
                _say(f"  then the original:      \"{text}\"")
            _say(f"  isError={_flag(is_error)}")
            if expect["verdict"] is None:
                problems.append(f"expected an unchanged response, got a {MARKER} verdict ({reason})")
            else:
                if verdict.get("kind") != "outcome_failed" or reason != expect["verdict"]:
                    problems.append(f"expected {MARKER} outcome_failed {expect['verdict']}, "
                                    f"got {verdict.get('kind')} {reason}")
                if self.baseline is None or content[1:] != self.baseline:
                    problems.append("the connector's original content was not preserved after the verdict")
        else:
            for text in texts or ["(no text content)"]:
                _say(f"  Agent receives:  \"{text}\"  (isError={_flag(is_error)})")
            if scene["id"] != "S1":
                same = self.baseline is not None and content == self.baseline
                _say("  The response is identical to scene S1: no [FOURGATE] verdict" if same
                     else "  The response differs from scene S1")
                if not same:
                    problems.append("response content differs from the connector's own response (S1)")
            if expect["verdict"] is not None:
                problems.append(f"expected a {MARKER} outcome_failed {expect['verdict']} verdict first, got none")
            if any(text.startswith(MARKER) for text in texts):
                problems.append(f"unexpected {MARKER} item in the response")
            if not texts or not texts[0]:
                problems.append("the connector returned no success text")
        if is_error is not False:
            problems.append(f"expected isError=false, got {_flag(is_error)}")
        return problems

    # --- after the scenes -----------------------------------------------------

    def finish(self):
        records = _read_log(self.log_path)
        got = [_log_tuple(r) for r in records]
        wanted = [s["expect"]["log"] for s in SCENES if s["expect"]["log"]]
        if got != wanted:
            self.problems.append(("log", LOG_NAME, f"expected {_describe(wanted)}, got {_describe(got)}"))

        loaded, skipped = summarizing.load([self.log_path])
        result = summarizing.summarize(loaded, skipped)
        totals = result["totals"]
        expected_totals = {s: sum(1 for t in wanted if t[1] == s) for s in summarizing.STATUSES}
        if totals != expected_totals:
            self.problems.append(("summary", "fourgate summary totals",
                                  f"expected {_totals(expected_totals)}, got {_totals(totals)}"))
        page = None
        if loaded:
            page = reporting.write_private_file(self.page_path, summarizing.render_html(result))

        _say("Summary")
        _say(f"  Totals (from fourgate summary): {_totals(totals)}")
        _say(f"  Outcome log:  {self.log_path.resolve()}")
        _say(f"  Summary page: {page.resolve().as_uri()}" if page else "  Summary page: not written (no outcome records)")
        _say()
        if self.problems:
            _say(f"SELF-CHECK FAILED: {len(self.problems)} expectation(s) did not hold")
            for where, title, problem in self.problems:
                _say(f"  {where} ({title}): {problem}")
            return 1
        _say("Self-check: every scene behaved as narrated.")
        return 0


def _read_log(path):
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({})
    return records


def _log_tuple(record):
    if not isinstance(record, dict):
        return (None, None, None)
    return (record.get("mode"), record.get("status"), record.get("reason_code"))


def _describe(tuples):
    if not tuples:
        return "no record"
    return "; ".join(f"{str(status).upper()} {reason} ({mode})" for mode, status, reason in tuples)


def _totals(totals):
    return f"PASS {totals['pass']} / FAIL {totals['fail']} / UNKNOWN {totals['unknown']}"


def _count_issues(store):
    if not store.exists():
        return 0
    try:
        rows = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return len(rows) if isinstance(rows, list) else 0


def _content(response):
    result = response.get("result") if isinstance(response, dict) else None
    content = result.get("content") if isinstance(result, dict) else None
    return content if isinstance(content, list) else None


def _item_text(item):
    return item.get("text", "") if isinstance(item, dict) and isinstance(item.get("text"), str) else ""


def _parse_verdict(text):
    try:
        verdict = json.loads(text[len(MARKER):].strip())
    except json.JSONDecodeError:
        return {}
    return verdict if isinstance(verdict, dict) else {}


def _flag(value):
    return "false" if value is False else "true" if value is True else "missing"


def _describe_error(response):
    error = response.get("error") if isinstance(response, dict) else None
    return f"error: {error.get('message')}" if isinstance(error, dict) else "malformed response"


def main(argv):
    args = build_parser().parse_args(argv)
    # Absolute once, up front: guard runs in another cwd and must get absolute paths.
    out_dir = Path(args.out).resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        # Truncate: each run's log holds exactly this run's records.
        with open(out_dir / LOG_NAME, "w", encoding="utf-8"):
            pass
    except OSError as exc:
        print(f"fourgate demo: cannot write to {out_dir}: {exc.strerror or type(exc).__name__}", file=sys.stderr)
        return 2

    _say(HEADER)
    _say(HONESTY)
    _say()
    _say(f"An agent asks the {SERVER_LABEL} connector to {TOOL} \"{TITLE}\".")
    _say("Each scene is a real MCP session; scenes S2-S5 run through a real `fourgate guard` process,")
    _say("which reads the system of record back after the connector reports success.")
    _say()
    with tempfile.TemporaryDirectory(prefix="fourgate-demo-", ignore_cleanup_errors=True) as work:
        work = Path(work).resolve()
        demo = Demo(out_dir, args.pace, work)
        demo.beat()
        demo.beat()
        demo.contracts = write_contract(work)
        try:
            outcome.load_strict(str(demo.contracts))
        except ValueError as exc:
            print(f"fourgate demo: generated contract is invalid: {exc}", file=sys.stderr)
            return 1
        for number, scene in enumerate(SCENES, 1):
            demo.run_scene(number, scene)
        return demo.finish()
