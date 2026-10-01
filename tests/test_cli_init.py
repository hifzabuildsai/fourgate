"""`fourgate init`: deterministic scaffolding of scan, runtime and read-back configs.

init never starts a server or contacts an endpoint; these tests run it
in-process and check its files with the same loaders scan, guard and doctor use.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fourgate import cli, scan, verify_http
from wrap import outcome
from test_readback_auth import _http

ROOT = Path(__file__).resolve().parent.parent
TOKEN_ENV = "FOURGATE_INIT_TEST_READ_TOKEN"
USER_ENV = "FOURGATE_INIT_TEST_READ_USER"
SENTINEL = "init-secret-sentinel-9e3a"
USER_SENTINEL = "init-user-sentinel-51d0"
ACCOUNT = "disposable-demo"
FILES = ("readback.json", "runtime.json", "scan.json")
SERVER = [sys.executable, "-m", "fourgate.demo.server"]
RUN_TIMEOUT = 60


def _argv(out, *extra, record=("--id-path", "result.structuredContent.issue_id"),
          url="https://api.example.test/issues/{record_id}", server=None, separator=True):
    argv = ["init", "--tool", "create_issue", "--test-account", ACCOUNT, *record,
            "--readback-url", url, "--dir", str(out), *extra]
    if separator:
        argv += ["--", *(SERVER if server is None else server)]
    return argv


def _base(*extra):
    return ("--expect", "title=title", "--arg", "title=FOURGATE-SCAN-TEST", *extra)


def _init(capsys, argv):
    rc = cli.main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _load(out):
    return {name: json.loads((out / name).read_text(encoding="utf-8")) for name in FILES}


def _assert_rejected(capsys, out, argv, needle=None):
    rc, stdout, stderr = _init(capsys, argv)
    assert rc == 2, stderr
    assert stdout == ""
    lines = stderr.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("fourgate init: error: ")
    if needle:
        assert needle in stderr
    assert not out.exists() or not any((out / name).exists() for name in FILES)
    return stderr


def _check_valid(out):
    docs = _load(out)
    extract = docs["runtime.json"]["tools"]["create_issue"]["extract"]
    verify_http.load_config(out / "readback.json", extract)
    outcome.load_strict(out / "runtime.json")
    scan.load_contract(out / "scan.json", ACCOUNT)
    return docs


# 1 -- happy path --------------------------------------------------------------

def test_happy_path_writes_three_valid_files(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "cfg"
    rc, stdout, stderr = _init(capsys, _argv(out, "--expect", "title=title", "--expect", "meta.label=labels.0",
                                             "--arg", "title=FOURGATE-SCAN-TEST",
                                             "--arg-json", 'labels=["init-test"]', "--token-env", TOKEN_ENV))
    assert rc == 0, stderr
    assert sorted(p.name for p in out.iterdir()) == sorted(FILES)
    docs = _check_valid(out)
    readback_config, runtime, scan_contract = docs["readback.json"], docs["runtime.json"], docs["scan.json"]
    tool = runtime["tools"]["create_issue"]
    assert tool["extract"] == {
        "record_id": {"source": "result", "path": "result.structuredContent.issue_id"},
        "title": {"source": "arguments", "path": "title"},
        "labels_0": {"source": "arguments", "path": "labels.0"},
    }
    assert tool["verifier"] == {"command": ["{python}", "-m", "fourgate.verify_http", "readback.json"],
                                "cwd": ".", "timeout_ms": 2000, "secret_env": [TOKEN_ENV]}
    assert tool["allowed_failure_reasons"] == ["field_mismatch"] and tool["recovery"] == "stop"
    assert readback_config == {"type": "http", "url_template": "https://api.example.test/issues/{record_id}",
                               "expected_fields": {"title": "title", "meta.label": "labels_0"},
                               "token_env": TOKEN_ENV, "attempts": 3, "interval_ms": 250, "timeout_ms": 1500}
    case = scan_contract["cases"][0]
    assert scan_contract["scan_version"] == 1 and scan_contract["write_tools"] == ["create_issue"]
    assert scan_contract["server"] == {"transport": "stdio", "command": SERVER, "test_account": ACCOUNT,
                                       "protocol_version": "2024-11-05", "call_timeout_ms": 10000}
    assert case["arguments"] == {"title": "FOURGATE-SCAN-TEST", "labels": ["init-test"]}
    assert case["outcome_contract"] == {"record_id_field": "record_id", "extract": tool["extract"]}
    assert case["readback"] == readback_config
    assert "scan performs real writes: use a disposable test account only." in stdout
    assert "--missing-status 404" in stdout


def test_next_steps_name_real_paths_and_label(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "cfg"
    rc, stdout, _ = _init(capsys, _argv(out, *_base("--server", "demo-label"), server=["python", "srv.py"]))
    assert rc == 0
    runtime_path, scan_path = os.path.join(str(out), "runtime.json"), os.path.join(str(out), "scan.json")
    for path in FILES:
        assert f"  {os.path.join(str(out), path)}" in stdout
    assert (f"fourgate doctor --contracts {runtime_path} --server demo-label --log outcomes.jsonl "
            "-- python srv.py") in stdout
    assert f"fourgate scan {scan_path} --confirm-test-account {ACCOUNT} --report-dir fourgate-report" in stdout
    assert (f"fourgate guard --contracts {runtime_path} --mode shadow --server demo-label --log outcomes.jsonl "
            "-- python srv.py") in stdout
    assert "fourgate summary outcomes.jsonl" in stdout


# 2 -- doctor accepts the output ----------------------------------------------

def test_doctor_reports_ready_with_zero_warnings(tmp_path, capsys):
    out = tmp_path / "cfg"
    rc, _, stderr = _init(capsys, _argv(out, *_base("--token-env", TOKEN_ENV)))
    assert rc == 0, stderr
    env = {**os.environ, TOKEN_ENV: SENTINEL}
    result = subprocess.run([sys.executable, "-m", "fourgate", "doctor", "--contracts", str(out / "runtime.json"),
                             "--log", str(tmp_path / "o.jsonl"), "--", *SERVER],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=RUN_TIMEOUT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verdict: READY FOR SHADOW (0 warning(s))" in result.stdout
    assert "[WARN]" not in result.stdout and "[FAIL]" not in result.stdout
    assert SENTINEL not in result.stdout + result.stderr


# 3 -- record id variants -------------------------------------------------------

@pytest.mark.parametrize("record, selector", [
    (("--id-regex", r"Created (ISSUE-\d+)"),
     {"source": "result", "path": "result.content.0.text", "parse": "regex", "pattern": r"Created (ISSUE-\d+)"}),
    (("--id-json-field", "issue.id"),
     {"source": "result", "path": "result.content.0.text", "parse": "embedded_json", "field": "issue.id"}),
])
def test_text_record_id_variants_are_valid(tmp_path, capsys, record, selector):
    out = tmp_path / "cfg"
    rc, _, stderr = _init(capsys, _argv(out, *_base(), record=record))
    assert rc == 0, stderr
    docs = _check_valid(out)
    assert docs["runtime.json"]["tools"]["create_issue"]["extract"]["record_id"] == selector
    assert docs["scan.json"]["cases"][0]["outcome_contract"]["extract"]["record_id"] == selector


@pytest.mark.parametrize("pattern", ["Created (ISSUE-", "Created ISSUE-\\d+"])
def test_invalid_regex_is_rejected(tmp_path, capsys, pattern):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *_base(), record=("--id-regex", pattern)))


def test_exactly_one_record_id_source(tmp_path, capsys):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *_base(), record=()))
    _assert_rejected(capsys, out, _argv(out, *_base("--id-json-field", "id"),
                                        record=("--id-path", "result.structuredContent.id")))


# 4 -- missing status --------------------------------------------------------

def test_missing_status_adds_record_missing(tmp_path, capsys):
    out = tmp_path / "with"
    rc, stdout, _ = _init(capsys, _argv(out, *_base("--missing-status", "404")))
    assert rc == 0
    docs = _check_valid(out)
    assert docs["runtime.json"]["tools"]["create_issue"]["allowed_failure_reasons"] == ["field_mismatch",
                                                                                         "record_missing"]
    assert docs["readback.json"]["missing_statuses"] == [404]
    assert "NOTE: a missing record" not in stdout

    out = tmp_path / "without"
    rc, stdout, _ = _init(capsys, _argv(out, *_base()))
    assert rc == 0
    docs = _check_valid(out)
    assert docs["runtime.json"]["tools"]["create_issue"]["allowed_failure_reasons"] == ["field_mismatch"]
    assert "missing_statuses" not in docs["readback.json"]
    assert ("NOTE: a missing record will be UNKNOWN, not FAIL, until you confirm the read credential can see "
            "records and add --missing-status 404.") in stdout


@pytest.mark.parametrize("code", ["401", "403", "500", "abc"])
def test_invalid_missing_status_is_rejected(tmp_path, capsys, code):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *_base("--missing-status", code)))


# 5 -- auth variants -----------------------------------------------------------

def test_header_auth(tmp_path, capsys):
    out = tmp_path / "cfg"
    rc, _, stderr = _init(capsys, _argv(out, *_base("--token-env", TOKEN_ENV, "--auth", "header",
                                                    "--auth-header", "X-Api-Key")))
    assert rc == 0, stderr
    docs = _check_valid(out)
    assert docs["readback.json"]["auth"] == {"scheme": "header", "header": "X-Api-Key"}
    assert docs["runtime.json"]["tools"]["create_issue"]["verifier"]["secret_env"] == [TOKEN_ENV]


def test_basic_auth_withholds_both_names(tmp_path, capsys):
    out = tmp_path / "cfg"
    rc, _, stderr = _init(capsys, _argv(out, *_base("--token-env", TOKEN_ENV, "--auth", "basic",
                                                    "--username-env", USER_ENV)))
    assert rc == 0, stderr
    docs = _check_valid(out)
    assert docs["readback.json"]["auth"] == {"scheme": "basic", "username_env": USER_ENV}
    assert docs["runtime.json"]["tools"]["create_issue"]["verifier"]["secret_env"] == [TOKEN_ENV, USER_ENV]


def test_explicit_bearer_auth(tmp_path, capsys):
    out = tmp_path / "cfg"
    rc, _, _ = _init(capsys, _argv(out, *_base("--token-env", TOKEN_ENV, "--auth", "bearer")))
    assert rc == 0
    assert _check_valid(out)["readback.json"]["auth"] == {"scheme": "bearer"}


@pytest.mark.parametrize("extra", [
    ("--token-env", TOKEN_ENV, "--auth", "header"),
    ("--token-env", TOKEN_ENV, "--auth", "basic"),
    ("--token-env", TOKEN_ENV, "--auth-header", "X-Api-Key"),
    ("--token-env", TOKEN_ENV, "--username-env", USER_ENV),
    ("--auth", "bearer"),
    ("--token-env", "NOT-A-NAME"),
    ("--token-env", TOKEN_ENV, "--auth", "header", "--auth-header", "Host"),
    ("--token-env", TOKEN_ENV, "--auth", "basic", "--username-env", TOKEN_ENV),
])
def test_incomplete_or_invalid_auth_is_rejected(tmp_path, capsys, extra):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *_base(*extra)))


# 6 -- rejections ----------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://api.example.test/issues/{record_id}",
    "https://{record_id}.example.test/issues",
    "https://api.example.test/issues/latest",
    "https://api.example.test/issues/{record_id}/{unknown}",
])
def test_bad_readback_url_is_rejected(tmp_path, capsys, url):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *_base(), url=url))


def test_loopback_http_is_allowed(tmp_path, capsys):
    out = tmp_path / "cfg"
    rc, _, stderr = _init(capsys, _argv(out, *_base(), url="http://127.0.0.1:8080/issues/{record_id}"))
    assert rc == 0, stderr


@pytest.mark.parametrize("extra, needle", [
    (("--expect", "title=subject", "--arg", "title=x"), "'subject'"),
    (("--expect", "a=meta.x", "--arg-json", 'meta={"y": 1}'), "not in the scan arguments"),
    (("--expect", "a=a-b", "--expect", "b=a_b", "--arg", "a-b=1", "--arg", "a_b=2"), "already used"),
    (("--expect", "a=record_id", "--arg", "record_id=1"), "reserved"),
    (("--expect", "title=title", "--expect", "title=body", "--arg", "title=1", "--arg", "body=2"),
     "more than once"),
    (("--expect", "title=title", "--arg", "title=1", "--arg", "title=2"), "more than once"),
    (("--expect", "title=title", "--arg", "title=1", "--arg-json", "n={bad"), "not valid JSON"),
    (("--expect", "title", "--arg", "title=1"), "RESPONSE_PATH=ARG_NAME"),
    (("--expect", "title=title", "--arg", "=1"), "NAME=VALUE"),
    (("--arg", "title=1"), "--expect"),
])
def test_bad_expect_or_args_are_rejected(tmp_path, capsys, extra, needle):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *extra), needle)


@pytest.mark.parametrize("path", ["id", "result.", "structuredContent.id"])
def test_id_path_must_point_into_result(tmp_path, capsys, path):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *_base(), record=("--id-path", path)), "--id-path")


def test_server_command_is_required(tmp_path, capsys):
    out = tmp_path / "cfg"
    _assert_rejected(capsys, out, _argv(out, *_base(), separator=False), "missing '--'")
    _assert_rejected(capsys, out, _argv(out, *_base(), server=[]), "no server command")


@pytest.mark.parametrize("drop", ["--tool", "--test-account"])
def test_tool_and_test_account_are_required(tmp_path, capsys, drop):
    out = tmp_path / "cfg"
    argv = _argv(out, *_base())
    index = argv.index(drop)
    del argv[index:index + 2]
    _assert_rejected(capsys, out, argv, drop)


def test_blank_test_account_is_rejected(tmp_path, capsys):
    out = tmp_path / "cfg"
    argv = _argv(out, *_base())
    argv[argv.index("--test-account") + 1] = "  "
    _assert_rejected(capsys, out, argv, "--test-account")


def test_abbreviated_flags_are_rejected(tmp_path, capsys):
    out = tmp_path / "cfg"
    argv = _argv(out, *_base())
    argv[argv.index("--test-account")] = "--test-acc"
    _assert_rejected(capsys, out, argv)


def test_existing_file_without_force_is_rejected(tmp_path, capsys):
    out = tmp_path / "cfg"
    out.mkdir()
    (out / "scan.json").write_text("keep me", encoding="utf-8")
    rc, stdout, stderr = _init(capsys, _argv(out, *_base()))
    assert rc == 2 and stdout == "" and "--force" in stderr
    assert (out / "scan.json").read_text(encoding="utf-8") == "keep me"
    assert not (out / "readback.json").exists() and not (out / "runtime.json").exists()


# 7 -- --force -------------------------------------------------------------------

def test_force_overwrites_only_the_three_files(tmp_path, capsys):
    out = tmp_path / "cfg"
    out.mkdir()
    for name in FILES:
        (out / name).write_text("old", encoding="utf-8")
    (out / "notes.txt").write_text("untouched", encoding="utf-8")
    (out / "outcomes.jsonl").write_text("{}\n", encoding="utf-8")
    rc, _, stderr = _init(capsys, _argv(out, *_base("--force")))
    assert rc == 0, stderr
    _check_valid(out)
    assert (out / "notes.txt").read_text(encoding="utf-8") == "untouched"
    assert (out / "outcomes.jsonl").read_text(encoding="utf-8") == "{}\n"
    assert sorted(p.name for p in out.iterdir()) == sorted([*FILES, "notes.txt", "outcomes.jsonl"])


# 8 -- secrets -------------------------------------------------------------------

def test_env_values_never_reach_files_or_output(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, SENTINEL)
    monkeypatch.setenv(USER_ENV, USER_SENTINEL)
    out = tmp_path / "cfg"
    rc, stdout, stderr = _init(capsys, _argv(out, *_base("--token-env", TOKEN_ENV, "--auth", "basic",
                                                         "--username-env", USER_ENV)))
    assert rc == 0, stderr
    for name in FILES:
        text = (out / name).read_text(encoding="utf-8")
        assert SENTINEL not in text and USER_SENTINEL not in text
    assert SENTINEL not in stdout + stderr and USER_SENTINEL not in stdout + stderr
    assert "is not set" not in stdout


def test_unset_credential_gets_a_note(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    out = tmp_path / "cfg"
    rc, stdout, _ = _init(capsys, _argv(out, *_base("--token-env", TOKEN_ENV)))
    assert rc == 0
    assert f"NOTE: {TOKEN_ENV} is not set in this shell" in stdout


# 9 -- relative server path ----------------------------------------------------

def test_relative_server_path_is_pinned_in_scan_only(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "server.py").write_text("", encoding="utf-8")
    out = tmp_path / "cfg"
    rc, stdout, stderr = _init(capsys, _argv(out, *_base(), server=["python", "server.py", "--flag"]))
    assert rc == 0, stderr
    absolute = str(tmp_path / "server.py")
    assert _load(out)["scan.json"]["server"]["command"] == ["python", absolute, "--flag"]
    assert f"scan.json: server command argument server.py -> {absolute}" in stdout
    guard_line = next(line for line in stdout.splitlines() if "fourgate guard" in line)
    doctor_line = next(line for line in stdout.splitlines() if "fourgate doctor" in line)
    assert guard_line.endswith("-- python server.py --flag")
    assert doctor_line.endswith("-- python server.py --flag")


# 10 -- ASCII output -------------------------------------------------------------

def test_output_is_ascii(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "srv\u00e9.py").write_text("", encoding="utf-8")
    out = tmp_path / "cfg\u00e9"
    rc, stdout, stderr = _init(capsys, _argv(out, *_base(), server=["python", "srv\u00e9.py"]))
    assert rc == 0, stderr
    stdout.encode("ascii")
    stderr.encode("ascii")
    rc, stdout, stderr = _init(capsys, _argv(out, *_base("--test-acc\u00e9")))
    assert rc == 2
    stderr.encode("ascii")


# 11 -- end to end ---------------------------------------------------------------

@pytest.mark.parametrize("title, status", [("FOURGATE-SCAN-TEST", "PASS"), ("SOMETHING-ELSE", "FAIL")])
def test_generated_scan_runs_end_to_end(tmp_path, capsys, title, status):
    out = tmp_path / "cfg"
    with _http(title=title) as (port, seen):
        rc, _, stderr = _init(capsys, _argv(out, *_base("--token-env", TOKEN_ENV, "--missing-status", "404"),
                                            url=f"http://127.0.0.1:{port}/issues/{{record_id}}",
                                            server=[sys.executable, str(ROOT / "fourgate" / "demo" / "server.py")]))
        assert rc == 0, stderr
        env = {**os.environ, TOKEN_ENV: SENTINEL, "FOURGATE_DEMO_MODE": "broken",
               "FOURGATE_DEMO_STORE": str(tmp_path / "store.json")}
        result = subprocess.run([sys.executable, "-m", "fourgate", "scan", str(out / "scan.json"),
                                 "--confirm-test-account", ACCOUNT], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=RUN_TIMEOUT)
    assert result.returncode == (0 if status == "PASS" else 1), result.stderr
    rows = json.loads(result.stdout)["cases"]
    assert [(row["tool"], row["status"]) for row in rows] == [("create_issue", status)]
    assert seen and seen[0]["authorization"] == f"Bearer {SENTINEL}"
