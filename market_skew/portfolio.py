"""The user's mix as weights over the six funds with history, one monthly return series for it, and what it costs to add to.
Pure: no network, no disk. Single stocks have no history here, so they are modelled as QQQ (said on the page)."""
from . import costs, history

SLEEVE_FUNDS = {"broad": ("VOO", "SCHD", "SYG500"), "growth": ("QQQ", "STXNDQ"), "stock": ("QQQ",)}
STOCK_AS = "QQQ"


def target_weights(targets: dict) -> dict[str, float]:
    """Sleeve targets split evenly over each sleeve's funds."""
    out: dict[str, float] = {}
    for sleeve, funds in SLEEVE_FUNDS.items():
        for f in funds:
            out[f] = out.get(f, 0.0) + targets.get(sleeve, 0.0) / len(funds)
    return {f: w for f, w in out.items() if w > 0}


def holding_weights(vals: list[dict]) -> dict[str, float]:
    """Rand values per holding -> weights over funds (other tickers count as QQQ); empty when nothing is valued."""
    out: dict[str, float] = {}
    for v in vals:
        if v.get("rand"):
            f = v["symbol"] if v["symbol"] in history.FUNDS else STOCK_AS
            out[f] = out.get(f, 0.0) + v["rand"]
    total = sum(out.values())
    return {f: x / total for f, x in out.items()} if total else {}


def series(returns: dict, weights: dict) -> list[tuple[str, float]]:
    """Month-by-month return of the mix (rebalanced monthly), over the months every weighted fund has."""
    if not weights:
        return []
    months = set.intersection(*(set(returns.get(f) or {}) for f in weights))
    return [(m, sum(w * returns[f][m] for f, w in weights.items())) for m in sorted(months)]


def fee_pct(weights: dict) -> float:
    """Share of each new rand lost to fees: JSE path for SYG500 and STXNDQ, rand-to-dollar plus US buy for the rest."""
    jse, usd = costs.tfsa_line(1.0)["fee_pct"], costs.usd_line(1.0)["fee_pct"]
    return sum(w * (jse if f in history.JSE else usd) for f, w in weights.items())
