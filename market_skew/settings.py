"""The one personal setting the data code needs: the contact address SEC asks every automated downloader to send.
It lives only in config/prefs.json (gitignored) and goes only to sec.gov."""
import json
import re
from pathlib import Path

PREFS = Path(__file__).resolve().parent.parent / "config" / "prefs.json"
EMAIL = re.compile(r"^[^@\s<>\"',;]{1,64}@[^@\s<>\"',;]{1,185}\.[A-Za-z]{2,}$")
MAX_EMAIL = 254
MISSING = ("Add your email under Settings on the How it works tab so the SEC lets the app download company filings "
           "(sec.gov requires a contact; it's sent only to sec.gov).")


def valid_email(value) -> bool:
    return isinstance(value, str) and len(value) <= MAX_EMAIL and bool(EMAIL.fullmatch(value))


def sec_contact(path: Path | None = None) -> str | None:
    try:
        value = json.loads((path or PREFS).read_text()).get("sec_contact")
    except (OSError, ValueError, AttributeError):
        return None
    return value if valid_email(value) else None
