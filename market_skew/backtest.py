"""Forward test from the app's own daily snapshots.

Old option chains are not free, so there is no ten-year backtest. Instead every daily run is kept, and this
checks what each bucket (and the top of the Asym list) did over the following 5 and 20 sessions, compared with
the average stock in the universe on the same days. It fills in as the days pile up.
"""
import pandas as pd

HORIZONS = {5: 7, 20: 28}  # sessions -> calendar days, so a skipped evening doesn't stretch the horizon
SLACK_DAYS = 4
SPLIT_LIKE = 0.6  # a move this big over a month is almost always a split, not a trade
TOP_ASYM = 20
BUCKET_ORDER = ["Contrarian Bid", "Chase", "Hedged Rally", "Fear"]


def forward_returns(history: pd.DataFrame, days: int) -> pd.DataFrame:
    """One row per (date, symbol) with a stored close about `days` calendar days later, and its excess return."""
    dates = sorted(pd.to_datetime(history["date"].unique()))
    later = {}
    for start in dates:
        target = start + pd.Timedelta(days=days)
        match = next((d for d in dates if target <= d <= target + pd.Timedelta(days=SLACK_DAYS)), None)
        if match is not None:
            later[start.date().isoformat()] = match.date().isoformat()
    if not later:
        return pd.DataFrame(columns=["date", "symbol", "bucket", "asym", "excess"])
    closes = history.set_index(["date", "symbol"])["close"]
    rows = history[history["date"].isin(later)].copy()
    rows["future"] = [closes.get((later[d], s)) for d, s in zip(rows["date"], rows["symbol"])]
    rows = rows.dropna(subset=["future", "close"])
    rows["fwd"] = rows["future"] / rows["close"] - 1
    rows = rows[rows["fwd"].abs() < SPLIT_LIKE]
    rows["excess"] = rows["fwd"] - rows.groupby("date")["fwd"].transform("mean")
    return rows[["date", "symbol", "bucket", "asym", "excess"]]


def summary(history: pd.DataFrame) -> dict:
    days = int(history["date"].nunique()) if not history.empty else 0
    result = {"days": days, "horizons": {}}
    for horizon, calendar in HORIZONS.items():
        fwd = forward_returns(history, calendar)
        if fwd.empty:
            result["horizons"][horizon] = {"ready": False, "needs": max(horizon + 1 - days, 1)}
            continue
        rows = []
        for bucket in BUCKET_ORDER:
            part = fwd[fwd["bucket"] == bucket]["excess"]
            if len(part):
                rows.append({"group": bucket, "n": int(len(part)), "mean": float(part.mean()),
                             "hit": float((part > 0).mean())})
        top = fwd[fwd.groupby("date")["asym"].rank(ascending=False, method="first") <= TOP_ASYM]["excess"]
        if len(top):
            rows.append({"group": f"Top {TOP_ASYM} by Asym", "n": int(len(top)), "mean": float(top.mean()),
                         "hit": float((top > 0).mean())})
        result["horizons"][horizon] = {"ready": True, "dates": int(fwd["date"].nunique()), "rows": rows}
    return result
