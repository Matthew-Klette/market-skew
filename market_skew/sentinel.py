"""The Quality score: a company's fundamentals and price, scored out of 100 following a popular public checklist. Pure: no files, no network.

Four pillars (points in brackets; every rule is in the "How it works" page):
  growing   /35  sales growth 12, speeding up vs a year ago 9, free cash per share growth 8, not diluting 6
  protected /25  gross margin 8, free cash margin 8, margin rank in its sector 5, capex vs operating cash flow 4
  survive   /25  net cash vs debt 10, debt vs free cash 9, free cash is positive 6
  street    /15  "Market's view (proxy)": 3-month price vs its sector 8, options positioning (bet_z) 7
A part whose number is missing is left out and the pillar is scaled up from the parts that are known (a pillar with
under 40% of its points known scores 0 and the company is marked as having gaps). Price checks sit beside the score and are not part of the 100.
"""
from statistics import median

TREASURY_10Y = 0.043   # approx. 10-year US Treasury yield, the bar a cash yield is held against; edit here
WATCH_AT, OK_AT = 80, 65   # our labels: WATCH >= 80, OK 65-79, PASS below
ALONE_PP = 0.05            # a 1-month move this far from its sector's median is "alone", otherwise "with sector"
CHEAP, RICH = -0.10, 0.10  # vs own history / sector peers: beyond 10% either way
MIN_PEERS = 5
MIN_KNOWN = 0.4            # a pillar needs this share of its points to be knowable, else it scores 0 and is listed as a gap
PILLARS = (("growing", "Is the business growing?", 35), ("protected", "How protected is it?", 25),
           ("survive", "Can it survive being wrong?", 25), ("street", "Market's view (proxy)", 15))
SHORT = {"growing": "growth", "protected": "margins", "survive": "balance sheet", "street": "market view"}


def label(score: int) -> str:
    return "WATCH" if score >= WATCH_AT else "OK" if score >= OK_AT else "PASS"


def _scale(x, zero, full, points):
    """0 points at `zero`, all of them at `full`, straight line between, clamped (works downwards too)."""
    if x is None:
        return None
    return max(0.0, min(1.0, (x - zero) / (full - zero))) * points


def _part(key, text, pts, top):
    return {"key": key, "label": text, "pts": None if pts is None else round(pts, 1), "max": top}


def _pillar(parts, cap):
    known = sum(p["max"] for p in parts if p["pts"] is not None)
    earned = sum(p["pts"] for p in parts if p["pts"] is not None)
    return round(earned / known * cap) if known and known >= cap * MIN_KNOWN else 0


def _known(parts, cap):
    return sum(p["max"] for p in parts if p["pts"] is not None) >= cap * MIN_KNOWN


def _med(values, least=3):
    values = [v for v in values if v is not None]
    return median(values) if len(values) >= least else None


def _band(value):
    return None if value is None else "cheap" if value <= CHEAP else "rich" if value >= RICH else "fair"


def _pfcf(m, x):
    fcf, shares, close = m.get("fcf"), m.get("shares"), x.get("close")
    return close / (fcf / shares) if fcf and fcf > 0 and shares and close else None


def _history(m, x):
    out = []
    for year, close in sorted((x.get("year_closes") or {}).items()):
        per_share = (m.get("fcf_ps_by_year") or {}).get(year)
        if per_share and per_share > 0 and close:
            out.append({"year": year, "pfcf": close / per_share})
    return out


def _rank_in_sector(symbol, margin, sector, margins):
    others = [v for k, (sec, v) in margins.items() if sec == sector and k != symbol and v is not None]
    if margin is None or len(others) + 1 < MIN_PEERS:
        return None
    return (sum(v < margin for v in others) + 0.5 * sum(v == margin for v in others)) / len(others)


def _net_cash_points(m):
    cash, revenue = m.get("net_cash"), m.get("ttm_revenue")
    if cash is None:
        return None
    if cash >= 0:
        return 10.0
    return _scale(-cash / revenue, 0.5, 0.0, 10) if revenue else None


def _debt_points(m):
    fcf, ratio = m.get("fcf"), m.get("debt_to_fcf")
    if fcf is None:
        return None
    return 0.0 if fcf <= 0 else _scale(ratio, 6, 1, 9)


def _capex_points(m):
    ocf, capex = m.get("ocf"), m.get("capex")
    if ocf is None or capex is None:
        return None
    return 0.0 if ocf <= 0 else _scale(capex / ocf, 1.0, 0.5, 4)


