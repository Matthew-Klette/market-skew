"""The Picks method: a swing-trading creator's public process, described generically. Pure rules, no network.

It buys Contrarian Bids (down against the market while options traders lean bullish), holds days to months, and
writes down an entry, a stop and a target first. It tells you where to look, not what will happen.

Rules (0 comes first: The quality score says whether it is attractive, this scan says when):
  0. Adjusted Quality score at or above gate.HIS_WAY_MIN (the threshold lives only in gate.py) and depth not Thin.
  1. Contrarian Bid bucket, price $5+, $50M+ traded a day, mid-price option quotes, implied volatility 100% or less,
     not down more than 35% in a month.
  2. Score = the options gap (asym) + 15 if up today + 10 if money is moving into its sector.
  3. One per sector, at most 5. In a stormy market (S&P 500 down 5%+ over a month and VIX up 5%+ today), at most 2.
  3b. Earnings: no trade when the company reports within 7 days of the report date (inclusive); "Wait until after
      results on 19 Nov". No earnings data never blocks; the card says "earnings date unknown".
  4. Plan: stop = entry less the bigger of 4% or 1.2 x the two-week options move; target = entry + 2 x the stop distance;
     give it 28 days.
Fees: a US buy and a US sell (costs.py). No rand conversion here: the money is already in dollars.
"""
import datetime as dt
import math
from dataclasses import asdict, dataclass

import pandas as pd

from . import costs
from . import gate as sentinel_gate
from .closes import price_at
from .costs import net_return

MAX_TRADES, STORM_TRADES = 5, 2
MIN_PRICE, MIN_DOLLAR_VOLUME, MAX_ATM_IV, WORST_MONTH = 5.0, 50e6, 1.0, -0.35
UP_TODAY_POINTS, FLOW_POINTS = 15, 10
MIN_STOP, MOVE_MULTIPLE, MOVE_DAYS, TARGET_MULTIPLE, HOLD_DAYS = 0.04, 1.2, 10, 2.0, 28
STORM_MONTH, STORM_VIX = -0.05, 0.05
EARNINGS_WAIT_DAYS = 7


@dataclass(frozen=True)
class Trade:
    symbol: str
    name: str
    sector: str
    score: int
    entry: float
    stop: float
    target: float
    until: str
    stop_pct: float
    target_pct: float
    atm: float
    ret_1m: float
    reasons: tuple[str, ...]
    earnings: str = ""


def days_to_report(result: dict | None, today: str) -> int | None:
    """Calendar days from `today` to the next report, None when unknown, already past or a fund."""
    if not result or result.get("kind") == "fund" or not result.get("next_date"):
        return None
    days = (dt.date.fromisoformat(result["next_date"]) - dt.date.fromisoformat(today)).days
    return days if days >= 0 else None


def wait_note(result: dict | None, today: str) -> str | None:
    """'Wait until after results on 19 Nov' when the report is 0-7 days away, else None (missing data never blocks)."""
    days = days_to_report(result, today)
    if days is None or days > EARNINGS_WAIT_DAYS:
        return None
    day = dt.date.fromisoformat(result["next_date"])
    return f"Wait until after results on {day.day} {day:%b}"


def earnings_line(result: dict | None, today: str) -> str:
    """Small earnings note on a pick: 'Reports in 3 days', 'earnings date unknown'; empty for funds."""
    if result and result.get("kind") == "fund":
        return ""
    days = days_to_report(result, today)
    if days is None:
        return "earnings date unknown"
    return "Reports today" if days == 0 else f"Reports in {days} day{'' if days == 1 else 's'}"


def is_stormy(indexes: dict) -> bool:
    spy = (indexes.get("SPY") or {}).get("ret_1m")
    vix = (indexes.get("VIX") or {}).get("ret_1d")
    return spy is not None and vix is not None and spy <= STORM_MONTH and vix >= STORM_VIX


def plan(entry: float, atm: float, today: str) -> tuple[float, float, str]:
    move = MOVE_MULTIPLE * atm * math.sqrt(MOVE_DAYS / 252)
    stop = entry * (1 - max(MIN_STOP, move))
    target = entry + TARGET_MULTIPLE * (entry - stop)
    return stop, target, (dt.date.fromisoformat(today) + dt.timedelta(days=HOLD_DAYS)).isoformat()


def _reasons(row, inflow: bool) -> tuple[str, ...]:
    out = [f"Down {abs(row['ret_1m']) * 100:.0f}% this month, but options traders lean towards a bounce."]
    if row["ret_1d"] > 0:
        out.append("Up today, the first sign it may have stopped falling.")
    if inflow:
        out.append(f"Money is flowing into {row['sector']}.")
    return tuple(out)


