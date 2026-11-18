"""My way's paper record, after EasyEquities fees, against VOO over the same stretch. Pure: no network.

A Steady pick is bought with rand: converted to dollars (fx fee) then a US buy fee. Nothing is sold, so no sell fee.
VOO is the plain comparison (no fees), the same way His way's record is compared.
A pick settles at day 28. From then its result is frozen at the day-28 close (and VOO's at the same day), so it stops
moving with the market; `freezes` works out those closes and the scan saves them.
"""
import datetime as dt

import pandas as pd

from . import costs
from .closes import price_at

SETTLED_DAYS = 28  # a pick counts toward the evidence once it has had about a month
FEE_STEPS = ("fx_convert", "usd_buy")


def net_return(entry: float, now: float) -> float:
    return costs.net_return(entry, now, FEE_STEPS)


def _age(row: dict, today: str) -> int:
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(row["date"])).days


def _day_28(row: dict) -> str:
    return (dt.date.fromisoformat(row["date"]) + dt.timedelta(days=SETTLED_DAYS)).isoformat()


def _close_on(series: pd.Series | None, day: str) -> float | None:
    """The close on `day` (or the session before), only once the series reaches that day."""
    if series is None or series.dropna().empty or series.dropna().index[-1].date() < dt.date.fromisoformat(day):
        return None
    return price_at(series, day)


def freezes(rows: list[dict], closes: pd.DataFrame, voo: pd.Series | None, today: str) -> list[tuple[str, float | None, float | None]]:
    """(symbol, pick close, VOO close) on day 28 for settled picks that are not frozen yet and whose data reaches that day."""
    out = []
    for r in rows:
        if _age(r, today) < SETTLED_DAYS or (r.get("exit_close") and r.get("voo_exit")):
            continue
        day = _day_28(r)
        pick = None if r.get("exit_close") else _close_on(closes[r["symbol"]] if r["symbol"] in closes else None, day)
        compare = None if r.get("voo_exit") else _close_on(voo, day)
        if pick or compare:
            out.append((r["symbol"], pick, compare))
    return out


def record(rows: list[dict], prices_now: dict, voo: pd.Series | None, today: str) -> list[dict]:
    """rows: store.paper_rows. voo: VOO closes (a Series by date) used for the entry (if missing) and for now."""
    voo_now = price_at(voo, today)
    out = []
    for r in rows:
        settled = _age(r, today) >= SETTLED_DAYS
        now = (r.get("exit_close") if settled else None) or prices_now.get(r["symbol"])
        voo_end = (r.get("voo_exit") if settled else None) or voo_now
        entry_voo = r.get("voo_entry") or price_at(voo, r["date"])
        out.append({"symbol": r["symbol"], "date": r["date"], "entry": r["entry"], "now": now,
                    "ret": net_return(r["entry"], now) if now else None,
                    "voo_ret": voo_end / entry_voo - 1 if voo_end and entry_voo else None,
                    "settled": settled})
    return out
