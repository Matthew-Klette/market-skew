"""Drift against sleeve targets, and where this month's money should go. Pure: no network, no disk.

Ported and simplified from JoelLewis/finance_skills (MIT) rebalancing.py: DriftAnalyzer.compute_drift and
cash_flow_rebalance (numpy removed, plain Python). Changes: sleeves instead of single assets, targets that are a floor
("broad") or a ceiling (growth, single stocks), and a tilt helper for allocation.py. Never sells.
"""
DRIFT_NOTE_PP = 0.05
SLEEVES = ("broad", "growth", "stock")
SLEEVE_NAMES = {"broad": "Broad ETFs (S&P 500 and dividend)", "growth": "Growth funds (Nasdaq and growth)", "stock": "Single stocks"}
SLEEVE_FUNDS = {"broad": "VOO, SCHD, SYG500", "growth": "QQQ, STXNDQ, VOOG", "stock": "your Picks"}
KINDS = {"broad": "min", "growth": "max", "stock": "max"}  # at least / at most
DEFAULT_TARGETS = {"broad": 0.70, "growth": 0.20, "stock": 0.10}
FUND_SLEEVE = {"VOO": "broad", "SYG500": "broad", "SCHD": "broad", "QQQ": "growth", "STXNDQ": "growth", "VOOG": "growth"}
ETFS = tuple(FUND_SLEEVE)  # every fund counts as an ETF here; single stocks do not
ETF_RULE_LOW, ETF_RULE_HIGH = 0.70, 0.75  # "a common rule of thumb": 70 to 75% of holdings in ETFs


def etf_share(vals: list[dict]) -> dict | None:
    """ETF share of the valued holdings against the 70 to 75% rule of thumb: {share, etf, total, status low/ok/high}; None when
    nothing is valued."""
    total = sum(v["rand"] for v in vals if v.get("rand"))
    if not total:
        return None
    etf = sum(v["rand"] for v in vals if v.get("rand") and v["symbol"] in ETFS)
    share = etf / total
    status = "low" if share < ETF_RULE_LOW - 1e-9 else "high" if share > ETF_RULE_HIGH + 1e-9 else "ok"
    return {"share": share, "etf": etf, "total": total, "status": status}


def sleeve_of(symbol: str) -> str:
    return FUND_SLEEVE.get(symbol, "stock")


def values(holdings: list[dict], closes: dict, quotes: dict, rate: float | None) -> list[dict]:
    """Rand value per holding from cached prices only: US closes in dollars times the cached rate, JSE quotes in rand.
    `rand` is None when units or a price (or the rate) is missing."""
    out = []
    for h in holdings:
        units = h.get("units")
        if h["account"] == "tfsa":
            price, fx = (quotes.get(h["symbol"]) or {}).get("price"), 1.0
        else:
            price, fx = closes.get(h["symbol"]), rate
        rand = units * price * fx if units is not None and price and fx else None
        out.append({"symbol": h["symbol"], "account": h["account"], "units": units, "price": price,
                    "rand": rand, "sleeve": sleeve_of(h["symbol"])})
    return out


def sleeve_values(vals: list[dict]) -> dict:
    totals = {s: 0.0 for s in SLEEVES}
    for v in vals:
        if v["rand"]:
            totals[v["sleeve"]] += v["rand"]
    return totals


def weights(vals: list[dict]) -> dict:
    """{"total": rand, "weights": sleeve -> share} (weights empty when nothing is valued)."""
    totals = sleeve_values(vals)
    total = sum(totals.values())
    return {"total": total, "values": totals, "weights": {s: x / total for s, x in totals.items()} if total else {}}


def drift(actual: dict, targets: dict) -> list[dict]:
    """Actual minus target per sleeve. A floor sleeve is under when below its target; a ceiling sleeve is over above it."""
    out = []
    for s in SLEEVES:
        d = actual.get(s, 0.0) - targets[s]
        state = "under" if KINDS[s] == "min" and d < 0 else "over" if KINDS[s] == "max" and d > 0 else "ok"
        out.append({"sleeve": s, "actual": actual.get(s, 0.0), "target": targets[s], "drift": d, "state": state, "kind": KINDS[s]})
    return out


def cash_flow(sleeve_rand: dict, targets: dict, cash: float) -> list[dict]:
    """Share `cash` across sleeves, most underweight first, never selling (JoelLewis cash_flow_rebalance)."""
    cash = max(float(cash), 0.0)
    total = sum(sleeve_rand.values()) + cash
    short = {s: max(targets[s] * total - sleeve_rand.get(s, 0.0), 0.0) for s in SLEEVES}
    need = sum(short.values())
    if need == 0:
        alloc = {s: targets[s] * cash for s in SLEEVES}
    elif need <= cash:
        alloc = {s: short[s] + targets[s] * (cash - need) for s in SLEEVES}
    else:
        alloc = {s: short[s] * cash / need for s in SLEEVES}
    return [{"sleeve": s, "rand": alloc[s]} for s in sorted(SLEEVES, key=lambda s: -alloc[s]) if alloc[s] > 0.01]


def _large(rows: list[dict]) -> dict:
    return {r["sleeve"]: r for r in rows if r["state"] != "ok" and abs(r["drift"]) > DRIFT_NOTE_PP}


def note(rows: list[dict]) -> str | None:
    """One plain line for the Picks plan when a sleeve is more than 5 points off, else None."""
    big = _large(rows)
    if "growth" in big and big["growth"]["state"] == "over":
        return f"Your growth funds are {big['growth']['drift'] * 100:.0f}pp over target: this month's plan leans to VOO and SCHD."
    if "broad" in big:
        return f"Your broad ETFs are {abs(big['broad']['drift']) * 100:.0f}pp under target: this month's plan leans to VOO and SCHD."
    return None


def tilt(rows: list[dict]) -> dict:
    """Weight multipliers for allocation.allocate's three funds; empty (no change) unless a sleeve is over 5 points off."""
    big = _large(rows)
    out = {}
    if "growth" in big and big["growth"]["state"] == "over":
        out["QQQ"] = 0.5
    if "broad" in big or ("growth" in big and big["growth"]["state"] == "over"):
        out.update({"VOO": 1.5, "SCHD": 1.5})
    return out


def clean_targets(values) -> dict | None:
    """Targets as whole-ish percentages (e.g. {"broad": 70, ...}) -> shares, or None unless each is 0-100 and they sum to 100."""
    if not isinstance(values, dict):
        return None
    out = {}
    for s in SLEEVES:
        raw = values.get(s)
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return None
        try:
            pct = float(raw)
        except ValueError:
            return None
        if not 0 <= pct <= 100:
            return None
        out[s] = pct / 100
    return out if abs(sum(out.values()) - 1) < 1e-6 else None


def targets_from(prefs: dict) -> dict:
    saved = clean_targets({k: v * 100 for k, v in (prefs.get("targets") or {}).items() if isinstance(v, (int, float))}) \
        if isinstance(prefs.get("targets"), dict) else None
    return saved or dict(DEFAULT_TARGETS)