def _flags(m):
    flags = []
    ocf, capex = m.get("ocf"), m.get("capex")
    if ocf is not None and capex is not None and capex > ocf:
        flags.append("Spending more than it makes: capex is above operating cash flow.")
    if (m.get("fcf") or 0) < 0:
        flags.append("Burning cash: free cash flow is negative.")
    if (m.get("share_change") or 0) > 0.03:
        flags.append(f"Diluting: share count up {m['share_change'] * 100:.0f}% in a year.")
    if (m.get("net_cash") or 0) < 0:
        flags.append("Debt is larger than cash.")
    return flags


def _summary(r):
    """The four-sentence 'Read this first', written by fixed rules from the numbers only."""
    m, g, prior = r["metrics"], r["growth"], r["growth_prior"]
    cents = None if m.get("fcf_margin") is None else m["fcf_margin"] * 100
    quality = "QUALITY: " + (f"sales grew {g * 100:.0f}% over the year" if g is not None else "sales growth is unknown")
    quality += f"; it keeps {cents:.0f} cents of every $1 of sales as free cash." if cents is not None else "; free cash is unknown."
    if g is None or prior is None:
        direction = "DIRECTION: not enough years of sales to say whether growth is speeding up or slowing."
    else:
        direction = f"DIRECTION: growth is {'speeding up' if r['accelerating'] else 'slowing'} ({g * 100:.0f}% now against {prior * 100:.0f}% a year ago)."
        if (m.get("share_change") or 0) > 0.03:
            direction = direction[:-1] + f", and the share count is up {m['share_change'] * 100:.0f}%."
    own = r["own_history_pct"]
    price = "PRICE: " + (f"a {r['cash_yield'] * 100:.1f}% cash yield against {TREASURY_10Y * 100:.1f}% on 10-year Treasuries"
                         if r["cash_yield"] is not None else "no cash yield (free cash or market value unknown)")
    price += f"; {abs(own) * 100:.0f}% {'cheaper' if own < 0 else 'richer'} than its own history." if own is not None else "; no price history to compare."
    weakest = min(r["pillars"].items(), key=lambda kv: kv[1]["pts"] / kv[1]["max"])[0]
    bet = (f"THE BET: {r['score']} out of 100 ({r['label']}), weakest on {SHORT[weakest]}. "
           "It says whether the company is attractive, not when to buy.")
    return [quality, direction, price, bet]


def _context(fundamentals, prices):
    margins = {k: ((prices.get(k) or {}).get("sector"), m.get("fcf_margin")) for k, m in fundamentals.items()}
    by_sector = {}
    for x in prices.values():
        by_sector.setdefault(x.get("sector"), []).append(x)
    moves = {sec: {k: _med([x.get(k) for x in xs]) for k in ("ret_1m", "ret_3m")} for sec, xs in by_sector.items()}
    pfcf = {}
    for k, m in fundamentals.items():
        value = _pfcf(m, prices.get(k) or {})
        if value:
            pfcf.setdefault((prices.get(k) or {}).get("sector"), []).append(value)
    return margins, moves, {sec: _med(v) for sec, v in pfcf.items()}


def _groups(m, x, rank, diff_3m):
    g, prior = m.get("revenue_growth"), m.get("revenue_growth_prior")
    speed = None if g is None or prior is None else g - prior
    return {
        "growing": [_part("growth", "Sales growth", _scale(g, 0, 0.25, 12), 12),
                    _part("accel", "Speeding up vs a year ago", _scale(speed, -0.10, 0.10, 9), 9),
                    _part("fcf_ps", "Free cash per share growth", _scale(m.get("fcf_per_share_growth"), 0, 0.20, 8), 8),
                    _part("dilution", "Not diluting", _scale(m.get("share_change"), 0.05, -0.025, 6), 6)],
        "protected": [_part("gross", "Gross margin", _scale(m.get("gross_margin"), 0, 0.60, 8), 8),
                      _part("fcf_margin", "Free cash margin", _scale(m.get("fcf_margin"), 0, 0.25, 8), 8),
                      _part("sector_rank", "Margin rank in sector", None if rank is None else rank * 5, 5),
                      _part("capex", "Capex vs operating cash", _capex_points(m), 4)],
        "survive": [_part("net_cash", "Net cash vs debt", _net_cash_points(m), 10),
                    _part("debt_fcf", "Debt vs free cash", _debt_points(m), 9),
                    _part("fcf_positive", "Free cash is positive", None if m.get("fcf") is None else (6.0 if m["fcf"] > 0 else 0.0), 6)],
        "street": [_part("momentum", "3-month price vs sector", _scale(diff_3m, -0.10, 0.10, 8), 8),
                   _part("bets", "Options positioning", _scale(x.get("bet_z"), -3, 3, 7), 7)],
    }


