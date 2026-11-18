"""Everything that talks to the internet: the Nasdaq listing, Yahoo prices, Yahoo option chains and sectors.
No account, no key, nothing about you in any request."""
import datetime as dt
import json
import re
import threading
import time
import urllib.request

import pandas as pd
import yfinance as yf

from .options import SkewReading, read_chain
from .sectors import classify

SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true"
PLAIN_TICKER = re.compile(r"^[A-Z]{1,5}([./][A-Z])?$")
MIN_MARKET_CAP = 300e6
TARGET_DAYS, MIN_DAYS = 30, 14
PRICE_BATCH = 250
RETRIES = 3
PRICE_TIMEOUT_SECONDS = 60  # per batch download; yfinance's own default is 10, too short for 250 names
CHAIN_TIMEOUT_SECONDS = 30  # one name's expiry list plus chain; a hung Yahoo call must not freeze the scan
BACKOFF_SECONDS = (3, 10)  # 5/15/40 made a 2,000-name run take 41 min on 2026-11-18; names with no options ate the waits


MIN_GAP_SECONDS = 0.35  # ~3 chains a second across all workers; faster got the session throttled
_pace_lock = threading.Lock()
_last_start = [0.0]


def _pace() -> None:
    with _pace_lock:
        wait = _last_start[0] + MIN_GAP_SECONDS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_start[0] = time.monotonic()


class Throttled(Exception):
    """Yahoo answers a throttled options request with an empty expiry list instead of an error."""


def listings() -> pd.DataFrame:
    """US-listed common stocks from Nasdaq's public screener: symbol, rough 1-day dollar volume, market cap."""
    request = urllib.request.Request(SCREENER_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        rows = json.load(response)["data"]["rows"]
    frame = pd.DataFrame(rows)
    frame = frame[frame["symbol"].str.match(PLAIN_TICKER)].copy()
    frame["symbol"] = frame["symbol"].str.replace(r"[./]", "-", regex=True)
    frame["price"] = pd.to_numeric(frame["lastsale"].str.replace("$", "", regex=False), errors="coerce")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    frame["market_cap"] = pd.to_numeric(frame["marketCap"], errors="coerce")
    frame["dvol_1d"] = frame["price"] * frame["volume"]
    frame = frame[frame["market_cap"] >= MIN_MARKET_CAP]
    frame["sector"] = [classify(sym, sec, ind) for sym, sec, ind in zip(frame["symbol"], frame["sector"], frame["industry"])]
    return frame[["symbol", "name", "sector", "dvol_1d", "market_cap"]].sort_values("dvol_1d", ascending=False)


def prices(symbols: list[str], period: str = "4mo") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Adjusted closes and volumes, one column per symbol, downloaded in batches."""
    closes, volumes = [], []
    for start in range(0, len(symbols), PRICE_BATCH):
        batch = symbols[start:start + PRICE_BATCH]
        data = yf.download(batch, period=period, auto_adjust=True, progress=False, threads=True, group_by="column",
                           timeout=PRICE_TIMEOUT_SECONDS)
        if data.empty:
            print(f"warning: no prices for a batch of {len(batch)} symbols starting {batch[0]}", flush=True)
            continue
        closes.append(data["Close"])
        volumes.append(data["Volume"])
    close = pd.concat(closes, axis=1).sort_index()
    volume = pd.concat(volumes, axis=1).sort_index()
    return close.loc[:, ~close.columns.duplicated()], volume.loc[:, ~volume.columns.duplicated()]


def price_stats(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """Per symbol: last close, 1-day / 1-week / 1-month return and dollar volume over 21 / 5 / 1 sessions."""
    close = close.ffill(limit=2)  # bridge a missing print, but a dead ticker drops out instead of showing 0%
    dollars = (close * volume).fillna(0)
    last = close.iloc[-1]
    stats = pd.DataFrame({
        "close": last,
        "ret_1d": last / close.iloc[-2] - 1,
        "ret_1w": last / close.iloc[-6] - 1,
        "ret_1m": last / close.iloc[-22] - 1,
        "dvol_21": dollars.iloc[-21:].mean(),
        "dvol_5": dollars.iloc[-5:].mean(),
        "dvol_today": dollars.iloc[-1],
    })
    stats.index.name = "symbol"
    return stats.reset_index().dropna(subset=["close", "ret_1m"])


def spy_off_high() -> float | None:
    """SPY's last close vs its highest close in the last year (zero or negative); None when the download fails."""
    from .narrative import off_high
    try:
        close, _ = prices(["SPY"], period="1y")
        return off_high(close["SPY"])
    except Exception as error:
        print(f"no 52-week high for SPY ({error})"[:200], flush=True)
        return None


def weekly_relative(close: pd.DataFrame, columns: dict[str, str], weeks: int = 4) -> dict:
    """Each sector ETF's weekly return minus SPY's, for the last few weeks (newest last)."""
    weekly = close.resample("W-FRI").last().pct_change().iloc[-weeks:]
    labels = []
    for end in weekly.index:
        start = end - pd.Timedelta(days=4)
        labels.append(f"{start:%b %-d}–{end:%b %-d}")
    rows = {}
    for name, etf in columns.items():
        if etf in weekly:
            rows[name] = [float(v) for v in (weekly[etf] - weekly["SPY"]).fillna(0)]
    month = close.iloc[-1] / close.iloc[-22] - 1
    one_month = {name: float(month[etf] - month["SPY"]) for name, etf in columns.items() if etf in month}
    return {"weeks": labels, "rows": rows, "rel_1m": one_month}


def _pick_expiry(expiries: tuple[str, ...], today: dt.date) -> str | None:
    usable = [e for e in expiries if (dt.date.fromisoformat(e) - today).days >= MIN_DAYS]
    if not usable:
        return None
    return min(usable, key=lambda e: abs((dt.date.fromisoformat(e) - today).days - TARGET_DAYS))


def _within(seconds: float, fn, *args):
    """Run fn(*args) in a helper thread and give up after `seconds` (the thread is left to finish by itself, as yfinance has no
    timeout on these calls). Raises what fn raised, or TimeoutError."""
    box: dict = {}

    def work():
        try:
            box["value"] = fn(*args)
        except BaseException as error:
            box["error"] = error
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise TimeoutError(f"timed out after {seconds:g}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _load_chain(symbol: str, today: dt.date):
    """(calls, puts, expiry) for the expiry nearest 30 days out; (None, None, None) when none is usable. Raises Throttled on an empty list."""
    ticker = yf.Ticker(symbol)
    expiries = ticker.options
    if not expiries:
        raise Throttled(f"{symbol}: no option expiries returned (throttled, or no listed options)")
    expiry = _pick_expiry(expiries, today)
    if not expiry:
        return None, None, None
    chain = ticker.option_chain(expiry)
    return chain.calls.to_dict("records"), chain.puts.to_dict("records"), expiry


def chain_skew(symbol: str, spot: float, today: dt.date, retries: int = RETRIES) -> tuple[SkewReading | None, str | None]:
    """The skew reading on the expiry nearest 30 days out. Returns (reading, expiry)."""
    for attempt in range(retries):
        try:
            _pace()
            calls, puts, expiry = _within(CHAIN_TIMEOUT_SECONDS, _load_chain, symbol, today)
            if not expiry:
                return None, None
            years = max((dt.date.fromisoformat(expiry) - today).days, 1) / 365
            return read_chain(calls, puts, spot, years), expiry
        except Exception as error:  # Yahoo throttles with a mix of exception types; back off and retry
            if attempt == retries - 1:
                raise RuntimeError(f"{symbol}: {error}") from error
            time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
    return None, None
