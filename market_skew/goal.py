"""Will I get there? Bootstrap Monte Carlo over the user's own monthly rand returns. Pure: no network, no disk.

The plain future-value formula is ported from JoelLewis/finance_skills (MIT), plugins/wealth-management/skills/savings-goals/
scripts/savings_goals.py (SavingsGoals.future_value_with_contributions). The rest is ours: 5,000 paths that resample whole
calendar months in 12-month blocks (keeps some of the way good and bad months cluster), contributions added at the start of each
month after fees and left flat in rand, everything shown in today's rand by taking off a constant inflation rate. Past returns,
resampled: not a forecast."""
import math

import numpy as np

PATHS, BLOCK, MIN_MONTHS = 5000, 12, 24
INFLATION = 0.045  # South African CPI is ~4.5% a year as an assumption; editable on the page
STEADY = 0.07
MAX_YEARS = 40
CAUTIOUS_PP = 5.0  # percentage points a year taken off every resampled month: the past decade ran ~16%/yr in rand, unusually high
CAUTIOUS_MONTHLY = CAUTIOUS_PP / 100 / 12


def fv_steady(start: float, monthly: float, annual: float, years: int) -> float:
    """FV = PV(1+r)^n + PMT * ((1+r)^n - 1) / r with a monthly rate r = annual / 12 (savings_goals.py)."""
    r, n = annual / 12.0, years * 12
    lump = start * (1.0 + r) ** n
    return lump + (monthly * n if r == 0 else monthly * ((1.0 + r) ** n - 1.0) / r)


def deflate(value, inflation: float, months: int):
    """Money `months` from now in today's rand."""
    return value / (1.0 + inflation) ** (months / 12.0)


def _sample(returns: np.ndarray, months: int, paths: int, rng: np.random.Generator) -> np.ndarray:
    """paths x months of returns: runs of BLOCK consecutive months from random starting points, cut to length."""
    blocks = math.ceil(months / BLOCK)
    starts = rng.integers(0, len(returns) - BLOCK + 1, size=(paths, blocks))
    index = (starts[:, :, None] + np.arange(BLOCK)).reshape(paths, -1)[:, :months]
    return returns[index]


def simulate(returns: list[float], years: int, start: float, monthly: float, fee: float, inflation: float,
             target: float, paths: int = PATHS, seed: int | None = None, haircut: float = 0.0) -> dict | None:
    """10/50/90 of the value in today's rand at every year end, the same at the end, and the share of paths that reach `target`
    (in today's rand). `haircut` is taken off every resampled monthly return before compounding (CAUTIOUS_MONTHLY for the cautious
    view): the spread and the 12-month blocks are untouched. `median_path` is the median at every month, for milestone dates.
    None when there is under two years of history. The same seed gives the same answer."""
    if len(returns) < MIN_MONTHS:
        return None
    months = years * 12
    sample = _sample(np.asarray(returns, dtype=float), months, paths, np.random.default_rng(seed)) - haircut
    value, net = np.full(paths, float(start)), monthly * (1.0 - fee)
    marks = {m: None for m in range(0, months + 1, 12)}
    marks[0] = value.copy()
    median = [float(np.median(value))]
    for m in range(months):
        value = (value + net) * (1.0 + sample[:, m])
        median.append(float(np.median(deflate(value, inflation, m + 1))))
        if m + 1 in marks:
            marks[m + 1] = value.copy()
    fan = {"years": list(range(years + 1))}
    for key, q in (("p10", 10), ("p50", 50), ("p90", 90)):
        fan[key] = [float(np.percentile(deflate(marks[m], inflation, m), q)) for m in marks]
    real_final = deflate(value, inflation, months)
    return {"fan": fan, "final": {k: fan[k][-1] for k in ("p10", "p50", "p90")}, "prob": float(np.mean(real_final >= target)),
            "net_monthly": net, "paths": paths, "months": months, "median_path": median}


def clean(values) -> dict | None:
    """Goal inputs typed on the page -> target (rand), years (1-40), optional start, monthly (rand), inflation (percent in, share out)
    and the tick for the user's actual split. Blank fields are left out; None when a value is not a number in range."""
    if not isinstance(values, dict):
        return None
    out = {}
    for key, low, high in (("target", 1.0, 1e10), ("years", 1, MAX_YEARS), ("start", 0.0, 1e10), ("monthly", 0.0, 1e9), ("inflation", 0.0, 20.0)):
        raw = values.get(key)
        if raw in (None, ""):
            if key in ("target", "years"):
                return None
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return None
        try:
            number = float(raw)
        except ValueError:
            return None
        if not math.isfinite(number) or not low <= number <= high:
            return None
        out[key] = int(number) if key == "years" else number / 100 if key == "inflation" else number
    if out["years"] != float(values["years"]):
        return None
    out["actual"] = values.get("actual") is True or values.get("actual") == "true"
    return out