def _one(symbol, m, x, margins, moves, sector_pfcf, previous):
    sector = x.get("sector")
    g, prior = m.get("revenue_growth"), m.get("revenue_growth_prior")
    move = moves.get(sector) or {}
    diff_3m = None if x.get("ret_3m") is None or move.get("ret_3m") is None else x["ret_3m"] - move["ret_3m"]
    groups = _groups(m, x, _rank_in_sector(symbol, m.get("fcf_margin"), sector, margins), diff_3m)
    pillars = {key: {"label": text, "max": cap, "pts": _pillar(groups[key], cap), "parts": groups[key], "known": _known(groups[key], cap)}
               for key, text, cap in PILLARS}
    gaps = [SHORT[k] for k, p in pillars.items() if not p["known"]]
    score = sum(p["pts"] for p in pillars.values())
    pfcf = _pfcf(m, x)
    mcap = x.get("market_cap") or (x["close"] * m["shares"] if x.get("close") and m.get("shares") else None)
    cash_yield = m["fcf"] / mcap if m.get("fcf") is not None and mcap else None
    history = _history(m, x)
    typical = _med([h["pfcf"] for h in history])
    own = pfcf / typical - 1 if pfcf and typical else None
    peer = pfcf / sector_pfcf[sector] - 1 if pfcf and sector_pfcf.get(sector) else None
    peg = pfcf / (g * 100) if pfcf and g and g > 0 else None
    gap = None if x.get("ret_1m") is None or move.get("ret_1m") is None else x["ret_1m"] - move["ret_1m"]
    prev = (previous or {}).get(symbol)
    depth = m.get("depth") or "Thin"
    row = {
        "symbol": symbol, "name": x.get("name") or symbol, "sector": sector or "Unclassified", "market_cap": mcap, "score": score,
        "label": label(score), "change": None if prev is None else score - prev, "depth": depth, "thin": depth == "Thin", "gaps": gaps,
        "as_of": m.get("as_of"), "pillars": pillars, "metrics": m, "growth": g, "growth_prior": prior,
        "accelerating": None if g is None or prior is None else g > prior,
        "cash_yield": cash_yield, "treasury": TREASURY_10Y, "beats_treasury": None if cash_yield is None else cash_yield >= TREASURY_10Y,
        "pfcf": pfcf, "peg": peg, "peg_label": None if peg is None else "cheap" if peg <= 1 else "fair" if peg <= 2 else "rich",
        "history": history, "median_pfcf": typical, "own_history_pct": own, "own_history_label": _band(own),
        "peer_pct": peer, "peer_label": _band(peer), "vs_sector_1m": gap,
        "together": None if gap is None else f"alone {gap * 100:+.0f}pp" if abs(gap) >= ALONE_PP else "with sector",
        "flags": _flags(m), "ret_1m": x.get("ret_1m"), "bucket": x.get("bucket"),
        "px": {k: x.get(k) for k in ("name", "sector", "market_cap", "close", "ret_1m", "ret_3m", "bet_z", "bucket", "year_closes")},
    }
    return {**row, "summary": _summary(row)}


def score_all(fundamentals: dict[str, dict], prices: dict[str, dict], previous: dict[str, float] | None = None) -> list[dict]:
    """fundamentals: symbol -> metrics (fundamentals.compute). prices: symbol -> {name, sector, market_cap, close, ret_1m, ret_3m,
    bet_z, bucket, year_closes} for the whole universe (sector medians use all of it). previous: symbol -> last stored score.
    Returns one ranked row per company that has numbers, best first."""
    margins, moves, sector_pfcf = _context(fundamentals, prices)
    rows = [_one(k, m, prices.get(k) or {}, margins, moves, sector_pfcf, previous) for k, m in fundamentals.items() if m]
    rows.sort(key=lambda r: (-r["score"], r["symbol"]))
    return [{**r, "rank": i} for i, r in enumerate(rows, 1)]
