"""`fourgate doctor`: non-destructive preflight for a `fourgate guard` setup.

Takes the same arguments as guard. It never sends tools/call, never runs a
verifier, never makes a network request, and never creates or modifies a
file. With a server command after `--`, it starts the server only for
initialize / notifications/initialized / tools/list, with verifier
secret_env names withheld exactly as guard does, then stops it.
The report goes to stdout as ASCII; usage errors go to stderr.
"""
import os
import shutil
import urllib.parse

from wrap import outcome

from . import __version__
from . import guard as guarding
from . import readback
from . import scan
from . import verify_http

USAGE = "fourgate doctor --contracts PATH [--mode shadow|enforce] [--server LABEL] [--log PATH] [-- <server command...>]"
DESCRIPTION = ("Check a fourgate guard setup without side effects: no tools/call, no verifier run, "
               "no network request, no file written. Pass the server command after -- to also check "
               "the MCP handshake and tool discovery.")
PROTOCOL = "2024-11-05"
STARTUP_HEADROOM_MS = 300
# INFO lines are statements, not checks: they never affect the verdict.
TAGS = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "INFO": "[INFO]"}
VERIFY_HTTP_USAGE = "verify_http command must be: {python} -m fourgate.verify_http <readback-config.json>"
LATER_SECTIONS = ("Verifiers", "Credentials", "MCP server", "Mode and log", "Write safety")


class Report:
    def __init__(self):
        self.counts = {tag: 0 for tag in TAGS}

    def line(self, text=""):
        # ASCII only: Windows code pages garble anything else.
        print(text.encode("ascii", "backslashreplace").decode("ascii"), flush=True)

    def section(self, title):
        self.line()
        self.line(title)

    def add(self, status, text):
        self.counts[status] += 1
        self.line(f"  {TAGS[status]} {text}")


def main(argv):
    parser = guarding.build_parser(prog="fourgate doctor", usage=USAGE, description=DESCRIPTION)
    own, target = guarding.split_argv(argv)
    args = parser.parse_args(own)
    if target is not None and not target:
        parser.error("no server command after '--'")

    report = Report()
    report.line(f"fourgate doctor {__version__}")
    report.line(f"  contracts: {os.path.abspath(args.contracts)}")
    report.line(f"  server label: {args.server}")
    report.line(f"  mode: {args.mode}")
    report.line(f"  target: {os.path.basename(target[0])} (+{len(target) - 1} args)" if target else "  target: none")

    report.section("Contract")
    try:
        contracts = outcome.load_strict(args.contracts)
    except ValueError as exc:
        report.add("FAIL", f"contract error: {exc}")
        contracts = None
    started = False
    if contracts is None:
        for title in LATER_SECTIONS:
            report.section(title)
            report.add("SKIP", "contract is invalid")
    else:
        tools = contracts["tools"]
        report.add("OK", f"contracts valid; protected tools: {', '.join(sorted(tools))}")
        configs = _check_verifiers(report, contracts)
        _check_credentials(report, tools, configs)
        started = _check_server(report, contracts, target)
        _check_mode_and_log(report, args)
        _check_write_safety(report, configs)

    report.line()
    report.line("Fourgate sent no tools/call, ran no verifier, made no network request and wrote no file.")
    if started:
        report.line("The server was started only for initialize and tools/list, then stopped. Anything the server "
                    "does on its own at start-up is outside Fourgate's control.")
    else:
        report.line("The server was not started.")
    if report.counts["FAIL"]:
        report.line(f"Verdict: NOT READY: {report.counts['FAIL']} problem(s)")
        return 1
    report.line(f"Verdict: READY FOR SHADOW ({report.counts['WARN']} warning(s))")
    return 0


def verify_http_config_arg(command):
    """The config argument of a bundled `-m fourgate.verify_http <config>` command, else None."""
    for index in range(len(command) - 1):
        if command[index] == "-m" and command[index + 1] == "fourgate.verify_http":
            return command[index + 2] if len(command) == index + 3 else None
    return None


def invokes_verify_http(command):
    """True if the command runs `-m fourgate.verify_http`, well-formed or not."""
    return any(command[i] == "-m" and command[i + 1] == "fourgate.verify_http" for i in range(len(command) - 1))


