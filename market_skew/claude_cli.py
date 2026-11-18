"""Where `claude` lives, for the two features that run `claude -p` (Ask about this page, Quietly breaking).
The app starts with a bare PATH, so Homebrew, /usr/local and ~/.local/bin are searched explicitly, and the same PATH goes to the child
(the claude launcher needs `node` from there). Order: MARKET_SKEW_CLAUDE, then which(), then the fixed paths."""
import os
import shutil
from pathlib import Path

ENV_OVERRIDE = "MARKET_SKEW_CLAUDE"
DEFAULT_FIXED_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")
FIXED_DIRS = DEFAULT_FIXED_DIRS  # plus ~/.local/bin, which depends on the home folder at call time
SYSTEM_PATH = "/usr/bin:/bin"
MESSAGE = "Install Claude Code to use this."


class NotFound(Exception):
    pass


def extra_dirs() -> list[str]:
    return [*FIXED_DIRS, str(Path.home() / ".local" / "bin")]


def find() -> str:
    """The claude executable, or NotFound (message: Install Claude Code to use this.)."""
    override = os.environ.get(ENV_OVERRIDE)
    if override and Path(override).is_file() and os.access(override, os.X_OK):
        return override
    found = shutil.which("claude", path=os.pathsep.join([*extra_dirs(), os.environ.get("PATH", "")]))
    if found:
        return found
    for folder in extra_dirs():
        candidate = Path(folder) / "claude"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise NotFound(MESSAGE)


def subprocess_env() -> dict:
    """The child's whole environment: no API key (so it can only use the Claude plan), but a PATH where claude and node are found."""
    import getpass
    import tempfile
    user = getpass.getuser()
    return {"HOME": str(Path.home()), "USER": user, "LOGNAME": user, "SHELL": "/bin/zsh",
            "PATH": os.pathsep.join([*extra_dirs(), SYSTEM_PATH]), "TMPDIR": tempfile.gettempdir()}
