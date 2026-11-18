"""Ten years of month-end prices for the user's funds, turned into monthly total returns in rand, kept in data/history.json.
Yahoo adjusted closes (dividends included) for SYG500.JO and STXNDQ.JO (cents, /100), VOO, SCHD, QQQ, VOOG, plus USD/ZAR,
so a dollar fund is measured the way the user feels it: in rand. SYG500 and STXNDQ are young; earlier months borrow VOO and
QQQ in rand and say so. The page only reads (`cached`); the scan (weekly) and `skew history` call `refresh`."""
import datetime as dt
import time
from pathlib import Path

from . import cache
from .cache import DATA

YAHOO = {"SYG500": "SYG500.JO", "STXNDQ": "STXNDQ.JO", "VOO": "VOO", "SCHD": "SCHD", "QQQ": "QQQ", "VOOG": "VOOG", "USDZAR": "ZAR=X"}
NAMES = tuple(YAHOO)
JSE = ("SYG500", "STXNDQ")
FUNDS = tuple(n for n in NAMES if n != "USDZAR")
PROXY = {"SYG500": "VOO", "STXNDQ": "QQQ"}
YEARS = 11  # a few months over ten, because the newest month is dropped (still open)
STALE_DAYS = 7
TIMEOUT_SECONDS = 20


def _month(day: str) -> str:
    return day[:7]


def _previous(month: str) -> str:
    year, num = int(month[:4]), int(month[5:7])
    return f"{year - 1}-12" if num == 1 else f"{year}-{num - 1:02d}"


def month_levels(closes, today: str) -> dict[str, float]:
    """A date-indexed pandas Series of monthly closes -> {"YYYY-MM": close}, without the month still open on `today`."""
    out = {}
    for stamp, value in closes.dropna().items():
        month = stamp.strftime("%Y-%m")
        if month < _month(today) and value > 0:
            out[month] = float(value)
    return out


def fetch(name: str, today: str | None = None) -> dict[str, float]:
    import yfinance as yf
    frame = yf.Ticker(YAHOO[name]).history(period=f"{YEARS}y", interval="1mo", auto_adjust=True, timeout=TIMEOUT_SECONDS)
    levels = month_levels(frame["Close"], today or dt.date.today().isoformat())
    if not levels:
        raise ValueError(f"No history for {name}")
    return {m: v / 100 for m, v in levels.items()} if name in JSE else levels


def cached(folder: Path = DATA) -> dict | None:
    """{"levels": {name: {month: level}}, "date"} from the last good fetches, however old; None before the first fetch."""
    saved = cache.read(folder / "history.json")
    levels = saved.get("levels")
    return {"levels": levels, "date": saved.get("date")} if isinstance(levels, dict) and levels else None


def _stale(day: str | None, today: str) -> bool:
    try:
        return (dt.date.fromisoformat(today) - dt.date.fromisoformat(day)).days >= STALE_DAYS
    except (TypeError, ValueError):
        return True


def refresh(folder: Path = DATA, today: str | None = None, fetcher=None, now: float | None = None, force: bool = False) -> dict:
    """Each name is fetched on its own, at most weekly (`force` ignores that). A failure keeps the last good levels and holds
    off retrying for a quarter of an hour. Returns the saved file's contents."""
    today = today or dt.date.today().isoformat()
    fetcher = fetcher or (lambda name: fetch(name, today))
    path = folder / "history.json"
    saved = cache.read(path)
    levels, dates, failed = dict(saved.get("levels") or {}), dict(saved.get("dates") or {}), dict(saved.get("failed") or {})
    for name in NAMES:
        if not force and (name in levels and not _stale(dates.get(name), today) or cache.backing_off(failed.get(name), now)):
            continue
        try:
            levels[name] = fetcher(name)
            dates[name] = today
            failed.pop(name, None)
        except Exception:
            failed[name] = now if now is not None else time.time()
    out = {"date": today, "levels": levels, "dates": dates, "failed": failed}
    cache.write(path, out)
    return out


def rand_returns(levels: dict) -> dict[str, dict[str, float]]:
    """Monthly return per fund in rand: month over the month just before it, only when both months exist."""
    rate = levels.get("USDZAR") or {}
    out = {}
    for name in FUNDS:
        series = levels.get(name) or {}
        if name in JSE:
            rand = dict(series)
        else:
            rand = {m: v * rate[m] for m, v in series.items() if m in rate}
        out[name] = {m: rand[m] / rand[_previous(m)] - 1 for m in sorted(rand) if _previous(m) in rand}
    return out


def with_proxies(returns: dict) -> tuple[dict, dict]:
    """Fill a young fund's missing early months with its proxy in rand. notes: name -> {proxy, months, from} when anything was borrowed."""
    out, notes = {k: dict(v) for k, v in returns.items()}, {}
    for name, proxy in PROXY.items():
        own, lent = returns.get(name) or {}, returns.get(proxy) or {}
        borrowed = {m: r for m, r in lent.items() if m not in own}
        if borrowed:
            out[name] = dict(sorted({**borrowed, **own}.items()))
            notes[name] = {"proxy": proxy, "months": len(borrowed), "from": min(own) if own else None}
    return out, notes
