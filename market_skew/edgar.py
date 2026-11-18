"""SEC EDGAR XBRL "frames": one request per concept per period covers every filer. Free, no key.
Raw frames are cached in data/edgar/; a period is fetched again only when it is not cached or the cache is over a week old.
SEC fair access: at most 10 requests a second (this paces at 4) and a User-Agent that names the app, never a person."""
import gzip
import json
import zlib
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import cache, settings

APP_AGENT = "MarketSkew"  # SEC asks for "Name email" exactly; a URL in the agent string gets refused
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json"
DIR = cache.DATA / "edgar"
MAX_AGE_SECONDS = 7 * 86400
PAUSE_SECONDS = 0.25
QUARTERS, YEARS = 10, 6
GIVE_UP_AFTER = 5

# metric -> [(taxonomy, concept, unit)], first tag that has a value for a company wins. kind: flow = 3-month and annual
# durations; instant = balance-sheet date (quarter ends only).
USD, SHARES = "USD", "shares"
SPECS = {
    "revenue": ("flow", [("us-gaap", c, USD) for c in (
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet",
        "RegulatedAndUnregulatedOperatingRevenue", "ElectricUtilityRevenue",  # utilities
        "RevenuesNetOfInterestExpense")]),  # banks
    "gross": ("flow", [("us-gaap", "GrossProfit", USD)]),
    # cost of revenue is only a fallback: company_series turns it into gross profit (revenue - cost) when GrossProfit is not tagged
    "cost": ("flow", [("us-gaap", c, USD) for c in ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold")]),
    "ocf": ("flow", [("us-gaap", c, USD) for c in ("NetCashProvidedByUsedInOperatingActivities",
                                                   "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")]),
    "capex": ("flow", [("us-gaap", c, USD) for c in ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")]),
    "shares_avg": ("flow", [("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", SHARES)]),
    # cash order matters (see _pick): the combined tag, else cash on its own, then short-term investments added when reported separately;
    # the last tag (long-term marketable securities, e.g. Apple, Alphabet) is a separate balance-sheet line and is added once on top
    "cash": ("instant", [("us-gaap", c, USD) for c in ("CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalentsAtCarryingValue",
                                                       "MarketableSecuritiesCurrent", "ShortTermInvestments",
                                                       "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "MarketableSecuritiesNoncurrent")]),
    # debt order matters (see _pick): total long-term debt, else non-current + current parts, else a combined figure
    "debt": ("instant", [("us-gaap", c, USD) for c in ("LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent",
                                                       "DebtLongtermAndShorttermCombinedAmount", "LongTermDebtAndCapitalLeaseObligations")]),
    "shares_out": ("instant", [("dei", "EntityCommonStockSharesOutstanding", SHARES)]),
}


def last_quarter(today) -> tuple[int, int]:
    """The most recent calendar quarter that has ended."""
    quarter = (today.month - 1) // 3
    return (today.year, quarter) if quarter else (today.year - 1, 4)


def quarter_periods(today, count: int = QUARTERS) -> list[str]:
    year, quarter = last_quarter(today)
    index = year * 4 + quarter - 1
    return [f"{(index - n) // 4}Q{(index - n) % 4 + 1}" for n in range(count)]


def year_periods(today, count: int = YEARS) -> list[str]:
    return [str(today.year - 1 - n) for n in range(count)]


def frame_period(label: str, kind: str, instant: bool = False) -> str:
    """'2025Q3' -> CY2025Q3 (3-month) or CY2025Q3I (instant); '2025' -> CY2025."""
    return f"CY{label}" + ("I" if instant and "Q" in label else "")


def jobs(today) -> list[tuple[str, str, str, str, str]]:
    """Every (metric, taxonomy, concept, unit, period label) the weekly refresh needs, newest periods first."""
    out = []
    for metric, (kind, concepts) in SPECS.items():
        labels = quarter_periods(today) + (year_periods(today) if kind == "flow" else [])
        for taxonomy, concept, unit in concepts:
            out += [(metric, taxonomy, concept, unit, label) for label in labels]
    return out


class NoContact(Exception):
    """SEC rejects automated requests that carry no contact; none is set, so nothing is sent."""


def user_agent() -> str:
    contact = settings.sec_contact()
    if not contact:
        raise NoContact(settings.MISSING)
    return f"{APP_AGENT} {contact}"


def _path(concept: str, label: str, instant: bool) -> Path:
    return DIR / f"{concept}__{label}{'I' if instant else ''}.json"


def fresh(path: Path, now: float) -> bool:
    stored = cache.read(path)
    return bool(stored) and now - float(stored.get("fetched", 0)) < MAX_AGE_SECONDS


def _get(url: str, opener=urllib.request.urlopen):
    request = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
    try:
        with opener(request, timeout=60) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            elif response.headers.get("Content-Encoding") == "deflate":
                raw = zlib.decompress(raw)
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        if error.code == 404:  # a period nobody has reported yet
            return {"data": []}
        raise


def parse_frame(payload: dict) -> dict[str, float]:
    """{cik: value}; when a company filed twice for a period, the later end date wins."""
    best: dict[str, tuple[str, float]] = {}
    for row in payload.get("data", []):
        cik, value, end = str(row.get("cik")), row.get("val"), row.get("end", "")
        if isinstance(value, (int, float)) and (cik not in best or end >= best[cik][0]):
            best[cik] = (end, float(value))
    return {cik: value for cik, (_, value) in best.items()}


def fetch_all(today, now: float | None = None, get=_get, sleep=time.sleep, log=print) -> dict:
    """Fills data/edgar/ for every job that is missing or a week old. Returns {'requests': n, 'failed': n}.
    One failed request keeps its older cache and is counted; it never stops the rest."""
    now = now if now is not None else time.time()
    requests = failed = streak = 0
    for metric, taxonomy, concept, unit, label in jobs(today):
        instant = SPECS[metric][0] == "instant" and "Q" in label
        path = _path(concept, label, instant)
        if fresh(path, now):
            continue
        url = FRAMES_URL.format(taxonomy=taxonomy, concept=concept, unit=unit, period=frame_period(label, SPECS[metric][0], instant))
        try:
            values = parse_frame(get(url))
            cache.write(path, {"fetched": now, "values": values})
            streak = 0
        except NoContact:
            raise
        except Exception as error:
            failed += 1
            streak += 1
            log(f"edgar: {concept} {label} skipped ({error})"[:200])
        requests += 1
        if streak >= GIVE_UP_AFTER:  # blocked or down: stop hitting SEC, keep what is cached
            log("edgar: several requests in a row failed, stopping for now")
            break
        sleep(PAUSE_SECONDS)
    return {"requests": requests, "failed": failed}


def load_frames(today) -> dict:
    """Every cached frame the series need, read once: {(concept, label, instant): {cik: value}}."""
    frames = {}
    for metric, taxonomy, concept, unit, label in jobs(today):
        instant = SPECS[metric][0] == "instant" and "Q" in label
        frames[(concept, label, instant)] = cache.read(_path(concept, label, instant)).get("values", {})
    return frames


def company_series(cik: str, today, frames: dict) -> dict:
    """One company's {"q","a","i"} series for fundamentals.compute, from load_frames()."""
    out = {"q": {}, "a": {}, "i": {}}
    for metric, (kind, concepts) in SPECS.items():
        instant = kind == "instant"
        for label in quarter_periods(today) + ([] if instant else year_periods(today)):
            quarter = "Q" in label
            values = [frames.get((c, label, instant and quarter), {}).get(cik) for _, c, _ in concepts]
            value = _pick(metric, values)
            if value is not None:
                out["i" if instant else ("q" if quarter else "a")].setdefault(metric, {})[label] = value
    cost = {"q": out["q"].pop("cost", {}), "a": out["a"].pop("cost", {})}
    for kind in ("q", "a"):  # gross profit = revenue - cost of revenue, only where GrossProfit itself is not tagged
        for label, spend in cost[kind].items():
            revenue = out[kind].get("revenue", {}).get(label)
            if revenue is not None and label not in out[kind].get("gross", {}):
                out[kind].setdefault("gross", {})[label] = revenue - spend
    return out


def _pick(metric: str, values: list):
    if metric == "debt":  # LongTermDebt, else non-current + current parts
        if values[0] is not None:
            return values[0]
        if values[1] is not None:
            return values[1] + (values[2] or 0.0)
        return next((v for v in values[3:] if v is not None), None)
    if metric == "cash":  # combined tag already holds the current investments; else cash + the first short-term investments tag (never two of them)
        noncurrent = values[5] if len(values) > 5 and values[5] is not None else 0.0
        if values[0] is not None:
            return values[0] + noncurrent
        if values[1] is None:
            return None
        # cash + the first current-investments tag (never two of them) + long-term marketable securities when reported
        extra = values[5] if len(values) > 5 and values[5] is not None else 0.0
        return values[1] + next((v for v in values[2:5] if v is not None), 0.0) + extra
    return next((v for v in values if v is not None), None)


def ticker_map(get=_get) -> dict[str, str]:
    """Ticker -> CIK (as a plain number string, the form frames use). Cached for a week."""
    path = DIR / "company_tickers.json"
    stored = cache.read(path)
    if stored and time.time() - float(stored.get("fetched", 0)) < MAX_AGE_SECONDS:
        return stored["map"]
    payload = get(TICKERS_URL)
    mapping = {row["ticker"].upper(): str(row["cik_str"]) for row in payload.values()}
    cache.write(path, {"fetched": time.time(), "map": mapping})
    return mapping


def cik_for(symbol: str, mapping: dict[str, str]) -> str | None:
    return mapping.get(symbol.upper()) or mapping.get(re.sub(r"[./]", "-", symbol.upper()))
