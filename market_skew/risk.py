"""What a bad year looks like, from history only (not a bell curve, because bad months come in clumps). Pure.

Historical VaR 95% and max drawdown follow JoelLewis/finance_skills (MIT), plugins/wealth-management/skills/historical-risk/
scripts/historical_risk.py (HistoricalRiskAnalyzer.historical_var, max_drawdown); CVaR, worst 12 months and the stress replays are
ours. `series` is [(month "YYYY-MM", monthly return in rand)] for the user's mix, oldest first."""
import numpy as np

MIN_MONTHS = 12
STRESS = (("Jan to Oct 2022", "2022-01", "2022-10"), ("March 2020", "2020-03", "2020-03"))


def _compound(returns) -> float:
    return float(np.prod(1.0 + np.asarray(list(returns), dtype=float)) - 1.0)


def _drawdown(months: list[str], rets: np.ndarray) -> dict:
    cumulative = np.cumprod(1.0 + rets)
    peaks = np.maximum.accumulate(cumulative)
    down = cumulative / peaks - 1.0
    trough = int(np.argmin(down))
    peak = int(np.argmax(cumulative[:trough + 1]))
    back = next((i for i in range(trough + 1, len(cumulative)) if cumulative[i] >= cumulative[peak]), None)
    return {"depth": float(-down[trough]), "peak": months[peak], "trough": months[trough],
            "recovered": None if back is None else months[back],
            "months_to_recover": None if back is None else back - trough, "months_underwater": None if back is None else back - peak}


def analyse(series: list[tuple[str, float]], value: float, windows=STRESS) -> dict | None:
    """Rand amounts on `value`. None when there is under two years of history."""
    if len(series) < MIN_MONTHS:
        return None
    months, rets = [m for m, _ in series], np.array([r for _, r in series], dtype=float)
    cut = float(np.percentile(rets, 5))
    var, cvar = -cut, -float(rets[rets <= cut].mean())
    worst = int(np.argmin(rets))
    rolling = [_compound(rets[i:i + 12]) for i in range(len(rets) - 11)]
    w12 = int(np.argmin(rolling)) if rolling else None
    stress = []
    for label, first, last in windows:
        inside = [r for m, r in series if first <= m <= last]
        if len(inside) == _span(first, last):
            stress.append({"label": label, "pct": _compound(inside), "rand": _compound(inside) * value})
    return {"months": len(series), "from": months[0], "to": months[-1],
            "var": {"pct": var, "rand": var * value}, "cvar": {"pct": cvar, "rand": cvar * value},
            "worst_month": {"month": months[worst], "pct": float(rets[worst]), "rand": float(rets[worst]) * value},
            "worst_12": None if w12 is None else {"from": months[w12], "to": months[w12 + 11], "pct": rolling[w12], "rand": rolling[w12] * value},
            "drawdown": _drawdown(months, rets), "stress": stress}


def _span(first: str, last: str) -> int:
    return (int(last[:4]) - int(first[:4])) * 12 + int(last[5:7]) - int(first[5:7]) + 1
