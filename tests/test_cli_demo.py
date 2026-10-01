"""`fourgate demo`: the five scenes run through the real guard, self-check, and summary page."""
import copy
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fourgate import cli, summary
from fourgate.demo import runner
from wrap import outcome

ROOT = Path(__file__).resolve().parent.parent
RUN_TIMEOUT = 120
EXPECTED = [
    ("enforce", "fail", "record_missing"),
    ("enforce", "pass", "postcondition_satisfied"),
    ("shadow", "fail", "record_missing"),
    ("enforce", "unknown", "verifier_error"),
]


def _demo(out, env=None, cwd=ROOT, command=None):
    command = command or [sys.executable, "-m", "fourgate", "demo"]
    return subprocess.run([*command, "--out", str(out)], stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=RUN_TIMEOUT, env=env, cwd=cwd)


def _tuples(out):
    records, skipped = summary.load([out / runner.LOG_NAME])
    assert skipped == 0
    return [(r["mode"], r["status"], r["reason_code"]) for r in records], records


@pytest.fixture(scope="module")
def first_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo") / "out"
    return out, _demo(out)


def test_demo_runs_all_scenes_and_writes_summary(first_run):
    out, result = first_run
    assert result.returncode == 0, result.stdout.decode("ascii", "replace")
    tuples, records = _tuples(out)
    assert tuples == EXPECTED
    page = (out / runner.PAGE_NAME).read_text(encoding="utf-8")
    for label in ("PASS", "FAIL", "UNKNOWN"):
        assert label in page
    assert summary.summarize(records)["totals"] == {"pass": 1, "fail": 2, "unknown": 1}
    stdout = result.stdout.decode("ascii")
    assert "PASS 1 / FAIL 2 / UNKNOWN 1" in stdout
    assert (out / runner.PAGE_NAME).resolve().as_uri() in stdout
    assert sorted(p.name for p in out.iterdir()) == sorted([runner.LOG_NAME, runner.PAGE_NAME])


def test_output_is_ascii_with_header_and_honesty_line(first_run):
    _, result = first_run
    stdout = result.stdout.decode("ascii")  # raises on any non-ASCII byte
    assert stdout.startswith(runner.HEADER)
    assert runner.HONESTY in stdout
    for scene in runner.SCENES:
        assert scene["takeaway"] in stdout
    assert "[FOURGATE] outcome_failed (reason: record_missing" in stdout
    assert "Created ISSUE-001" in stdout
    # Child processes never write to the narration (guard banner, server stderr).
    assert "fourgate guard 0." not in stdout and "withheld from server env" not in stdout
    assert "SELF-CHECK" not in stdout


def test_rerun_truncates_log_and_leaves_other_files_alone(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    unrelated = out / "notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")
    stat = unrelated.stat()
    for _ in range(2):
        result = _demo(out)
        assert result.returncode == 0, result.stdout.decode("ascii", "replace")
        assert _tuples(out)[0] == EXPECTED
    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert unrelated.stat().st_mtime_ns == stat.st_mtime_ns
    assert sorted(p.name for p in out.iterdir()) == sorted(["notes.txt", runner.LOG_NAME, runner.PAGE_NAME])


def test_minimal_environment(tmp_path):
    env = {"PATH": os.environ.get("PATH", "")}
    if os.name == "nt":
        for name in ("SYSTEMROOT", "TEMP", "TMP"):
            if name in os.environ:
                env[name] = os.environ[name]
    result = _demo(tmp_path / "out", env=env)
    assert result.returncode == 0, result.stdout.decode("ascii", "replace")
    assert _tuples(tmp_path / "out")[0] == EXPECTED


def _patched(monkeypatch, scene_id, edit):
    scenes = copy.deepcopy(runner.SCENES)
    edit(next(s for s in scenes if s["id"] == scene_id))
    monkeypatch.setattr(runner, "SCENES", scenes)


@pytest.mark.parametrize("scene_id, edit, detail", [
    ("S3", lambda s: s.update(verifier="crash"),
     "outcome log: expected PASS postcondition_satisfied (enforce), got UNKNOWN verifier_error (enforce)"),
    ("S1", lambda s: s["expect"].update(issues=1), "system of record: expected 1 issue(s), found 0"),
    ("S4", lambda s: s["expect"].update(verdict="record_missing"), "expected a [FOURGATE] outcome_failed"),
])
def test_self_check_fails_when_a_scene_differs(tmp_path, monkeypatch, capsys, scene_id, edit, detail):
    _patched(monkeypatch, scene_id, edit)
    rc = cli.main(["demo", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "SELF-CHECK FAILED" in out
    assert f"  {scene_id} (" in out and detail in out
    assert "Self-check: every scene behaved as narrated." not in out


def test_runtime_contract_is_strict_and_doctor_ready(tmp_path):
    path = runner.write_contract(tmp_path)
    loaded = outcome.load_strict(str(path))
    contract = loaded["tools"]["create_issue"]
    assert contract["verifier"] == {"command": ["{python}", "-m", "fourgate.demo.verifier"], "timeout_ms": 2000}
    assert contract["allowed_failure_reasons"] == ["record_missing", "field_mismatch"]
    assert contract["recovery"] == "stop"
    env = runner.child_env(tmp_path / "store.json", "broken", "normal")
    result = subprocess.run([sys.executable, "-m", "fourgate", "doctor", "--contracts", str(path),
                             "--server", runner.SERVER_LABEL, "--", *runner.server_command()],
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=RUN_TIMEOUT, env=env, cwd=tmp_path)
    stdout = result.stdout.decode("ascii")
    assert result.returncode == 0, stdout
    assert "[ OK ] create_issue is advertised by the server" in stdout


def test_relative_out_in_process(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["demo", "--out", "demo-output"])
    assert rc == 0, capsys.readouterr().out
    out = tmp_path / "demo-output"
    assert _tuples(out)[0] == EXPECTED
    assert (out / runner.PAGE_NAME).is_file()


def test_relative_out_subprocess(tmp_path):
    # The CI step: a relative --out from the caller's cwd; guard children run elsewhere.
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    result = subprocess.run([sys.executable, "-m", "fourgate", "demo", "--out", "demo-output"],
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=RUN_TIMEOUT, env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stdout.decode("ascii", "replace")
    out = tmp_path / "demo-output"
    assert _tuples(out)[0] == EXPECTED
    assert (out / runner.PAGE_NAME).is_file()


@pytest.mark.parametrize("pace", ["-1", "10.5", "abc"])
def test_pace_out_of_range_is_a_usage_error(tmp_path, pace):
    result = subprocess.run([sys.executable, "-m", "fourgate", "demo", "--out", str(tmp_path / "out"), "--pace", pace],
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=RUN_TIMEOUT, cwd=ROOT)
    assert result.returncode == 2
    assert not (tmp_path / "out").exists()


def test_installed_console_script_ships_the_demo(tmp_path):
    script = shutil.which("fourgate")
    if script is None:
        pytest.skip("fourgate console script is not installed")
    # cwd outside the repo: only the installed package can provide fourgate.demo.
    try:
        result = _demo(tmp_path / "out", cwd=tmp_path, command=[script, "demo"])
    except OSError as exc:
        # Windows Application Control / Smart App Control can block a freshly built launcher exe.
        if getattr(exc, "winerror", None) == 4551:
            pytest.skip(f"the OS blocked the fourgate launcher: {exc}")
        raise
    assert result.returncode == 0, result.stdout.decode("ascii", "replace") + result.stderr.decode("ascii", "replace")
    assert _tuples(tmp_path / "out")[0] == EXPECTED
