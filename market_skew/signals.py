"""Per-stock signals and the four buckets.

price_z  how the stock did over a month against SPY, scaled by the universe's spread. Above 0 = beat SPY.
bet_z    what the options market is betting, as a robust z-score. Built from up to three parts:
         - skew against its sector's median (low skew = calls bid, people pay for upside)
         - skew change against the stock's own last 5 readings (needs history; skipped on day one)
         - call/put volume today against the universe median (half weight; volume is noisy)
         Positive = bets lean bullish.

Buckets cross the two signs:
  price down + bets bullish -> Contrarian Bid   price down + bets bearish -> Fear
  price up   + bets bullish -> Chase            price up   + bets bearish -> Hedged Rally

Asym ranks the most lopsided set-ups first: 50 x (bet_z - 0.5 x price_z), plus 25 when a falling name
was up today (the "done falling" tell), floored at 0. It is a where-to-look list, not a forecast.
"""
import numpy as np
import pandas as pd

Z_CLIP = 3.0
FLOW_WEIGHT = 0.5
BOUNCE_BONUS = 25
BUCKETS = {
    (False, True): ("Contrarian Bid", "FRESH LOOK - contrarian bid"),
    (False, False): ("Fear", "AVOID - fear"),
    (True, True): ("Chase", "MOMENTUM - crowded"),
    (True, False): ("Hedged Rally", "TIGHTEN - hedged rally"),
}


def robust_z(values: pd.Series, centre: bool = True) -> pd.Series:
    """Robust z-score. With centre=False zero stays zero, so the sign keeps its meaning (e.g. beat SPY or not)."""
    clean = values.astype(float)
    median = clean.median() if centre else 0.0
    mad = (clean - clean.median()).abs().median() * 1.4826
    if not mad or np.isnan(mad):
        spread = clean.std()
        mad = spread if spread and not np.isnan(spread) else 1.0
    return ((clean - median) / mad).clip(-Z_CLIP, Z_CLIP)


def _bet_score(frame: pd.DataFrame) -> pd.Series:
    sector_median = frame.groupby("sector")["skew"].transform("median")
    parts = [(-robust_z(frame["skew"] - sector_median)).fillna(0), ]
    weights = [1.0]
    if "skew_prev" in frame and frame["skew_prev"].notna().any():
        change = frame["skew"] - frame["skew_prev"]
        parts.append((-robust_z(change)).fillna(0))
        weights.append(1.0)
    flow = np.log((frame["call_volume"].fillna(0) + 1) / (frame["put_volume"].fillna(0) + 1))
    parts.append(robust_z(flow).fillna(0))
    weights.append(FLOW_WEIGHT)
    total = sum(w * p for w, p in zip(weights, parts))
    return robust_z(total / sum(weights))


def score(stocks: pd.DataFrame, spy_1m: float) -> pd.DataFrame:
    """Returns a new frame with price_z, bet_z, bucket, action and asym. Rows without a skew reading are dropped."""
    frame = stocks.dropna(subset=["skew", "ret_1m"]).copy()
    if frame.empty:
        return frame.assign(price_z=[], bet_z=[], bucket=[], action=[], asym=[])
    frame["price_z"] = robust_z(frame["ret_1m"] - spy_1m, centre=False)
    frame["bet_z"] = _bet_score(frame)
    keys = list(zip(frame["price_z"] >= 0, frame["bet_z"] >= 0))
    frame["bucket"] = [BUCKETS[k][0] for k in keys]
    frame["action"] = [BUCKETS[k][1] for k in keys]
    bounce = ((frame["price_z"] < 0) & (frame["ret_1d"] > 0)).astype(float) * BOUNCE_BONUS
    frame["asym"] = (50 * (frame["bet_z"] - 0.5 * frame["price_z"]) + bounce).clip(lower=0).round().astype(int)
    return frame.sort_values("asym", ascending=False)


def capped_weights(dollar_volume: pd.Series, cap: float = 0.25) -> pd.Series:
    """Dollar-volume weights where no single name carries more than `cap` (unless there are too few names)."""
    weights = dollar_volume.clip(lower=0).astype(float)
    if weights.sum() <= 0:
        return pd.Series(1 / len(weights), index=weights.index) if len(weights) else weights
    weights = weights / weights.sum()
    if len(weights) * cap < 1:
        return weights
    for _ in range(50):
        over = weights > cap + 1e-12
        if not over.any():
            break
        spare = (weights[over] - cap).sum()
        weights = weights.where(~over, cap)
        under = ~over & (weights < cap)
        if weights[under].sum() <= 0:
            break
        weights = weights + spare * weights.where(under, 0) / weights[under].sum()
    return weights


def group_table(scored: pd.DataFrame, membership: dict[str, list[str]], spy: dict, total_dvol_21: float,
                total_dvol_5: float) -> pd.DataFrame:
    """One row per group (sector or theme): returns against SPY, trend, money flow, breadth and skew."""
    rows = []
    for name, symbols in membership.items():
        members = scored[scored["symbol"].isin(symbols)]
        if len(members) < 2:
            continue
        w = capped_weights(members["dvol_21"])
        rel_1m = float((w * members["ret_1m"]).sum() - spy["ret_1m"])
        rel_1w = float((w * members["ret_1w"]).sum() - spy["ret_1w"])
        today = float((w * members["ret_1d"]).sum())
        share_21 = members["dvol_21"].sum() / total_dvol_21 if total_dvol_21 else 0
        share_5 = members["dvol_5"].sum() / total_dvol_5 if total_dvol_5 else 0
        rows.append({
            "name": name, "count": int(len(members)), "rel_1m": rel_1m, "rel_1w": rel_1w, "today": today,
            "vol_today": float(members["dvol_today"].sum() / members["dvol_21"].sum()) if members["dvol_21"].sum() else 1.0,
            "trend": "improving" if rel_1w > rel_1m / 4.3 else "fading",
            "flow_bps": float((share_5 - share_21) * 10_000),
            "breadth": float((members["ret_1m"] > spy["ret_1m"]).mean()),
            "skew": float((w * members["skew"]).sum()),
            "leaders": members.nlargest(3, "ret_1m")["symbol"].tolist(),
        })
    if not rows:
        return pd.DataFrame(columns=["name", "count", "rel_1m", "rel_1w", "today", "vol_today", "trend",
                                     "flow_bps", "breadth", "skew", "leaders"])
    return pd.DataFrame(rows).sort_values("rel_1m", ascending=False).reset_index(drop=True)
