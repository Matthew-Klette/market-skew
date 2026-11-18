"""The Windows build: every platform answer flips on Windows and stays the same on a Mac. Runs on both."""
import os
import sys
from pathlib import Path

import pytest

from market_skew import claude_cli, system, winapp


@pytest.fixture
def windows(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "IS_WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "me")
    return tmp_path


@pytest.mark.skipif(sys.platform == "win32", reason="checks the Mac answers")
def test_a_mac_gets_the_answers_it_always_had():
    assert system.DEVICE == "Mac" and not system.IS_WINDOWS
    assert system.venv_python(Path("/p/.venv")) == Path("/p/.venv/bin/python")
    assert system.app_support() == Path.home() / "Library" / "Application Support" / "MarketSkew"
    assert system.python_flags() == []
    assert "preexec_fn" in system.low_priority() and system.hidden_window() == {}
    assert claude_cli.extra_dirs()[:2] == ["/opt/homebrew/bin", "/usr/local/bin"]


def test_windows_paths(windows):
    assert system.venv_python(Path("C:/p/.venv")) == Path("C:/p/.venv/Scripts/python.exe")
    assert system.venv_python(Path("C:/p/.venv"), windowed=True).name == "pythonw.exe"
    assert system.app_support() == windows / "Local" / "MarketSkew"
    assert system.python_flags() == ["-X", "utf8"]


def test_windows_starts_the_scan_low_priority_without_preexec(windows):
    kwargs = system.low_priority()
    assert "preexec_fn" not in kwargs  # Popen refuses preexec_fn on Windows
    assert kwargs["creationflags"] & 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS


def test_pid_alive_for_this_process_and_a_finished_one():
    import subprocess
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    assert system.pid_alive(os.getpid())
    assert not system.pid_alive(done.pid)


def test_claude_on_windows_prefers_the_native_exe(windows, monkeypatch):
    monkeypatch.delenv("MARKET_SKEW_CLAUDE", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(claude_cli.shutil, "which", lambda *a, **k: None)
    npm = windows / "Roaming" / "npm"
    npm.mkdir(parents=True)
    (npm / "claude.cmd").write_text("@echo off\n")
    (npm / "claude.cmd").chmod(0o755)  # Windows counts every file as runnable; a Mac needs the bit
    assert claude_cli.find() == str(npm / "claude.cmd")
    native = windows / "me" / ".local" / "bin"
    native.mkdir(parents=True)
    (native / "claude.exe").write_bytes(b"MZ")
    (native / "claude.exe").chmod(0o755)
    assert claude_cli.find() == str(native / "claude.exe")


def test_claude_env_on_windows_keeps_what_windows_programs_need(windows, monkeypatch):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-pass")
    env = claude_cli.subprocess_env()
    assert env["SYSTEMROOT"] == r"C:\Windows"
    assert "ANTHROPIC_API_KEY" not in env
    assert str(windows / "Roaming" / "npm") in env["PATH"].split(os.pathsep)


def test_browser_prefers_edge_then_chrome(tmp_path):
    env = {"PROGRAMFILES(X86)": str(tmp_path / "x86"), "PROGRAMFILES": str(tmp_path / "pf"), "LOCALAPPDATA": str(tmp_path / "local")}
    chrome = tmp_path / "pf" / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"")
    assert winapp.find_browser(env) == str(chrome)
    edge = tmp_path / "x86" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b"")
    assert winapp.find_browser(env) == str(edge)


def test_window_is_app_mode_with_its_own_profile(tmp_path):
    command = winapp.window_command("msedge.exe", "http://127.0.0.1:5000/", tmp_path / "window")
    assert command[0] == "msedge.exe"
    assert "--app=http://127.0.0.1:5000/" in command
    assert f"--user-data-dir={tmp_path / 'window'}" in command


def test_one_window_at_a_time(tmp_path, monkeypatch):
    monkeypatch.setattr(winapp, "LOCK", tmp_path / "app.lock")
    assert winapp.take_lock()
    assert not winapp.take_lock()  # this process holds it
    import subprocess
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    (tmp_path / "app.lock").write_text(str(gone.pid))  # a window that crashed
    assert winapp.take_lock()


def test_app_command_explains_itself_on_a_mac(monkeypatch, capsys):
    monkeypatch.setattr(system, "IS_WINDOWS", False)
    assert winapp.run() == 2
    assert "Market Skew.app" in capsys.readouterr().out


def test_window_waits_while_edge_still_holds_its_profile(tmp_path, monkeypatch):
    calls, lock = [], tmp_path / "lockfile"
    lock.write_text("")
    monkeypatch.setattr(winapp.subprocess, "run", lambda command: calls.append(command))
    states = iter([True, True, False])
    monkeypatch.setattr(winapp, "window_open", lambda profile: next(states))
    slept = []
    winapp.wait_for_window("msedge.exe", "http://127.0.0.1:1/", tmp_path, sleep=slept.append)
    assert len(calls) == 1 and slept == [2, 2]


def test_a_free_profile_lock_means_the_window_is_closed(tmp_path):
    assert not winapp.window_open(tmp_path)
    (tmp_path / "lockfile").write_text("")
    assert not winapp.window_open(tmp_path)  # removable, so nothing holds it
    assert not (tmp_path / "lockfile").exists()


def test_windows_stops_the_whole_scan_tree(windows, monkeypatch):
    seen = []

    class Child:
        pid = 4242

        def wait(self, timeout=None):
            seen.append("wait")

        def kill(self):
            seen.append("kill")

    monkeypatch.setattr(system, "hidden_window", lambda: {})
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: seen.append(command))
    system.stop_process(Child())
    assert seen[0] == ["taskkill", "/PID", "4242", "/T", "/F"] and seen[1] == "wait"


def test_children_get_console_python_on_windows(windows, tmp_path):
    (tmp_path / "python.exe").write_bytes(b"")
    assert system.console_python(str(tmp_path / "pythonw.exe")) == str(tmp_path / "python.exe")
    assert system.console_python("/usr/bin/python3") == "/usr/bin/python3"
