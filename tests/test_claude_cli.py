import os
import subprocess
from pathlib import Path

import pytest

from market_skew import breaking, claude_cli
from market_skew.ui import chat


def fake_claude(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "claude"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("MARKET_SKEW_CLAUDE", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(claude_cli, "FIXED_DIRS", ("/nonexistent-a", "/nonexistent-b"))  # this Mac may really have one in Homebrew
    return tmp_path


def test_env_override_comes_first(home, monkeypatch):
    mine = fake_claude(home / "custom")
    fake_claude(home / ".local" / "bin")
    monkeypatch.setenv("MARKET_SKEW_CLAUDE", str(mine))
    assert claude_cli.find() == str(mine)


def test_a_broken_override_falls_through_to_the_next_place(home, monkeypatch):
    found = fake_claude(home / ".local" / "bin")
    monkeypatch.setenv("MARKET_SKEW_CLAUDE", str(home / "gone"))
    assert claude_cli.find() == str(found)


def test_which_searches_homebrew_usr_local_and_local_bin_even_when_path_is_bare(home, monkeypatch):
    fake_claude(home / "brew")
    monkeypatch.setattr(claude_cli, "extra_dirs", lambda: [str(home / "brew")])
    assert claude_cli.find() == str(home / "brew" / "claude")


def test_fixed_paths_are_the_last_resort_when_which_finds_nothing(home, monkeypatch):
    fake_claude(home / "fixed")
    monkeypatch.setattr(claude_cli, "FIXED_DIRS", (str(home / "fixed"),))
    monkeypatch.setattr(claude_cli.shutil, "which", lambda *a, **k: None)
    assert claude_cli.find() == str(home / "fixed" / "claude")


def test_the_real_directories_are_the_documented_ones(home, monkeypatch):
    assert claude_cli.DEFAULT_FIXED_DIRS == ("/opt/homebrew/bin", "/usr/local/bin")
    monkeypatch.setattr(claude_cli, "FIXED_DIRS", claude_cli.DEFAULT_FIXED_DIRS)
    assert claude_cli.extra_dirs() == ["/opt/homebrew/bin", "/usr/local/bin", str(home / ".local" / "bin")]
    assert claude_cli.subprocess_env()["PATH"].split(":")[:3] == claude_cli.extra_dirs()
    assert "/usr/bin" in claude_cli.subprocess_env()["PATH"].split(":")


def test_not_found_says_how_to_fix_it(home):
    with pytest.raises(claude_cli.NotFound, match="Install Claude Code to use this"):
        claude_cli.find()
    with pytest.raises(chat.ChatError, match="Install Claude Code to use this"):
        chat._claude()
    with pytest.raises(breaking.BreakingError, match="Install Claude Code to use this"):
        breaking._claude()


def test_chat_and_breaking_pass_the_search_path_to_the_subprocess(home, monkeypatch):
    monkeypatch.setattr(claude_cli, "FIXED_DIRS", claude_cli.DEFAULT_FIXED_DIRS)
    seen = []
    monkeypatch.setattr(chat, "_claude", lambda: "/x/claude")
    monkeypatch.setattr(breaking, "_claude", lambda: "/x/claude")

    def run(cmd, **kw):
        seen.append(kw["env"]["PATH"])
        return subprocess.CompletedProcess(cmd, 0, stdout='{"deductions":[],"what_breaks":"x"}', stderr="")
    chat.ask("hi", [], "page", run=run)
    breaking.ask({"symbol": "A", "name": "A", "sector": "s", "score": 50, "label": "WATCH", "metrics": {}, "pillars": {}, "depth": "Full"}, run=run)
    assert len(seen) == 2 and all(p.startswith("/opt/homebrew/bin:/usr/local/bin:") and p.endswith("/usr/bin:/bin") for p in seen)