def _with_score(reasons: tuple[str, ...], gate: dict | None, symbol: str) -> tuple[str, ...]:
    entry = (gate or {}).get(symbol)
    return (entry["line"], *reasons) if entry else reasons


def choose(scored: pd.DataFrame, sector_flow: dict, indexes: dict, today: str, excluded=frozenset(),
           gate: dict | None = None, earnings: dict | None = None) -> list[Trade]:
    """`gate` is gate.table(...): attractive first (adjusted Quality score at or above gate.HIS_WAY_MIN, depth not Thin), then the timing rules.
    None = no Quality score gate; an empty dict means no company passes."""
    frame = scored[
        ~scored["symbol"].isin(excluded) & (scored["bucket"] == "Contrarian Bid") & (scored["close"] >= MIN_PRICE)
        & (scored["dvol_21"] >= MIN_DOLLAR_VOLUME) & (scored["source"] == "mid")
        & (scored["atm"] <= MAX_ATM_IV) & (scored["ret_1m"] > WORST_MONTH)
    ].copy()
    if gate is not None:
        frame = frame[[sentinel_gate.passes(gate.get(sym)) for sym in frame["symbol"]]].copy()
    if earnings is not None:
        frame = frame[[wait_note(earnings.get(sym), today) is None for sym in frame["symbol"]]].copy()
    if frame.empty:
        return []
    frame["ret_1d"] = frame["ret_1d"].fillna(0)
    inflow = frame["sector"].map(sector_flow).fillna(0) > 0
    frame["inflow"] = inflow
    frame["score"] = (frame["asym"].fillna(0) + UP_TODAY_POINTS * (frame["ret_1d"] > 0) + FLOW_POINTS * inflow).round().astype(int)
    limit = STORM_TRADES if is_stormy(indexes) else MAX_TRADES
    frame = frame.sort_values("score", ascending=False, kind="stable").drop_duplicates("sector").head(limit)
    trades = []
    for r in frame.to_dict("records"):
        entry = float(r["close"])
        stop, target, until = plan(entry, float(r["atm"]), today)
        trades.append(Trade(r["symbol"], r.get("name") or r["symbol"], r["sector"], int(r["score"]), entry, stop, target, until,
                            stop / entry - 1, target / entry - 1, float(r["atm"]), float(r["ret_1m"]), _with_score(_reasons(r, bool(r["inflow"])), gate, r["symbol"]),
                            "" if earnings is None else earnings_line(earnings.get(r["symbol"]), today)))
    return trades


def as_dicts(trades: list[Trade]) -> list[dict]:
    return [{**asdict(t), "reasons": list(t.reasons)} for t in trades]


def settle(trade: dict, closes: pd.Series) -> dict | None:
    """Walks the daily closes after the entry date. First close at or under the stop, at or over the target, or on/after
    the give-up date ends it. None while it is still open."""
    after = closes.dropna()
    after = after[after.index.date > dt.date.fromisoformat(trade["date"])]
    until = dt.date.fromisoformat(trade["until"])
    for day, price in after.items():
        status = ("stopped" if price <= trade["stop"] else "target" if price >= trade["target"]
                  else "time" if day.date() >= until else None)
        if status:
            return {"status": status, "exit_date": day.date().isoformat(), "exit_price": float(price),
                    "net_ret": net_return(trade["entry"], float(price))}
    return None


def record(rows: list[dict], closes: pd.DataFrame) -> list[dict]:
    """Each paper trade with price now / result and VOO over the same stretch (entry day to exit, or to the latest close)."""
    out = []
    voo = closes["VOO"] if "VOO" in closes else pd.Series(dtype=float)
    latest = closes.index[-1].date().isoformat() if len(closes) else None
    for r in rows:
        closed = r["status"] != "open"
        now = r["exit_price"] if closed else (price_at(closes[r["symbol"]], latest) if r["symbol"] in closes and latest else None)
        ret = r["net_ret"] if closed else (net_return(r["entry"], now) if now else None)  # open: after fees, as if sold now
        end = r["exit_date"] if closed else latest
        voo_end = price_at(voo, end) if end and len(voo) else None
        voo_ret = voo_end / r["spy_entry"] - 1 if voo_end and r.get("spy_entry") else None
        out.append({**r, "now": now, "ret": ret, "voo_ret": voo_ret})
    return out
