"""Glue for His way: adds today's trades to the paper table, settles open ones on daily closes, builds the record."""
import pandas as pd

from . import market, store, swing
from .closes import price_at

COMPARE = "VOO"


def _closes_for(symbols: list[str], closes: pd.DataFrame | None, fetch) -> pd.DataFrame:
    have = closes if closes is not None else pd.DataFrame()
    missing = [s for s in dict.fromkeys(symbols) if s not in have or have[s].dropna().empty]
    if not missing:
        return have
    got, _ = fetch(missing, period="4mo")
    return got if have.empty else have.join(got.drop(columns=[c for c in got if c in have]), how="outer").sort_index()


def update(conn, date: str, trades: list[dict], closes: pd.DataFrame | None = None, fetch=market.prices) -> list[dict]:
    """Returns the paper record (open and closed). Closes already downloaded are used; only missing symbols are fetched."""
    open_symbols = [r["symbol"] for r in store.swing_rows(conn) if r["status"] == "open"]
    wanted = open_symbols + [t["symbol"] for t in trades] + [COMPARE]
    frame = _closes_for(wanted, closes, fetch)
    voo_series = frame[COMPARE] if COMPARE in frame else None
    store.add_swing(conn, date, trades, price_at(voo_series, date))
    for row in store.swing_rows(conn):  # trades saved before VOO was tracked get its close on their day
        if row["spy_entry"] is None and (price := price_at(voo_series, row["date"])):
            store.set_swing_voo(conn, row["symbol"], row["date"], price)
    for row in store.swing_rows(conn):
        if row["status"] == "open" and row["symbol"] in frame:
            result = swing.settle(row, frame[row["symbol"]])
            if result:
                store.close_swing(conn, row["symbol"], row["date"], result)
    return swing.record(store.swing_rows(conn), frame)
