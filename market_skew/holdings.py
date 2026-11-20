"""What you own (config/holdings.json) and the tickers you can't buy (config/excluded.txt)."""
import json
import math
import os
import re
import threading
from pathlib import Path

from . import atomic

ROOT = Path(__file__).resolve().parent.parent
HOLDINGS = ROOT / "config" / "holdings.json"
EXCLUDED = ROOT / "config" / "excluded.txt"
TICKER = re.compile(r"[A-Z][A-Z0-9-]{0,6}")
NO_READING = "No options reading yet; added from the next scan."
MAX_ROWS = 50
MAX_UNITS, MAX_PRICE = 1e9, 1e7
SAVE_LOCK = threading.Lock()
JSE_NOTE = "JSE fund: price only"


def _num(value, high: float, positive: bool = False) -> float | None:
    """A finite number in [0, high) (> 0 when `positive`), or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    ok = math.isfinite(number) and 0 <= number < high and not (positive and number == 0)
    return number if ok else None


def load(path: Path = HOLDINGS) -> list[dict]:
    """Valid holdings only: {symbol, account, new_money} plus units, avg_price and last_buy when set and sane.
    A missing or broken file means no holdings."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        symbol = str(item.get("symbol", "")).upper() if isinstance(item, dict) else ""
        if TICKER.fullmatch(symbol):
            extra = {key: n for key, high, pos in (("units", MAX_UNITS, False), ("avg_price", MAX_PRICE, True), ("last_buy", MAX_PRICE, True))
                     if isinstance(item.get(key), (int, float)) and (n := _num(item[key], high, pos)) is not None}
            out.append({"symbol": symbol, "account": "tfsa" if item.get("account") == "tfsa" else "usd",
                        "new_money": item.get("new_money") is not False, **extra})
    return out


def buy_price(h: dict) -> float | None:
    """The price the add-on rule measures from: the last buy, else the average buy price."""
    return h.get("last_buy") or h.get("avg_price")


def validate(rows) -> list[dict]:
    """Check a whole holdings list from the editor and return it cleaned. Blank units or prices are allowed (left out).
    Raises ValueError with a plain message on the first bad row."""
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError(f"Up to {MAX_ROWS} holdings.")
    out = []
    for i, item in enumerate(rows, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Row {i} is not a holding.")
        symbol = str(item.get("symbol", "")).strip().upper()
        if not TICKER.fullmatch(symbol):
            raise ValueError(f"Row {i}: that is not a ticker.")
        if item.get("account") not in ("usd", "tfsa"):
            raise ValueError(f"Row {i}: pick USD or TFSA.")
        row = {"symbol": symbol, "account": item["account"], "new_money": item.get("new_money") is not False}
        for key, label, high, pos in (("units", "units", MAX_UNITS, False), ("avg_price", "average buy price", MAX_PRICE, False),
                                      ("last_buy", "last buy price", MAX_PRICE, False)):
            raw = item.get(key)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                continue
            number = _num(raw.strip() if isinstance(raw, str) else raw, high)
            if number is None:
                raise ValueError(f"Row {i}: {label} must be a number from 0 up to {high:,.0f}.")
            if number > 0 or key == "units":
                row[key] = number
        out.append(row)
    return out


def save(rows, path: Path = HOLDINGS) -> list[dict]:
    """Validate, then write atomically under a lock (a temp file renamed into place). Returns what was saved."""
    clean = validate(rows)
    with SAVE_LOCK:
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(clean, indent=1))
        os.replace(temp, path)
    return clean


def excluded(path: Path = EXCLUDED) -> set[str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return set()
    return {s for s in (line.strip().upper() for line in lines) if TICKER.fullmatch(s)}


def exclude(symbol: str, path: Path = EXCLUDED) -> set[str]:
    """Add a ticker (validated) and return the new set."""
    symbol = symbol.strip().upper()
    if not TICKER.fullmatch(symbol):
        raise ValueError("Not a ticker.")
    with SAVE_LOCK:
        current = excluded(path)
        if symbol not in current:
            try:
                text = path.read_text()
            except OSError:
                text = ""
            atomic.write_text(path, text + ("" if not text or text.endswith("\n") else "\n") + symbol + "\n")
    return current | {symbol}


def include(symbol: str, path: Path = EXCLUDED) -> set[str]:
    """Undo exclude: drop the ticker's line, keep every other line (comments too), return the new set."""
    symbol = symbol.strip().upper()
    if not TICKER.fullmatch(symbol):
        raise ValueError("Not a ticker.")
    with SAVE_LOCK:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return set()
        kept = [line for line in lines if line.strip().upper() != symbol]
        if len(kept) != len(lines):
            atomic.write_text(path, "".join(f"{line}\n" for line in kept))
    return excluded(path)


def rows(holdings: list[dict], lights: list[dict], quotes: dict) -> list[dict]:
    """One display row per holding. `lights` are picks.holdings_check rows for the US names; JSE (tfsa) holdings
    show their rand price only."""
    by_symbol = {x["symbol"]: x for x in lights if x.get("price") is not None}
    out = []
    for h in holdings:
        s = h["symbol"]
        if h["account"] == "tfsa":
            price = (quotes.get(s) or {}).get("price")
            out.append({"symbol": s, "name": s, "light": "none", "label": "No signal", "why": JSE_NOTE,
                        "price": price, "currency": "ZAR", "ret_1m": None})
        elif s in by_symbol:
            out.append({**by_symbol[s], "currency": "USD"})
        else:
            out.append({"symbol": s, "name": s, "light": "none", "label": "No reading", "why": NO_READING,
                        "price": None, "currency": "USD", "ret_1m": None})
    return out
