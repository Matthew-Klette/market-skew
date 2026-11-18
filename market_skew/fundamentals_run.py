"""Weekly company numbers: fetch (cached) EDGAR frames, compute per company, save to SQLite. Never fails the scan."""
import datetime as dt
import json

from . import edgar, fundamentals, store


def refresh(conn, symbols: list[str], today: dt.date | None = None, fetch=edgar.fetch_all, mapping=None, log=print) -> dict:
    """Returns {'rows': n, 'requests': n, 'failed': n, 'universe': n}. Foreign filers with no US-GAAP revenue get no row."""
    today = today or dt.date.today()
    stats = fetch(today, log=log)
    mapping = mapping if mapping is not None else edgar.ticker_map()
    frames = edgar.load_frames(today)
    rows, cache_by_cik = [], {}
    for symbol in symbols:
        cik = edgar.cik_for(symbol, mapping)
        if cik is None:
            continue
        if cik not in cache_by_cik:
            cache_by_cik[cik] = fundamentals.compute(edgar.company_series(cik, today, frames))
        metrics = cache_by_cik[cik]
        if metrics:
            rows.append((symbol, cik, metrics["as_of"], json.dumps(metrics)))
    store.save_fundamentals(conn, rows)
    return {**stats, "rows": len(rows), "universe": len(symbols)}
