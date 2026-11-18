"""First-run setup of the personal config files, plus the optional config/local.env.

The repo ships `config/*.example.*` files. The real files (holdings, watchlist, excluded tickers) are yours, gitignored,
and created from the examples the first time the app or the CLI starts. Existing files are never touched."""
import os
import shutil
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"
SEEDED = ("holdings.json", "watchlist.txt", "excluded.txt")


def _example(name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    return f"{stem}.example.{ext}"


def seed(config: Path = CONFIG) -> list[str]:
    """Copy each missing real file from its example. Returns the names it created."""
    made = []
    for name in SEEDED:
        target, example = config / name, config / _example(name)
        if not target.exists() and example.exists():
            shutil.copyfile(example, target)
            made.append(name)
    return made


def load_local_env(path: Path | None = None) -> dict[str, str]:
    """Read KEY=VALUE lines from config/local.env into os.environ (values already in the environment win).
    Used to point the app at a predictor installed somewhere else. Returns what it set."""
    path = path or CONFIG / "local.env"
    applied = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return applied
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), os.path.expandvars(os.path.expanduser(value.strip().strip("\"'")))
        if key and key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


def startup() -> None:
    load_local_env()
    seed()
