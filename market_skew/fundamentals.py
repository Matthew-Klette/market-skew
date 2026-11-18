"""Company numbers from SEC XBRL frames, as pure functions: no network, no files.

Input is one company's series, {"q": {metric: {"2025Q3": value}}, "a": {metric: {"2025": value}}, "i": {...}} (see
edgar.company_series). Flow metrics (revenue, gross profit, cash flow, diluted shares) come as 3-month and annual values;
instants (cash, debt, shares outstanding) come per quarter end. Companies tag things differently, so every figure is
None when its inputs are missing; nothing here raises on a sparse company."""
import re

FLOW = ("revenue", "gross", "ocf", "capex", "shares_avg")
INSTANT = ("cash", "debt", "shares_out")
_LABEL = re.compile(r"^(\d{4})Q([1-4])$")


def qindex(label: str) -> int:
    year, quarter = _LABEL.match(label).groups()
    return int(year) * 4 + int(quarter) - 1


def qlabel(index: int) -> str:
    return f"{index // 4}Q{index % 4 + 1}"


def _num(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _quarters(series: dict, annual: dict, additive: bool = True) -> dict[int, float]:
    """Quarter index -> value, with a missing Q4 derived as the year minus Q1..Q3 (10-Ks carry no Q4 filing).
    additive=False (share averages: a yearly average is not the sum of its quarters) never derives a Q4, and counts must be > 0."""
    out = {qindex(label): v for label, v in series.items() if _LABEL.match(label) and _num(v) is not None and (additive or v > 0)}
    for year, total in (annual.items() if additive else ()):
        year, total = int(year), _num(total)
        base = year * 4
        if total is not None and base + 3 not in out and all(base + n in out for n in range(3)):
            out[base + 3] = total - sum(out[base + n] for n in range(3))
    return out


def _window(quarters: dict[int, float], end: int, count: int = 4) -> float | None:
    values = [quarters.get(end - n) for n in range(count)]
    return None if any(v is None for v in values) else sum(values)


def _ratio(a, b):
    return None if a is None or b is None or b == 0 else a / b


def _growth(now, before):
    return None if now is None or before is None or before <= 0 else now / before - 1


def _annual_flow(data: dict, metric: str) -> dict[int, float]:
    return {int(y): float(v) for y, v in data["a"].get(metric, {}).items() if _num(v) is not None}


def _fcf_by_year(data: dict) -> dict[int, float]:
    ocf, capex = _annual_flow(data, "ocf"), _annual_flow(data, "capex")
    return {y: ocf[y] - capex[y] for y in sorted(ocf) if y in capex}


def _ttm_flow(data: dict, quarters: dict[str, dict[int, float]], end: int, metric: str) -> float | None:
    return _window(quarters[metric], end)


def _ttm_cash(data: dict, quarters: dict, end: int) -> tuple[float | None, float | None, int | None]:
    """Four quarters of operating cash flow and capex; most filers only tag cash flow yearly, so fall back to the
    latest completed fiscal year (both pieces from the same basis). The third value is that fiscal year, None for four quarters."""
    ocf, capex = _window(quarters["ocf"], end), _window(quarters["capex"], end)
    if ocf is not None and capex is not None:
        return ocf, capex, None
    annual_ocf, annual_capex = _annual_flow(data, "ocf"), _annual_flow(data, "capex")
    year = end // 4 if end % 4 == 3 else end // 4 - 1
    usable = [y for y in annual_ocf if y in annual_capex and y <= year]
    return (annual_ocf[max(usable)], annual_capex[max(usable)], max(usable)) if usable else (None, None, None)


def _shares(data: dict, quarters: dict, index: int) -> float | None:
    out = _num(data["i"].get("shares_out", {}).get(qlabel(index)))
    return out if out is not None and out > 0 else quarters["shares_avg"].get(index)


def _fcf_ps_by_year(data: dict, quarters: dict, by_year: dict[int, float]) -> dict[int, float]:
    """Free cash per share for each fiscal year (shares: that year's average of what is reported)."""
    out = {}
    for year, fcf in by_year.items():
        counts = [s for s in (_shares(data, quarters, year * 4 + n) for n in range(4)) if s and s > 0]
        if counts:
            out[year] = fcf / (sum(counts) / len(counts))
    return out


def _per_share_growth(per_share: dict[int, float]) -> float | None:
    """Free cash per share, last fiscal year against the one before."""
    years = sorted(per_share)
    if len(years) < 2 or years[-1] - years[-2] != 1:
        return None
    now, before = per_share[years[-1]], per_share[years[-2]]
    return None if before <= 0 else now / before - 1


def depth(quarter_count: int, year_count: int) -> str:
    if quarter_count >= 8 and year_count >= 4:
        return "Deep"
    return "Medium" if quarter_count >= 4 else "Thin"


def compute(data: dict) -> dict | None:
    """One company's numbers, or None when it has no revenue at all (foreign filers without US-GAAP frames)."""
    data = {"q": data.get("q") or {}, "a": data.get("a") or {}, "i": data.get("i") or {}}
    quarters = {m: _quarters(data["q"].get(m, {}), data["a"].get(m, {}), m != "shares_avg") for m in FLOW}
    revenue = quarters["revenue"]
    annual_revenue = _annual_flow(data, "revenue")
    if not revenue and not annual_revenue:
        return None
    seen = list(revenue) or [qindex(l) for l in data["i"].get("cash", {}) if _LABEL.match(l)]
    if not seen:  # annual-only company: anchor on the last fiscal year end
        seen = [max(annual_revenue) * 4 + 3]
    end = max(seen)
    now_q, year_ago_q, two_ago_q = revenue.get(end), revenue.get(end - 4), revenue.get(end - 8)
    growth = _growth(now_q, year_ago_q)
    prior = _growth(year_ago_q, two_ago_q)
    if growth is None and len(annual_revenue) >= 2:  # annual-only filers: last two fiscal years
        years = sorted(annual_revenue)
        growth = _growth(annual_revenue[years[-1]], annual_revenue[years[-2]])
        prior = _growth(annual_revenue[years[-2]], annual_revenue[years[-3]]) if len(years) >= 3 else None
    ttm_revenue = _window(revenue, end)
    if ttm_revenue is None and annual_revenue:
        ttm_revenue = annual_revenue[max(annual_revenue)]
    ttm_gross = _window(quarters["gross"], end)
    gross_margin = _ratio(ttm_gross, ttm_revenue) if _window(revenue, end) is not None else None
    if gross_margin is None:
        annual_gross = _annual_flow(data, "gross")
        shared = [y for y in annual_gross if y in annual_revenue]
        gross_margin = _ratio(annual_gross[max(shared)], annual_revenue[max(shared)]) if shared else None
    ocf, capex, fcf_year = _ttm_cash(data, quarters, end)
    fcf = None if ocf is None or capex is None else ocf - capex
    fcf_revenue = ttm_revenue if fcf_year is None else annual_revenue.get(fcf_year)  # margin on the same basis as the cash flow
    cash = _num(data["i"].get("cash", {}).get(qlabel(end)))
    debt = _num(data["i"].get("debt", {}).get(qlabel(end)))
    shares_now, shares_before = _shares(data, quarters, end), _shares(data, quarters, end - 4)
    by_year = _fcf_by_year(data)
    per_share = _fcf_ps_by_year(data, quarters, by_year)
    quarter_count = len(revenue)
    year_count = len(annual_revenue)
    return {
        "as_of": qlabel(end),
        "ttm_revenue": ttm_revenue,
        "revenue_growth": growth,
        "revenue_growth_prior": prior,
        "accelerating": None if growth is None or prior is None else growth > prior,
        "gross_margin": gross_margin,
        "fcf": fcf,
        "fcf_margin": _ratio(fcf, fcf_revenue),
        "net_cash": None if cash is None or debt is None else cash - debt,
        "debt_to_fcf": _ratio(debt, fcf) if fcf and fcf > 0 else None,
        "share_change": None if shares_now is None or shares_before is None or shares_before <= 0 else shares_now / shares_before - 1,
        "fcf_per_share_growth": _per_share_growth(per_share),
        "ocf": ocf, "capex": capex, "shares": shares_now, "cash": cash, "debt": debt,
        "fcf_ps_by_year": {str(y): v for y, v in per_share.items()},
        "fcf_by_year": {str(y): v for y, v in by_year.items()},
        "quarters": quarter_count,
        "years": year_count,
        "depth": depth(quarter_count, year_count),
    }
