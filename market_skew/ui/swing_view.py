"""The Picks section: each pick with entry, stop, target and a give-up date, buy ladder, earnings line, quality score and prediction; then the paper record vs VOO."""
from .. import costs, gate
from . import levels_view, near_view, prediction_view, research_view
from .fmt import e, money, pct, tone, ticker_link

STATUS = {"open": "Open", "stopped": "Hit the stop", "target": "Hit the target", "time": "Time ran out"}
FEES = (costs.RATES["usd_buy"] + costs.RATES["usd_sell"]) * 100


def _level(label: str, price: float, dist: float, tone_name: str) -> str:
    return (f'<div class="level"><span class="muted">{e(label)}</span><b>${money(price)}</b>'
            f'<span class="{tone_name}">{pct(dist)}</span></div>')


def earnings_note(text: str) -> str:
    return f'<div class="hint earn-note">{e(text)}</div>' if text else ""


def _card(t: dict, r: dict, preds: dict, sentinel: dict) -> str:
    why = "".join(f"<li>{e(x)}</li>" for x in t["reasons"])
    return f"""<article class="pick swing" data-swing="{e(t["symbol"])}">
<div class="pick-head"><div><span class="pick-symbol">{ticker_link(t["symbol"])}</span> <span class="muted">{e(t["name"])}</span>
<div class="leaders">{e(t["sector"])} · {pct(t["ret_1m"])} this month</div>{research_view.chip(sentinel.get(t["symbol"]), t["symbol"])}</div></div>
<div class="levels">{_level("Buy at", t["entry"], 0.0, "flat")}{_level("Sell if below", t["stop"], t["stop_pct"], "down")}
{_level("Take profit at", t["target"], t["target_pct"], "up")}<div class="level"><span class="muted">Give it until</span><b>{e(t["until"])}</b><span class="muted">28 days</span></div></div>
<p class="answer-a"><span class="pill fresh">Worth a look</span> because</p><ul class="pick-why">{why}</ul>{earnings_note(t.get("earnings", ""))}
{levels_view.block(t["symbol"], r, "swing", (r.get("last_buys") or {}).get(t["symbol"]))}
{prediction_view.block(preds.get(t["symbol"]))}
<button type="button" class="quiet small" data-exclude="{e(t["symbol"])}">Not on EasyEquities</button></article>"""


def _row(x: dict) -> str:
    closed = x["status"] != "open"
    now = f'${money(x["exit_price"])} on {e(x["exit_date"])}' if closed else f'${money(x["now"])}'
    return (f'<tr><td><b>{e(x["symbol"])}</b></td><td>{e(x["date"])}</td><td>${money(x["entry"])}</td><td>{now}</td>'
            f'<td>{e(STATUS.get(x["status"], x["status"]))}</td><td class="{tone(x["ret"])}">{pct(x["ret"])}{"" if closed else ' <span class="muted">after fees if sold now</span>'}</td>'
            f'<td class="{tone(x["voo_ret"])}">{pct(x["voo_ret"])}</td></tr>')


def _record(rows: list[dict]) -> str:
    if not rows:
        return '<p class="hint">The record starts with the first trades above. No real money.</p>'
    body = "".join(_row(x) for x in rows)
    return f"""<h3 class="plan-sub">Paper record <span class="muted">no real money</span></h3>
<div class="table-wrap"><table class="data swing-record"><thead><tr><th>Trade</th><th>Bought on</th><th>Entry</th><th>Price now / exit</th>
<th>Status</th><th>Return after fees</th><th>VOO same period</th></tr></thead><tbody>{body}</tbody></table></div>
<p class="hint">Closed trades are net of about {FEES:.1f}% round-trip fees (a US buy and a US sell; no rand conversion, since the money
is already in dollars). Open trades show the return so far as if sold now, also after fees. Trades settle on daily closes, so a fast drop can end
past the stop.</p>"""


def hidden_line(symbols: list[str]) -> str:
    if not symbols:
        return ""
    buttons = " ".join(f'<button type="button" class="quiet small" data-include="{e(s)}">Show {e(s)} again</button>' for s in symbols)
    return f'<p class="hint hidden-picks">Hidden because you marked them as not on EasyEquities: {buttons}</p>'


def section(r: dict) -> str:
    trades, preds = r.get("swing") or [], r.get("predictions") or {}
    if trades:
        cards = f'<div class="picks">{"".join(_card(t, r, preds, r.get("sentinel") or {}) for t in trades)}</div>'
    elif r.get("swing") is None:
        cards = '<p class="prose">Not worked out for this report yet. It fills in at the next scan.</p>'
    else:
        cards = ('<p class="answer-a"><span class="pill fear">No stock picks today</span> because</p><ul class="because">'
                 f'<li>No company is both good quality (Quality score {gate.HIS_WAY_MIN} or more, with enough filings) and on sale with people betting on a bounce right now.</li>'
                 '<li>So the stock part of your plan goes into the funds instead. That\'s a fine answer.</li></ul>') + near_view.block(r.get("swing_near"))
    storm = ('<p class="hint"><b>Stormy market:</b> the S&amp;P 500 is down and VIX is jumping, so only the top two are shown.</p>'
             if r.get("swing_storm") else "")
    return f"""<section class="block" data-his-way><div class="block-head"><h2>Picks</h2>
<span class="hint">A quality company at a good moment, with a buy price, a stop and a target.</span></div>
{storm}{cards}{hidden_line(r.get("swing_hidden") or [])}
<details class="explain"><summary>How these are chosen</summary><p class="prose"><b>Attractive first, then timing.</b> The Quality score
must be {gate.HIS_WAY_MIN} or more after Claude argues against it, with enough filings that it is not marked Thin (a score Claude has not checked yet counts at its raw score and says so).
Then the options scan decides when: a Contrarian Bid (down against the market this month while options bets lean bullish), share price $5+, $50M+ traded a day,
options pricing in a move of 100% a year or less, not down more than 35% this month. A company reporting within 7 days is skipped ("Wait until after results"); a missing date never blocks.
Up today and money moving into its sector rank higher; one per sector, at most 5. <b>Sell if below</b> is the bigger of 4% or 1.2 times
the move options expect over two weeks. <b>Take profit at</b> is twice that distance above the entry. If neither is hit, give it
28 days. Buy in pieces at the price levels shown, not all at once.</p></details>
{_record(r.get("swing_record") or [])}</section>"""
