"""Small on-disk caches in data/ for the things the page needs but must never wait for (rand rate, JSE prices, VOO closes).
Refreshing happens inside the scan and the CLI commands; the page only reads. A failed fetch leaves a marker so nothing is retried
for RETRY_SECONDS, and the last good value stays in place."""
import json
import os
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
RETRY_SECONDS = 15 * 60


def read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write(path: Path, value: dict) -> None:
    """Atomic: a reader never sees half a file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(value))
        os.replace(temp, path)
    except OSError:
        pass


def backing_off(failed_at: float | None, now: float | None = None) -> bool:
    """True while a recent failure says to leave the network alone."""
    return failed_at is not None and ((now if now is not None else time.time()) - failed_at) < RETRY_SECONDS
