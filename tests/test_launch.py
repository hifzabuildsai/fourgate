"""wrap.launch.resolve_command: bare server names resolve against the server's PATH on Windows only."""
import os

import pytest

from wrap import launch

windows_only = pytest.mark.skipif(os.name != "nt", reason="PATH resolution applies on Windows only")


@pytest.fixture
def fake_bin(tmp_path):
    (tmp_path / "python.exe").write_bytes(b"")
    return tmp_path


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def test_off_windows_the_command_is_unchanged(monkeypatch, fake_bin):
    monkeypatch.setattr(os, "name", "posix")
    command = ["python", "-m", "fourgate.demo.server"]
    env = {"PATH": str(fake_bin)}
    assert launch.resolve_command(command, env) is command
    assert launch.resolve_command(command, None) is command


@windows_only
def test_bare_name_resolves_first_on_the_env_path(fake_bin):
    env = {"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")}
    resolved = launch.resolve_command(["python", "-m", "fourgate.demo.server"], env)
    assert _same(resolved[0], fake_bin / "python.exe")
    assert resolved[1:] == ["-m", "fourgate.demo.server"]


@windows_only
def test_env_path_name_is_case_insensitive(fake_bin):
    resolved = launch.resolve_command(["python"], {"Path": str(fake_bin)})
    assert _same(resolved[0], fake_bin / "python.exe")


@windows_only
def test_no_env_uses_the_process_path(monkeypatch, fake_bin):
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))
    resolved = launch.resolve_command(["python", "server.py"], None)
    assert _same(resolved[0], fake_bin / "python.exe")
    assert resolved[1:] == ["server.py"]


@windows_only
@pytest.mark.parametrize("first", ["{bin}\\python.exe", "{bin}/python.exe", "sub\\python", "./python"])
def test_command_with_a_path_is_unchanged(fake_bin, first):
    command = [first.format(bin=fake_bin), "-V"]
    env = {"PATH": str(fake_bin)}
    assert launch.resolve_command(command, env) is command


@windows_only
def test_name_not_found_is_unchanged(fake_bin):
    command = ["fourgate-no-such-program-7c1e", "--flag"]
    assert launch.resolve_command(command, {"PATH": str(fake_bin)}) is command
