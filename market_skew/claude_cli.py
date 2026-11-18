"""Where `claude` lives, for the two features that run `claude -p` (Ask about this page, Quietly breaking).
The app starts with a bare PATH, so Homebrew, /usr/local and ~/.local/bin are searched explicitly, and the same PATH goes to the child
(the claude launcher needs `node` from there). Order: MARKET_SKEW_CLAUDE, then which(), then the fixed paths.
On Windows the places are the native installer's ~/.local/bin (claude.exe) and npm's %APPDATA%/npm (claude.cmd)."""
import os
import shutil
from pathlib import Path

from . import system

ENV_OVERRIDE = "MARKET_SKEW_CLAUDE"
DEFAULT_FIXED_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")
FIXED_DIRS = DEFAULT_FIXED_DIRS  # plus ~/.local/bin, which depends on the home folder at call time
SYSTEM_PATH = "/usr/bin:/bin"
MESSAGE = "Install Claude Code to use this."


class NotFound(Exception):
    pass


def extra_dirs() -> list[str]:
    if system.IS_WINDOWS:
        return _windows_dirs()
    return [*FIXED_DIRS, str(Path.home() / ".local" / "bin")]


def _windows_dirs() -> list[str]:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    programs = os.environ.get("PROGRAMFILES") or r"C:\Program Files"
    return [str(Path.home() / ".local" / "bin"), str(Path(appdata) / "npm"), str(Path(programs) / "nodejs")]


def _names() -> list[str]:
    """claude.exe first: a .cmd shim goes through cmd.exe, which mangles some arguments."""
    return ["claude.exe", "claude.cmd", "claude"] if system.IS_WINDOWS else ["claude"]


def find() -> str:
    """The claude executable, or NotFound (message: Install Claude Code to use this.)."""
    override = os.environ.get(ENV_OVERRIDE)
    if override and Path(override).is_file() and os.access(override, os.X_OK):
        return override
    search = os.pathsep.join([*extra_dirs(), os.environ.get("PATH", "")])
    for name in _names():
        found = shutil.which(name, path=search)
        if found:
            return found
    for folder in extra_dirs():
        for name in _names():
            candidate = Path(folder) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    raise NotFound(MESSAGE)


def subprocess_env() -> dict:
    """The child's whole environment: no API key (so it can only use the Claude plan), but a PATH where claude and node are found."""
    import getpass
    import tempfile
    if system.IS_WINDOWS:
        base = system.windows_base_env()
        system_dirs = [str(Path(base.get("SYSTEMROOT", r"C:\Windows")) / "System32"), base.get("SYSTEMROOT", r"C:\Windows")]
        return {**base, "HOME": str(Path.home()), "PATH": os.pathsep.join([*extra_dirs(), *system_dirs])}
    user = getpass.getuser()
    return {"HOME": str(Path.home()), "USER": user, "LOGNAME": user, "SHELL": "/bin/zsh",
            "PATH": os.pathsep.join([*extra_dirs(), SYSTEM_PATH]), "TMPDIR": tempfile.gettempdir()}
