"""Builds the day's report (a plain dict, saved as JSON) from prices, skew readings and sectors. No network here."""
import pandas as pd

from . import picks as lights
from .narrative import todays_read
from .sectors import INDEXES, SECTOR_ETFS, UNCLASSIFIED
from .signals import group_table, score

TOP_STOCKS = 400


def _records(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    return [{k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()}
            for row in frame[columns].to_dict("records")]


def kpis(sectors: pd.DataFrame, indexes: dict, index_skew: dict) -> list[dict]:
    spy = indexes["SPY"]
    tiles = [{"label": "S&P 500 (SPY), 1 month", "value": spy["ret_1m"], "kind": "pct",
              "note": " · ".join(f"{k} {indexes[k]['ret_1m'] * 100:+.1f}%" for k in ("QQQ", "IWM", "RSP") if k in indexes)}]
    if not sectors.empty:
        into, out = sectors.loc[sectors["flow_bps"].idxmax()], sectors.loc[sectors["flow_bps"].idxmin()]
        steep, flat = sectors.loc[sectors["skew"].idxmax()], sectors.loc[sectors["skew"].idxmin()]
        tiles += [
            {"label": "Money moved in", "value": into["name"], "kind": "text", "note": f"turnover share {into['flow_bps']:+.1f} bps this week"},
            {"label": "Money moved out", "value": out["name"], "kind": "text", "note": f"turnover share {out['flow_bps']:+.1f} bps this week"},
            {"label": "Steepest sector skew", "value": steep["name"], "kind": "text", "note": f"{steep['skew'] * 100:.1f}% weighted 25Δ skew, puts in demand"},
            {"label": "Flattest sector skew", "value": flat["name"], "kind": "text", "note": f"{flat['skew'] * 100:.1f}%, calls in demand"},
        ]
    if "SPY" in index_skew:
        tiles.append({"label": "Index skew (SPY)", "value": index_skew["SPY"], "kind": "pct_plain",
                      "note": " · ".join(f"{k} {v * 100:.1f}%" for k, v in index_skew.items() if k != "SPY")})
    return tiles


def build(date: str, built_at: str, stats: pd.DataFrame, readings: dict, sector_of: dict, themes: dict,
          indexes: dict, index_skew: dict, heatmap: dict, prev_skew: dict, watchlist: set[str],
          expiry: str | None, failed: list[str]) -> tuple[dict, pd.DataFrame]:
    """Returns (report, scored stocks)."""
    frame = stats.copy()
    frame["sector"] = frame["symbol"].map(sector_of).fillna(UNCLASSIFIED)
    for field in ("skew", "put25", "call25", "atm", "call_volume", "put_volume", "source"):
        frame[field] = frame["symbol"].map(lambda s: getattr(readings[s], field) if readings.get(s) else None)
    frame["skew_prev"] = frame["symbol"].map(prev_skew)
    for column in ("name", "market_cap"):
        if column not in frame:
            frame[column] = None
    scored = score(frame, indexes["SPY"]["ret_1m"])
    totals = (scored["dvol_21"].sum(), scored["dvol_5"].sum())
    sector_groups = {name: scored.loc[scored["sector"] == name, "symbol"].tolist() for name in SECTOR_ETFS}
    sectors = group_table(scored, sector_groups, indexes["SPY"], *totals)
    theme_table = group_table(scored, themes, indexes["SPY"], *totals)
    scored = scored.assign(watch=scored["symbol"].isin(watchlist))
    holdings = lights.holdings_check(scored, watchlist)
    shown = pd.concat([scored.head(TOP_STOCKS), scored[scored["watch"]]]).drop_duplicates("symbol")
    body = {
        "date": date, "built_at": built_at, "expiry": expiry,
        "universe": int(len(stats)), "with_skew": int(len(scored)), "failed": failed[:50], "failed_count": len(failed),
        "unclassified": int((scored["sector"] == UNCLASSIFIED).sum()),
        "indexes": {k: {**v, "name": INDEXES.get(k, k), "skew": index_skew.get(k)} for k, v in indexes.items()},
        "kpis": kpis(sectors, indexes, index_skew),
        "read": todays_read(indexes, theme_table, sectors, scored, watchlist),
        "themes": _records(theme_table, list(theme_table.columns)),
        "sectors": _records(sectors, list(sectors.columns)),
        "heatmap": heatmap,
        "buckets": scored["bucket"].value_counts().to_dict(),
        "stocks": _records(shown, ["symbol", "name", "sector", "action", "bucket", "asym", "close", "ret_1d", "ret_1w", "ret_1m",
                                   "skew", "atm", "call_volume", "put_volume", "price_z", "bet_z", "watch", "source"]),
        "history_days": int(len(prev_skew) > 0),
        "holdings": holdings,
    }
    return body, scored
