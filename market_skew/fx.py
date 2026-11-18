"""Daily USD/ZAR from Frankfurter (ECB reference rate), kept in data/fx.json.
The page only reads (`cached`); the scan and CLI commands call `refresh`."""
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

from . import cache
from .cache import DATA

URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=ZAR"
TIMEOUT_SECONDS = 8


def parse(payload: dict) -> float:
    rate = (payload.get("rates") or {}).get("ZAR")
    if not isinstance(rate, (int, float)) or rate <= 0:
        raise ValueError("No ZAR rate in the answer.")
    return float(rate)


def fetch() -> float:
    request = urllib.request.Request(URL, headers={"User-Agent": "market-skew"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return parse(json.load(response))


def cached(folder: Path = DATA) -> dict | None:
    """The last good rate as {"rate", "date"}, however old. Never touches the network."""
    saved = cache.read(folder / "fx.json")
    return {"rate": saved["rate"], "date": saved.get("date")} if saved.get("rate") else None


def refresh(folder: Path = DATA, today: str | None = None, fetcher=fetch, now: float | None = None) -> float | None:
    """Today's rate: kept if already fetched today, else fetched. A failure keeps the last good rate and
    holds off retrying for a quarter of an hour."""
    today = today or dt.date.today().isoformat()
    path = folder / "fx.json"
    saved = cache.read(path)
    if saved.get("date") == today and saved.get("rate"):
        return saved["rate"]
    if cache.backing_off(saved.get("failed_at"), now):
        return saved.get("rate")
    try:
        rate = fetcher()
    except Exception:
        cache.write(path, {**saved, "failed_at": now if now is not None else time.time()})
        return saved.get("rate")
    cache.write(path, {"date": today, "rate": rate})
    return rate
