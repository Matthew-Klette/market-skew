"""The red BUY NOW banner at the top of the Picks page. Nothing at all on the (many) days it does not fire."""
from .. import buynow
from .fmt import e, money, ticker_link


def _card(h: dict) -> str:
    why = "".join(f"<li>{e(x)}</li>" for x in h["reasons"])
    risks = "".join(f"<li>{e(x)}</li>" for x in h["risks"])
    kind = "Index fund" if h["kind"] == "fund" else "Stock"
    return f"""<article class="buynow-card" data-buynow="{e(h["symbol"])}">
<div class="buynow-head"><span class="buynow-word">BUY NOW</span><span class="pick-symbol">{ticker_link(h["symbol"])}</span>
<span class="muted">{e(h["name"])} · {kind} · ${money(h["price"])}</span></div>
<p class="buynow-action">{e(h["action"])}</p>
<p class="answer-a">Why every check lined up</p><ul class="pick-why">{why}</ul>
<details class="explain"><summary>What could still go wrong</summary><ul class="because">{risks}</ul></details></article>"""


def block(hits: list[dict] | None) -> str:
    if not hits:
        return ""
    return f"""<section class="block buynow" aria-label="BUY NOW">{"".join(_card(h) for h in hits)}
<p class="hint">BUY NOW only shows when every strict check agrees at once ({buynow.STOCK_SCORE}+ Quality score after Claude, price under the
bear case and on a floor for a stock; a 10%+ market drop, a fear spike and bullish options for a fund). Most days it's empty. Rules on public
data, not advice, and not a promise. See How it works.</p></section>"""
