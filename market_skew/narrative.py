"""Today's read: five or six sentences written by fixed rules from the numbers on the page.

Same rules every day, so every claim can be checked in the tables underneath. No model writes this.
"""
import pandas as pd

BROAD_BREADTH = 0.7
NARROW_BREADTH = 0.4
CALM_VIX_MOVE = 0.03
ROTATION_GAP = 0.02   # SPY vs equal-weight RSP, one month: 2 points or more is a story
AT_HIGH = 0.0005


def pct(value: float, signed: bool = True) -> str:
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def tape(indexes: dict) -> str:
    spy, qqq, iwm = indexes["SPY"], indexes["QQQ"], indexes["IWM"]
    vix = indexes.get("VIX")
    parts = [f"SPY {pct(spy['ret_1d'])} today ({pct(spy['ret_1m'])} on the month)",
             f"QQQ {pct(qqq['ret_1d'])}", f"small caps (IWM) {pct(iwm['ret_1d'])}"]
    if vix is not None:
        parts.append(f"volatility (VIX) {pct(vix['ret_1d'])}")
    moves = [spy["ret_1d"], qqq["ret_1d"], iwm["ret_1d"]]
    vix_move = vix["ret_1d"] if vix is not None else 0.0
    if all(m > 0 for m in moves) and vix_move <= 0:
        verdict = "risk-on: everything up and volatility falling"
    elif all(m < 0 for m in moves) and vix_move >= 0:
        verdict = "risk-off: everything down and volatility rising"
    elif abs(vix_move) < CALM_VIX_MOVE:
        verdict = "mixed, no strong signal from volatility"
    else:
        verdict = "mixed, with volatility " + ("rising" if vix_move > 0 else "falling")
    return "The tape: " + " · ".join(parts) + f" → {verdict}."


def strongest_theme(themes: pd.DataFrame) -> str | None:
    if themes.empty:
        return None
    top = themes.iloc[0]
    if top["rel_1m"] <= 0:
        return (f"No theme beat SPY this month. The least bad is {top['name']} ({pct(top['rel_1m'])} vs SPY). "
                f"Defensive tape: cash is a position.")
    if top["breadth"] >= BROAD_BREADTH:
        quality = f"with {pct(top['breadth'], False).replace(".0%", "%")} of its names beating SPY. Broad moves like this are the healthy kind"
    elif top["breadth"] <= NARROW_BREADTH:
        quality = f"but only {pct(top['breadth'], False).replace(".0%", "%")} of its names beat SPY. A few names carry it, so it is fragile"
    else:
        quality = f"with {pct(top['breadth'], False).replace(".0%", "%")} of its names beating SPY"
    return (f"{top['name']} is the strongest theme, {pct(top['rel_1m'])} vs SPY over a month, {quality}. "
            f"Names: {', '.join(top['leaders'])}.")


def leader_fading(themes: pd.DataFrame) -> str | None:
    """A theme other than the strongest that is up on the month but rolling over now."""
    rest = themes.iloc[1:]
    fading = rest[(rest["rel_1m"] > 0) & (rest["trend"] == "fading") & (rest["today"] < 0)]
    if fading.empty:
        return None
    row = fading.iloc[0]
    return (f"{row['name']} is still up {pct(row['rel_1m'])} on the month vs SPY but fading now "
            f"({pct(row['rel_1w'])} this week, {pct(row['today'])} today). If you hold it, protect gains before adding. "
            f"That means {', '.join(row['leaders'])}.")


def laggard(themes: pd.DataFrame) -> str | None:
    if len(themes) < 2:
        return None
    row = themes.iloc[-1]
    if row["rel_1w"] < 0:
        return (f"{row['name']} stays in the penalty box: {pct(row['rel_1m'])} vs SPY on the month and still weak this week "
                f"({pct(row['rel_1w'])}). Nothing to do until buyers show up.")
    return (f"{row['name']} is the month's weakest theme ({pct(row['rel_1m'])} vs SPY) but bounced this week "
            f"({pct(row['rel_1w'])}). Early, not confirmed.")


def caution(scored: pd.DataFrame, watchlist: set[str]) -> str | None:
    hedged = scored[scored["bucket"] == "Hedged Rally"]
    if hedged.empty:
        return None
    mine = hedged[hedged["symbol"].isin(watchlist)]
    pool = mine if not mine.empty else hedged.nlargest(20, "dvol_21")
    row = pool.sort_values("skew", ascending=False).iloc[0]
    where = "on your watchlist" if not mine.empty else "among the most traded names"
    return (f"Caution flag {where}: {row['symbol']} is up {pct(row['ret_1m'])} on the month while someone pays heavily "
            f"for crash protection (skew {pct(row['skew'], False)}). If you're long, tighten stops. That's insurance "
            f"buying, not enthusiasm.")


def money_flow(sectors: pd.DataFrame) -> str | None:
    if sectors.empty:
        return None
    into = sectors.loc[sectors["flow_bps"].idxmax()]
    out = sectors.loc[sectors["flow_bps"].idxmin()]
    return (f"Big-picture tide: trading dollars moved toward {into['name']} this week ({into['flow_bps']:+.1f} bps of "
            f"the whole market's volume) and away from {out['name']} ({out['flow_bps']:+.1f} bps).")


def off_high(closes: pd.Series) -> float | None:
    """Last close vs the highest close in the series (zero or negative), None when there are no closes."""
    series = closes.dropna()
    return None if series.empty else float(series.iloc[-1] / series.max() - 1)


def _moved(value: float) -> str:
    return f"up {value * 100:.1f}%" if value >= 0 else f"down {abs(value) * 100:.1f}%"


def rotation_read(indexes: dict, sectors: pd.DataFrame) -> str | None:
    """Is the market narrow? SPY vs equal-weight RSP over a month, sectors beating SPY, SPY vs its 52-week high.
    Each part is left out when its data is missing."""
    spy, rsp = indexes.get("SPY") or {}, indexes.get("RSP") or {}
    parts = []
    if "ret_1m" in spy and "ret_1m" in rsp:
        gap = spy["ret_1m"] - rsp["ret_1m"]
        if gap >= ROTATION_GAP:
            parts.append(f"The S&P is {_moved(spy['ret_1m'])} on the month while the average stock is {_moved(rsp['ret_1m'])}: "
                         "gains are narrow, money is rotating.")
        elif -gap >= ROTATION_GAP:
            parts.append(f"The average stock is {_moved(rsp['ret_1m'])} on the month while the S&P is {_moved(spy['ret_1m'])}: "
                         "the broad market is holding up better than the big names.")
    if len(sectors):
        beat = int((sectors["rel_1m"] > 0).sum())
        text = f"{beat} of {len(sectors)} sectors beat SPY this month"
        if "ret_1m" in spy:  # a sector's own return is its gap to SPY plus SPY's return: "beat SPY" and "up" are different questions
            text += f", and {int((sectors['rel_1m'] + spy['ret_1m'] > 0).sum())} of {len(sectors)} are up outright"
        parts.append(text + ".")
    high = spy.get("off_high")
    if high is not None:
        parts.append("SPY is at its 52-week high." if high > -AT_HIGH else f"SPY is {pct(-high, False)} below its 52-week high.")
    return " ".join(parts) or None


def todays_read(indexes: dict, themes: pd.DataFrame, sectors: pd.DataFrame, scored: pd.DataFrame,
                watchlist: set[str]) -> list[str]:
    lines = [tape(indexes), rotation_read(indexes, sectors), strongest_theme(themes), leader_fading(themes), laggard(themes),
             caution(scored, watchlist), money_flow(sectors)]
    return [line for line in lines if line]
