"""Puts the Quality score together from what is already saved: company numbers (weekly SEC download), the scan's prices and
option bets, and yearly closes for the "vs its own history" check. Never fails the scan."""
import datetime as dt

import pandas as pd

from . import cache, market, sentinel, store, valuation

YEAR_CLOSES = cache.DATA / "year_closes.json"
YEARS_SECONDS = 7 * 24 * 3600
HISTORY_PERIOD = "6y"
THREE_MONTHS = 63  # sessions


def _clean(value):
    return None if value is None or value != value else float(value)


def three_month_returns(close: pd.DataFrame) -> dict[str, float | None]:
    """Each symbol's return over the last ~63 sessions (None when there are not that many closes)."""
    close = close.ffill(limit=2)
    if len(close) <= THREE_MONTHS:
        return {}
    return {s: _clean(v) for s, v in (close.iloc[-1] / close.iloc[-1 - THREE_MONTHS] - 1).items()}


def prices_from_scan(scored: pd.DataFrame, close: pd.DataFrame, year_closes: dict) -> dict[str, dict]:
    """symbol -> price inputs for every name in the scan's universe (sector medians need all of them)."""
    ret3 = three_month_returns(close)
    out = {}
    for r in scored.to_dict("records"):
        s = r["symbol"]
        out[s] = {"name": r.get("name") if isinstance(r.get("name"), str) else s, "sector": r.get("sector"),
                  "market_cap": _clean(r.get("market_cap")), "close": _clean(r.get("close")), "ret_1m": _clean(r.get("ret_1m")),
                  "ret_3m": ret3.get(s), "bet_z": _clean(r.get("bet_z")), "bucket": r.get("bucket"),
                  "year_closes": year_closes.get(s) or {}}
    return out


def saved_betas(path=None) -> dict[str, float]:
    """symbol -> beta measured at the last history download (weekly returns vs SPY, 2 years); {} until one has run."""
    return {s: float(b) for s, b in (cache.read(path or YEAR_CLOSES).get("betas") or {}).items() if isinstance(b, (int, float))}


def year_closes(symbols: list[str], today: dt.date, fetch=market.prices, path=YEAR_CLOSES) -> dict[str, dict[str, float]]:
    """symbol -> {calendar year: that year's last close}, completed years only. Six years of daily closes are downloaded for
    everything once a week; in between, only symbols not yet saved are downloaded and merged in. The same download gives each
    name's beta against SPY (valuation.beta_from_closes), saved beside the closes."""
    saved = cache.read(path)
    stamp = saved.get("at")
    current = bool(stamp) and (today - dt.date.fromisoformat(stamp)).days < 7
    closes, betas = (saved.get("closes", {}), saved.get("betas", {})) if current else ({}, {})
    wanted = [s for s in dict.fromkeys(symbols) if s not in closes]
    if not wanted:
        return closes
    close, _ = fetch(list(dict.fromkeys(wanted + ["SPY"])), period=HISTORY_PERIOD)
    yearly = close.groupby(close.index.year).last()
    new = {s: ({str(y): float(v) for y, v in yearly[s].dropna().items() if y < today.year} if s in yearly.columns else {}) for s in wanted}
    market_close = close["SPY"] if "SPY" in close else None
    for s in wanted:
        beta = valuation.beta_from_closes(close[s], market_close) if market_close is not None and s in close and s != "SPY" else None
        if beta is not None:
            betas[s] = beta
    cache.write(path, {"at": stamp if current else today.isoformat(), "closes": {**closes, **new}, "betas": betas})
    return {**closes, **new}


def with_values(rows: list[dict], betas: dict[str, float] | None = None) -> list[dict]:
    """Each row gains its fair-value range ('value'), computed from the row's own numbers, price and measured beta
    (1.0 where none was measured). Cheap; `betas` defaults to the saved ones."""
    betas = saved_betas() if betas is None else betas
    return [{**r, "value": valuation.for_row(r, betas.get(r.get("symbol"), valuation.DEFAULT_BETA))} for r in rows]


def revalue(conn) -> tuple[str | None, int, int]:
    """`skew value`: recompute every stored row's fair-value range from stored data. (date, rows, rows with a range)."""
    date, rows = store.sentinel(conn)
    if not rows:
        return None, 0, 0
    out = with_values(rows)
    store.save_sentinel(conn, date, out)
    return date, len(out), sum(r["value"]["ok"] for r in out)


def compute(conn, date: str, prices: dict[str, dict]) -> list[dict]:
    """Score every company with numbers, against the last stored run, and save under `date`."""
    numbers = {s: m for s, m in store.fundamentals(conn).items() if s in prices}  # only names the scan priced
    rows = with_values(sentinel.score_all(numbers, prices, store.sentinel_scores(conn, date)))
    if rows:
        store.save_sentinel(conn, date, rows)
    return rows


def refresh(conn, date: str, scored: pd.DataFrame, close: pd.DataFrame, today: dt.date | None = None, fetch=market.prices,
            path=YEAR_CLOSES) -> int:
    """After the weekly numbers refresh: score the scan's universe. A failed history download only drops the history check."""
    today = today or dt.date.today()
    have = [s for s in store.fundamentals(conn) if s in set(scored["symbol"])]
    if not have:
        return 0
    try:
        years = year_closes(have, today, fetch, path)
    except Exception as error:
        print(f"price history skipped: {error}"[:300], flush=True)
        years = {}
    return len(compute(conn, date, prices_from_scan(scored, close, years)))


def recompute(conn) -> tuple[str, int]:
    """`skew sentinel`: rescore from stored data only. Price inputs come from the newest stored run (or, the first time,
    from the saved stocks table, which has no 3-month return, names or market values)."""
    body = store.report(conn)
    if not body:
        raise RuntimeError("No report yet. Run ./skew scan")
    date = body["date"]
    _, old = store.sentinel(conn)
    if old:
        prices = {r["symbol"]: r["px"] for r in old}
        sectors = {}
    else:
        day = store.stocks_on(conn, date)
        names = {s["symbol"]: s.get("name") for s in body["stocks"]}
        prices = {r["symbol"]: {"name": names.get(r["symbol"]) or r["symbol"], "sector": r["sector"], "close": _clean(r["close"]),
                                "ret_1m": _clean(r["ret_1m"]), "bet_z": _clean(r["bet_z"]), "bucket": r["bucket"]}
                  for r in day.to_dict("records")}
    return date, len(compute(conn, date, prices))
