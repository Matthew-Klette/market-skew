"""The monthly plan on the Picks page: a TFSA block and a USD block, in rand. The browser rescales the TFSA row as you
type (data-plan-config); the USD table is re-rendered by the server (POST /plan) so rounding and tilts stay exact."""
import datetime as dt
import json

from .. import allocation, costs, system
from .fmt import e

DEFAULT_AMOUNTS = {"tfsa": 0.0, "usd": 0.0}   # nothing is assumed: a fresh install asks (see first_run)


def first_run() -> str:
    """Shown instead of the plan until you say how much you invest. Saves through POST /amounts, then the page reloads."""
    return """<section class="block plan first-run" data-first-run>
<div class="block-head"><h2>Tell me how much you invest each month</h2><span class="hint">Then this page builds your plan.</span></div>
<p class="prose">Enter the rand you put in each month. Leave a box at 0 if you don't use that account. You can change these any time; they are
saved on this DEVICE only, per month. Nothing is bought for you: the plan is a suggestion for you to act on yourself.</p>
<form data-first-run-form>
<label class="amount">TFSA each month <span class="amount-box">R <input type="number" min="0" step="100" inputmode="numeric" value="" placeholder="0" data-first-amount="tfsa" aria-label="TFSA each month in rand"></span></label>
<label class="amount">USD account each month <span class="amount-box">R <input type="number" min="0" step="100" inputmode="numeric" value="" placeholder="0" data-first-amount="usd" aria-label="USD account each month in rand"></span></label>
<button type="submit">Build my plan</button> <span class="hint" data-first-run-status></span>
</form></section>""".replace("this DEVICE", f"this {system.DEVICE}")


def rand(value: float) -> str:
    return f"R{value:,.0f}"


def dollars(value: float, rate: float | None) -> str:
    return f"${value / rate:,.0f}" if rate else "–"


def usd_lines(report: dict, amount: float, rate: float | None) -> list[dict]:
    """The recommendation: the USD amount split by the funds' signals, with the stock slice going to the Picks."""
    return allocation.allocate(amount, report.get("funds") or {}, report.get("swing") or [], rate, tilt=report.get("drift_tilt"))


def usd_body(lines: list[dict], rate: float | None) -> str:
    """The rows of the USD table (lines plus a total), also what POST /plan returns."""
    rows = "".join(
        f'<tr><td class="line-name"><b>{e(x["symbol"])}</b> <span class="muted">{e(x["name"])}</span>'
        f'<div class="line-why">{e(x["reason"])}</div></td><td>{rand(x["rand"])}</td><td>{dollars(x["rand"], rate)}</td>'
        f'<td>{rand(x["fee"])}</td><td>{rand(x["invested"])}</td></tr>' for x in lines)
    total, fee, net = sum(x["rand"] for x in lines), sum(x["fee"] for x in lines), sum(x["invested"] for x in lines)
    return (rows + f'<tr class="total"><td><b>Total</b></td><td>{rand(total)}</td><td>{dollars(total, rate)}</td>'
            f'<td>{rand(fee)}</td><td>{rand(net)}</td></tr>')


def _row(label: str, note: str, weight: float, amount: float, fee_pct: float, rate: float | None, show_usd: bool) -> str:
    gross = amount * weight
    fee = gross * fee_pct
    usd = f'<td data-cell="usd">{dollars(gross, rate)}</td>' if show_usd else ""
    return (f'<tr data-w="{weight:.6f}"><td><b>{e(label)}</b> <span class="muted">{e(note)}</span></td>'
            f'<td data-cell="rand">{rand(gross)}</td>{usd}<td data-cell="fee">{rand(fee)}</td>'
            f'<td data-cell="net">{rand(gross - fee)}</td></tr>')


def _total(amount: float, line: dict, rate: float | None, show_usd: bool) -> str:
    usd = f'<td data-cell="usd">{dollars(amount, rate)}</td>' if show_usd else ""
    return (f'<tr class="total" data-w="1"><td><b>Total</b></td><td data-cell="rand">{rand(amount)}</td>{usd}'
            f'<td data-cell="fee">{rand(line["fee"])}</td><td data-cell="net">{rand(line["invested"])}</td></tr>')


