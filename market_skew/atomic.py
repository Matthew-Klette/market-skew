"""Write a small text file so a crash or a second writer never leaves it half-written: temp file in the same folder, then os.replace."""
import os
import tempfile
from pathlib import Path


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