def _verifier_cwd(contracts, verifier):
    # Same resolution as outcome.evaluate: cwd relative to the contract file, else inherited.
    cwd = verifier.get("cwd")
    if cwd is None:
        return os.getcwd()
    return os.path.abspath(os.path.join(contracts["_contract_dir"], cwd))


def _check_verifiers(report, contracts):
    """Static verifier checks. Returns {tool: validated verify_http config}."""
    configs = {}
    for tool in sorted(contracts["tools"]):
        contract = contracts["tools"][tool]
        verifier = contract["verifier"]
        cwd = _verifier_cwd(contracts, verifier)
        report.section(f"Verifier: {tool}")
        config_arg = verify_http_config_arg(verifier["command"])
        if config_arg is None:
            if invokes_verify_http(verifier["command"]):
                report.add("FAIL", VERIFY_HTTP_USAGE)
            else:
                _check_custom(report, verifier, cwd)
            continue
        try:
            config = verify_http.load_config(os.path.join(cwd, config_arg), contract["extract"])
        except OSError as exc:
            report.add("FAIL", f"read-back config {config_arg} cannot be read: {exc.strerror or type(exc).__name__}")
            continue
        except (ValueError, RecursionError) as exc:
            report.add("FAIL", f"read-back config {config_arg} is invalid: {exc}")
            continue
        configs[tool] = config
        report.add("OK", f"bundled HTTP verifier; read-back config {config_arg} is valid (type {config['type']})")
        if config["type"] == "http" and urllib.parse.urlsplit(config["url_template"]).scheme == "http":
            report.add("OK", "HTTP to loopback only")
        else:
            report.add("OK", "HTTPS read-back to a static host")
        report.add("OK", "redirects are never followed (built in)")
        _check_budget(report, config, verifier["timeout_ms"])
        _check_failure_reasons(report, config, contract["allowed_failure_reasons"])
    return configs


def _check_custom(report, verifier, cwd):
    command = verifier["command"]
    executable = command[0]
    if executable == "{python}" and len(command) > 1 and not command[1].startswith("-"):
        script = os.path.basename(command[1])
        if os.path.exists(os.path.join(cwd, command[1])):
            report.add("OK", f"verifier script found: {script}")
        else:
            report.add("FAIL", f"verifier script not found: {script}")
    elif executable == "{python}":
        report.add("OK", "verifier executable: {python} (the interpreter running Fourgate)")
    elif shutil.which(executable) or os.path.exists(os.path.join(cwd, executable)):
        report.add("OK", f"verifier executable found: {os.path.basename(executable)}")
    else:
        report.add("FAIL", f"verifier executable not found: {os.path.basename(executable)}")
    report.add("WARN", "custom verifier: Fourgate cannot inspect what it reads or which credentials it uses")


def _check_budget(report, config, verifier_ms):
    budget = config.get("timeout_ms", 5000)
    attempts = config.get("attempts", 3)
    interval = config.get("interval_ms", 250)
    fits = True
    if budget > verifier_ms - STARTUP_HEADROOM_MS:
        fits = False
        report.add("WARN", f"read-back timeout_ms {budget} leaves under {STARTUP_HEADROOM_MS} ms of the "
                           f"{verifier_ms} ms verifier timeout for interpreter start-up")
    if (attempts - 1) * interval >= budget:
        fits = False
        report.add("WARN", f"retry spacing ({attempts - 1} x {interval} ms) uses the whole {budget} ms "
                           "read-back budget; later attempts cannot run")
    if fits:
        report.add("OK", f"read-back budget {budget} ms ({attempts} attempt(s), {interval} ms apart) "
                         f"fits the {verifier_ms} ms verifier timeout")


def _check_failure_reasons(report, config, allowed):
    if config["type"] == "http":
        detects_missing, setting = bool(config.get("missing_statuses")), "missing_statuses"
    else:
        detects_missing, setting = config.get("missing_is_fail", False), "missing_is_fail"
    missing_allowed = "record_missing" in allowed
    if missing_allowed and not detects_missing:
        report.add("WARN", f"record_missing is allowed but {setting} is not set: "
                           "a missing record can only ever be UNKNOWN")
    elif detects_missing and not missing_allowed:
        report.add("WARN", f"{setting} is set but record_missing is not in allowed_failure_reasons: "
                           "a confirmed missing record becomes UNKNOWN (verifier_malformed)")
    else:
        report.add("OK", "record_missing handling matches allowed_failure_reasons")


