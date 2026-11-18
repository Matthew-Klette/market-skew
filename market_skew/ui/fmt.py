"""Small, pure formatting helpers shared by the views and the export."""
from html import escape

BUCKET_CLASS = {"Contrarian Bid": "fresh", "Chase": "crowded", "Hedged Rally": "tighten", "Fear": "fear"}


def e(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def pct(value, signed: bool = True, digits: int = 1) -> str:
    if value is None:
        return "–"
    return f"{value * 100:+.{digits}f}%" if signed else f"{value * 100:.{digits}f}%"


def tone(value, flat: float = 0.0005) -> str:
    if value is None or abs(value) < flat:
        return "flat"
    return "up" if value > 0 else "down"


def money(value) -> str:
    if value is None:
        return "–"
    return f"{value:,.2f}" if value < 1000 else f"{value:,.0f}"


def count(value) -> str:
    if value is None:
        return "–"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{value / 1e3:.1f}k"
    return f"{value:.0f}"


def cp_ratio(calls, puts) -> str:
    if not calls and not puts:
        return "–"
    return f"{(calls or 0) / max(puts or 0, 1):.2f}"


def ticker_link(symbol: str) -> str:
    """A ticker that opens its Research card. Tickers are [A-Z0-9-] only (holdings.TICKER), so the path needs no quoting."""
    return f'<a class="tlink" href="/research/{e(symbol)}">{e(symbol)}</a>'
