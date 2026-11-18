"""Earnings dates and track record for stocks (never funds), from Yahoo through yfinance. Fetched in the scan and by
`skew earnings`, one name at a time, paced, with a timeout; the page only reads what was saved. Any failure means no line.

Plain words, e.g. "Reports 12 Dec · beat 4 of the last 4, average surprise +3.1%". Knowing the dates is a habit, not a signal."""
import concurrent.futures
import datetime as dt
import time
from pathlib import Path

import pandas as pd

from . import cache
from .funds import FUNDS

PATH = cache.DATA / "earnings.json"
FRESH_SECONDS = 24 * 3600
PACE_SECONDS = 1.0
TIMEOUT_SECONDS = 20
LAST = 4
SOON_DAYS = 14
WIDE = 0.20          # analyst high-low range over 20% of the consensus is a wide spread
FUND_TYPES = ("ETF", "MUTUALFUND")
NY = "America/New_York"


def _next_date(dates: pd.DataFrame | None, today: dt.date) -> str | None:
    if dates is None or dates.empty:
        return None
    pending = dates[dates["Reported EPS"].isna()] if "Reported EPS" in dates else dates
    days = sorted(d.date() for d in pending.index.tz_convert(NY) if d.date() >= today) if pending.size else []
    return days[0].isoformat() if days else None


def _track(dates: pd.DataFrame | None, history: pd.DataFrame | None) -> tuple[int, int, float | None]:
    """(beats, quarters counted, average surprise %) over the last four reported quarters."""
    if history is not None and not history.empty and {"epsActual", "epsEstimate"} <= set(history.columns):
        last = history.sort_index().dropna(subset=["epsActual", "epsEstimate"]).tail(LAST)
        if len(last):
            surprise = last["surprisePercent"].dropna() * 100 if "surprisePercent" in last else pd.Series(dtype=float)
            return int((last["epsActual"] > last["epsEstimate"]).sum()), len(last), (float(surprise.mean()) if len(surprise) else None)
    if dates is not None and not dates.empty and "Reported EPS" in dates:
        done = dates.dropna(subset=["Reported EPS", "EPS Estimate"]).sort_index().tail(LAST)
        if len(done):
            surprise = done["Surprise(%)"].dropna() if "Surprise(%)" in done else pd.Series(dtype=float)
            return int((done["Reported EPS"] > done["EPS Estimate"]).sum()), len(done), (float(surprise.mean()) if len(surprise) else None)
    return 0, 0, None


def _spread(estimate: dict | None) -> str | None:
    try:
        high, low, avg = (float(estimate[k]) for k in ("high", "low", "avg"))
    except (TypeError, KeyError, ValueError):
        return None
    if avg == 0 or pd.isna(high) or pd.isna(low) or pd.isna(avg):
        return None
    return "wide" if (high - low) / abs(avg) > WIDE else "narrow"


def parse(dates, history, estimate: dict | None, today: dt.date) -> dict | None:
    """One company's reading from the raw tables, or None when Yahoo gave nothing usable."""
    next_date = _next_date(dates, today)
    beats, of, average = _track(dates, history)
    if next_date is None and of == 0:
        return None
    return {"kind": "stock", "next_date": next_date, "beats": beats, "of": of,
            "avg_surprise": None if average is None else round(average, 2), "spread": _spread(estimate)}


def soon(next_date: str | None, today: dt.date | None = None) -> bool:
    """True when the report is within two weeks (today included)."""
    if not next_date:
        return False
    days = (dt.date.fromisoformat(next_date) - (today or dt.date.today())).days
    return 0 <= days <= SOON_DAYS


def line(result: dict | None) -> str:
    if not result:
        return ""
    if result.get("kind") == "fund":
        return "Fund: no earnings"
    day = dt.date.fromisoformat(result["next_date"]) if result.get("next_date") else None
    head = f"Reports {day.day} {day:%b}" if day else "Next date not announced yet"
    if result.get("of"):
        avg = result.get("avg_surprise")
        track = f"beat {result['beats']} of the last {result['of']}" + ("" if avg is None else f", average surprise {avg:+.1f}%")
    else:
        track = "no track record yet"
    split = " · analysts disagree more than usual" if result.get("spread") == "wide" else ""
    return f"{head} · {track}{split}"


def _call(fn):
    try:
        return fn()
    except Exception:
        return None


def _estimate(ticker) -> dict | None:
    table = _call(lambda: ticker.earnings_estimate)
    if table is None or getattr(table, "empty", True) or not {"high", "low", "avg"} <= set(table.columns):
        return None
    row = table.loc["0q"] if "0q" in table.index else table.iloc[0]
    return {k: row[k] for k in ("high", "low", "avg")}


def fetch(symbol: str, today: dt.date, factory=None) -> dict | None:
    """One company's result (or {"kind": "fund"}), None when Yahoo gave nothing. Each Yahoo call fails on its own."""
    if symbol in FUNDS:
        return {"kind": "fund"}
    import yfinance as yf
    ticker = (factory or yf.Ticker)(symbol)
    dates = _call(lambda: ticker.get_earnings_dates(limit=8))
    history = _call(lambda: ticker.earnings_history)
    result = parse(dates, history, _estimate(ticker), today)
    if result is None and (dates is None or dates.empty):
        quote = _call(lambda: (ticker.info or {}).get("quoteType"))
        return {"kind": "fund"} if quote in FUND_TYPES else None
    return result


def _timed(symbol: str, today: dt.date, factory, timeout: float) -> dict | None:
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(fetch, symbol, today, factory).result(timeout=timeout)
    except Exception:
        return None
    finally:
        pool.shutdown(wait=False)


def cached(path: Path = PATH) -> dict[str, dict]:
    """Saved results by symbol; what the page and the report read."""
    return {s: v["data"] for s, v in cache.read(path).items() if isinstance(v, dict) and v.get("data")}


def refresh(symbols: list[str], today: dt.date | None = None, factory=None, path: Path = PATH, sleep=time.sleep,
            now: float | None = None, timeout: float = TIMEOUT_SECONDS, log=print) -> dict[str, dict]:
    """Sequential and paced (one name a second). Names saved within a day are skipped; a failed name keeps its last good
    value and is left alone for 15 minutes. Returns the results for `symbols`."""
    today = today or dt.date.today()
    stamp = now if now is not None else time.time()
    saved, fetched = cache.read(path), 0
    for symbol in dict.fromkeys(symbols):
        old = saved.get(symbol) or {}
        if old.get("data") and stamp - old.get("at", 0) < FRESH_SECONDS or cache.backing_off(old.get("failed_at"), stamp):
            continue
        if fetched:
            sleep(PACE_SECONDS)
        fetched += 1
        data = _timed(symbol, today, factory, timeout)
        saved = {**saved, symbol: {"data": data, "at": stamp} if data else {**old, "failed_at": stamp}}
        if not data:
            log(f"earnings for {symbol} skipped (no data)"[:200])
    cache.write(path, saved)
    return {s: (saved.get(s) or {}).get("data") for s in dict.fromkeys(symbols) if (saved.get(s) or {}).get("data")}