def _fold(name):
    # Windows env names are case-insensitive (same rule as wrap.py _server_env).
    return name.upper() if os.name == "nt" else name


def _check_credentials(report, tools, configs):
    report.section("Credentials")
    names = []
    for tool in sorted(tools):
        names += tools[tool]["verifier"].get("secret_env", [])
        names += readback.credential_envs(configs.get(tool))
    unique = sorted({_fold(n): n for n in names}.values())
    for name in unique:
        if os.environ.get(name):
            report.add("OK", f"{name} is set")
        else:
            report.add("FAIL", f"{name} is not set or empty: read-back would be UNKNOWN")
    if not unique:
        report.add("OK", "no credential variables are declared")
    for tool in sorted(configs):
        withheld = {_fold(n) for n in tools[tool]["verifier"].get("secret_env", [])}
        for name in readback.credential_envs(configs[tool]):
            if _fold(name) in withheld:
                report.add("OK", f"{tool}: {name} is withheld from the MCP server")
            else:
                report.add("WARN", f"{tool}: {name} is visible to the MCP server (add it to secret_env)")
    report.add("INFO", "Fourgate cannot verify the read credential is read-only or valid "
                     "(doctor makes no network requests)")
    report.add("INFO", "the verifier process inherits the full environment, including the server's own credentials")


def _check_server(report, contracts, target):
    """initialize + tools/list only. Returns True if the server process was started."""
    report.section("MCP server")
    if not target:
        report.add("SKIP", "pass the server command after -- to check the handshake and tool discovery")
        return False
    # Imported late: wrap.py adds wrap/ to sys.path for its own bare imports.
    from wrap import wrap as runtime
    env = runtime._server_env(outcome.secret_env_names(contracts))
    client, discovered = None, None
    try:
        client = scan.StdioClient(target, None, env)
        discovered = client.initialize(PROTOCOL)
    except Exception as exc:
        stage = "start" if client is None else "handshake"
        report.add("FAIL", f"server {stage} failed ({type(exc).__name__})")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    if discovered is None:
        report.add("SKIP", "tool discovery needs a successful handshake")
    else:
        report.add("OK", "handshake: initialize and tools/list answered")
        for tool in sorted(contracts["tools"]):
            if tool in discovered:
                report.add("OK", f"{tool} is advertised by the server")
            else:
                report.add("FAIL", f"{tool} is not advertised by the server (tools/list)")
    return client is not None


def _check_mode_and_log(report, args):
    report.section("Mode and log")
    if args.mode == "enforce":
        report.add("WARN", "enforce requested; run shadow until shadow results are clean")
    else:
        report.add("OK", "shadow: responses are never modified")
    if not args.log:
        report.add("WARN", "no --log: outcomes go to stderr, which MCP clients usually discard; "
                           "fourgate summary needs a log file")
        return
    path = os.path.abspath(args.log)
    parent = os.path.dirname(path)
    if os.path.isdir(path):
        report.add("FAIL", f"outcome log {path} is a directory (guard would refuse to start)")
    elif os.path.exists(path):
        if os.access(path, os.W_OK):
            report.add("OK", f"outcome log {path} exists and is writable (guard appends)")
        else:
            report.add("FAIL", f"outcome log {path} is not writable (guard would refuse to start)")
    elif os.path.isdir(parent) and os.access(parent, os.W_OK):
        report.add("OK", f"outcome log {path} can be created (directory is writable)")
    else:
        report.add("FAIL", f"outcome log directory {parent} is missing or not writable (guard would refuse to start)")


def _check_write_safety(report, configs):
    report.section("Write safety")
    report.add("OK", "Fourgate never re-sends a tools/call (no automatic write retries)")
    for tool in sorted(configs):
        report.add("OK", f"{tool}: read-back retries are GET only (attempts: {configs[tool].get('attempts', 3)})")