def _head(show_usd: bool) -> str:
    usd = "<th>In dollars, before costs</th>" if show_usd else ""
    return f"<thead><tr><th>Line</th><th>Put in</th>{usd}<th>Costs</th><th>Invested after costs</th></tr></thead>"


def _input(name: str, label: str, value: float) -> str:
    return (f'<label class="amount">{e(label)} <span class="amount-box">R <input type="number" min="0" step="100" '
            f'inputmode="numeric" value="{value:.0f}" data-amount="{name}" aria-label="{e(label)} in rand"></span></label>')


def _cost_note(line_kind: str) -> str:
    if line_kind == "tfsa":
        return "Costs: JSE ETF buys are about 0.25% (VAT on rand trades is unverified, so treat it as about)."
    return (f"Costs: rand to dollars is about {costs.RATES['fx_convert'] * 100:.1f}% (about 0.5% transfer plus about 0.7% rate margin), "
            f"then about {costs.RATES['usd_buy'] * 100:.2f}% a buy (0.25% brokerage + 0.31% clearing, plus 15% VAT).")


def plan(amounts: dict, report: dict, rate: float | None, jse: dict) -> str:
    tfsa_amt, usd_amt = float(amounts["tfsa"]), float(amounts["usd"])
    tfsa, usd = costs.tfsa_line(tfsa_amt), costs.usd_line(usd_amt)
    quote = jse.get("SYG500") or {}
    price = quote.get("price")
    old = f", as of {quote['date']}" if price and quote.get("date") not in (None, dt.date.today().isoformat()) else ""
    price_txt = f"about R{price:,.2f} a unit{old}" if price else "price at next scan"
    lines = usd_lines(report, usd_amt, rate)
    config = {"rate": rate, "tfsaFee": tfsa["fee_pct"]}
    tfsa_rows = _row("SYG500", f"Sygnia Itrix S&P 500 on the JSE, {price_txt}", 1.0, tfsa_amt, tfsa["fee_pct"], rate, False)
    when = report.get("rate_date")
    stale = when and when != dt.date.today().isoformat()
    if not rate:
        rate_txt = "The rand rate comes at the next scan, so dollar amounts are hidden until then."
    elif stale:
        rate_txt = f"At the last known rate of R{rate:,.2f} to the dollar (ECB, via Frankfurter, {e(when)})."
    else:
        rate_txt = f"At today's rate of R{rate:,.2f} to the dollar (ECB, via Frankfurter)."
    return f"""<section class="block plan" data-plan data-plan-config="{e(json.dumps(config))}">
<div class="block-head"><h2>Your plan this month</h2><span class="hint">The recommendation built from everything above: the funds by their signals, and the stock slice to your Picks.</span></div>
<h3 class="plan-sub">TFSA <span class="muted">rand account</span></h3>
{_input("tfsa", "TFSA this month", tfsa_amt)}
<div class="table-wrap"><table class="data split" data-block="tfsa">{_head(False)}<tbody>{tfsa_rows}{_total(tfsa_amt, tfsa, rate, False)}</tbody></table></div>
<p class="hint">{_cost_note("tfsa")}</p>
<h3 class="plan-sub">USD account <span class="muted">paid in rand, converted to dollars</span></h3>
{_input("usd", "USD account this month", usd_amt)}
<div class="table-wrap"><table class="data split" data-block="usd">{_head(True)}<tbody>{usd_body(lines, rate)}</tbody></table></div>
<p class="hint">{rate_txt} {_cost_note("usd")}</p>
<p class="hint">EasyEquities Thrive also charges R{costs.THRIVE_MONTHLY_FEE} a month, whatever you buy.</p>
{f'<p class="prose drift-note"><b>{e(report["drift_note"])}</b> <a href="/money">See your split</a></p>' if report.get("drift_note") else ""}
<p class="prose"><b>How the USD money is split:</b> QQQ, SCHD and VOO each get at least 15%. What's left above that leans towards
the funds whose options signal says it's a good time to add. Single stocks (your Picks, top two)
get 30%, and that money goes back to the funds when nothing qualifies. VOOG gets nothing new. Put money in every month,
whatever the market does; that matters more than timing.</p></section>"""
