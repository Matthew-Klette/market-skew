"""Rand prices for the JSE ETFs, kept per symbol in data/jse.json. Yahoo quotes JSE in cents, so divide by 100.
The page only reads (`cached`); the scan and CLI commands call `refresh`. Each name is fetched and retried on its own,
so one that fails never freezes the other, and the last good price (with its date) stays until a newer one arrives."""
import datetime as dt
import time
from pathlib import Path

from . import cache
from .cache import DATA

SYMBOLS = ("SYG500", "STXNDQ")
TIMEOUT_SECONDS = 10


def fetch(symbol: str) -> float:
    """Last close in cents."""
    import yfinance as yf
    closes = yf.Ticker(symbol).history(period="5d", timeout=TIMEOUT_SECONDS)["Close"].dropna()
    if closes.empty:
        raise ValueError(f"No price for {symbol}")
    return float(closes.iloc[-1])


def cached(folder: Path = DATA) -> dict:
    """{"SYG500": {"price": rand, "date": day}, ...} from the last good fetches; names never fetched are left out."""
    quotes = cache.read(folder / "jse.json").get("quotes") or {}
    return {s: q for s, q in quotes.items() if isinstance(q, dict) and q.get("price")}


def refresh(folder: Path = DATA, today: str | None = None, fetcher=fetch, now: float | None = None) -> dict:
    today = today or dt.date.today().isoformat()
    path = folder / "jse.json"
    saved = cache.read(path)
    quotes, failed = dict(cached(folder)), dict(saved.get("failed") or {})
    for symbol in SYMBOLS:
        if (quotes.get(symbol) or {}).get("date") == today or cache.backing_off(failed.get(symbol), now):
            continue
        try:
            quotes[symbol] = {"price": fetcher(symbol + ".JO") / 100, "date": today}
            failed.pop(symbol, None)
        except Exception:
            failed[symbol] = now if now is not None else time.time()
    cache.write(path, {"quotes": quotes, "failed": failed})
    return quotes
