"""My holdings editor, with current values from cached prices, and the drift / cash-flow rebalance block."""
from .. import rebalance
from .fmt import e

PROMPT = "Add how many units you own to see your split."


def rand(value: float) -> str:
    return f"R{value:,.0f}"


def _num(value) -> str:
    return "" if value is None else f"{value:g}"


def _input(name: str, value, label: str, step: str = "any") -> str:
    return (f'<input type="number" min="0" step="{step}" inputmode="decimal" data-f="{name}" value="{_num(value)}" '
            f'aria-label="{e(label)}">')


def holding_row(h: dict, value: float | None = None) -> str:
    sym, acct = e(h.get("symbol", "")), h.get("account", "usd")
    options = "".join(f'<option value="{k}"{" selected" if acct == k else ""}>{n}</option>' for k, n in (("usd", "USD account"), ("tfsa", "TFSA")))
    return (f'<tr data-holding><td><input type="text" data-f="symbol" value="{sym}" maxlength="7" size="7" autocapitalize="characters" aria-label="Ticker"></td>'
            f'<td><select data-f="account" aria-label="Account">{options}</select></td>'
            f'<td>{_input("units", h.get("units"), "Units owned")}</td><td>{_input("avg_price", h.get("avg_price"), "Average buy price")}</td>'
            f'<td>{_input("last_buy", h.get("last_buy"), "Last buy price")}</td>'
            f'<td><input type="checkbox" data-f="new_money" aria-label="Add new money"{"" if h.get("new_money") is False else " checked"}></td>'
            f'<td class="value">{rand(value) if value else "–"}</td>'
            f'<td><button type="button" class="quiet small" data-remove-row aria-label="Remove {sym}">Remove</button></td></tr>')


def editor(holdings: list[dict], vals: list[dict]) -> str:
    by = {(v["symbol"], v["account"]): v["rand"] for v in vals}
    rows = "".join(holding_row(h, by.get((h["symbol"], h["account"]))) for h in holdings)
    blank = holding_row({"symbol": "", "account": "usd"})
    missing = f'<p class="notice" role="note">{PROMPT}</p>' if any(h.get("units") is None for h in holdings) else ""
    return f"""<section class="block" data-holdings><div class="block-head"><h2>My holdings</h2><span class="hint">Prices are the last saved ones, in rand. Average and last buy prices are in the holding's own currency (dollars for USD, rand for TFSA); both are optional.</span></div>
{missing}<div class="table-wrap"><table class="data holdings-edit"><thead><tr><th>Ticker</th><th>Account</th><th>Units</th><th>Average buy price</th>
<th>Last buy price</th><th>New money</th><th>Value</th><th></th></tr></thead><tbody data-rows>{rows}</tbody></table></div>
<template data-row-template>{blank}</template>
<p class="actions"><button type="button" class="quiet" data-add-row>Add row</button> <button type="button" data-save-holdings>Save holdings</button> <span class="hint" data-holdings-status></span></p></section>"""


def meter_pair(row: dict) -> str:
    """Actual against target: a filled bar for the actual with a tick at the target."""
    s = row["sleeve"]
    word = "at least" if row["kind"] == "min" else "no more than"
    state = {"under": "Under target", "over": "Over target", "ok": "Within target"}[row["state"]]
    gap = f'{row["drift"] * 100:+.0f}pp'
    return (f'<div class="meter" data-status="{"ok" if row["state"] == "ok" else "high" if row["state"] == "over" else "low"}">'
            f'<div class="meter-head"><b>{e(rebalance.SLEEVE_NAMES[s])}</b><span class="muted">{row["actual"] * 100:.0f}% now, {word} {row["target"] * 100:.0f}%</span></div>'
            f'<div class="meter-track" role="img" aria-label="{e(rebalance.SLEEVE_NAMES[s])}: {row["actual"] * 100:.0f} percent, target {row["target"] * 100:.0f} percent">'
            f'<span class="meter-fill" style="width:{min(row["actual"], 1) * 100:.1f}%"></span><span class="meter-mark" style="left:{row["target"] * 100:.1f}%"></span></div>'
            f'<div class="meter-note">{state} ({gap}) · {e(rebalance.SLEEVE_FUNDS[s])}</div></div>')


def _target_fields(targets: dict) -> str:
    return "".join(f'<label class="money-field"><span>{e(rebalance.SLEEVE_NAMES[s])}</span><span class="amount-box"><input type="number" min="0" max="100" step="1" '
                   f'name="{s}" value="{targets[s] * 100:.0f}" aria-label="{e(rebalance.SLEEVE_NAMES[s])} target percent"> %</span></label>' for s in rebalance.SLEEVES)


def drift_block(ctx: dict) -> str:
    w, targets = ctx["weights"], ctx["targets"]
    form = (f'<form class="money-form" data-targets-form>{_target_fields(targets)}<button type="submit">Save targets</button> '
            f'<span class="hint" data-targets-status></span></form>'
            '<p class="hint">Broad ETFs are a floor, growth funds and single stocks are ceilings. The three should add up to 100%.</p>')
    if not w["weights"]:
        return (f'<section class="block"><div class="block-head"><h2>Drift and this month\'s money</h2><span class="hint">Your split against your targets.</span></div>'
                f'{form}<p class="prose">{PROMPT}</p></section>')
    bars = "".join(meter_pair(r) for r in ctx["drift"])
    sugg = "".join(f'<tr><td><b>{e(rebalance.SLEEVE_NAMES[x["sleeve"]])}</b><div class="line-why">{e(rebalance.SLEEVE_FUNDS[x["sleeve"]])}</div></td>'
                   f'<td>{rand(x["rand"])}</td></tr>' for x in ctx["suggestion"])
    note = f'<p class="prose">{e(ctx["note"])}</p>' if ctx.get("note") else ""
    return f"""<section class="block"><div class="block-head"><h2>Drift and this month's money</h2><span class="hint">Valued at about {rand(w["total"])} with the saved prices and rand rate.</span></div>
{form}<div class="meters">{bars}</div>{note}
<h3 class="plan-sub">If you put in {rand(ctx["cash"])} this month</h3>
<p class="hint">It goes to the most underweight sleeves first. Nothing is ever sold. This sits beside the plan on Picks and does not change its numbers, except a small lean towards the funds when a sleeve is over 5pp off.</p>
<div class="table-wrap"><table class="data split"><tbody>{sugg}</tbody></table></div></section>"""


ETF_NOTES = {"low": "Below the rule of thumb: more in single stocks than the rule suggests", "ok": "Inside the rule of thumb",
             "high": "Above the rule of thumb: more in ETFs than the rule suggests"}


def etf_block(share: dict | None) -> str:
    """Share of holdings value in ETFs (VOO, SYG500, SCHD, QQQ, STXNDQ, VOOG; single stocks do not count) against the 70 to 75% rule."""
    low, high = rebalance.ETF_RULE_LOW, rebalance.ETF_RULE_HIGH
    rule = f"A common rule of thumb is {low * 100:.0f} to {high * 100:.0f}% of what you hold in ETFs, the rest in single stocks."
    if not share:
        body = f'<p class="prose">{PROMPT}</p>'
    else:
        now = f"{share['share'] * 100:.0f}%"
        body = (f'<div class="meter" data-status="{share["status"]}"><div class="meter-head"><b>ETFs share of holdings</b><span class="muted">{now} of {rand(share["total"])}</span></div>'
                f'<div class="meter-track" role="img" aria-label="ETFs are {now} of holdings; rule of thumb {low * 100:.0f} to {high * 100:.0f} percent">'
                f'<span class="meter-fill" style="width:{min(share["share"], 1) * 100:.1f}%"></span>'
                f'<span class="meter-mark" style="left:{low * 100:.1f}%"></span><span class="meter-mark" style="left:{high * 100:.1f}%"></span></div>'
                f'<div class="meter-note">{e(ETF_NOTES[share["status"]])} · {low * 100:.0f} to {high * 100:.0f}%</div></div>')
    return (f'<section class="block"><div class="block-head"><h2>ETF share</h2><span class="hint">{e(rule)}</span></div>{body}'
            f'<p class="hint">Counted as ETFs: {e(", ".join(rebalance.ETFS))}. Everything else counts as a single stock. Not advice.</p></section>')


def page(ctx: dict) -> str:
    return editor(ctx["holdings"], ctx["values"]) + etf_block(rebalance.etf_share(ctx["values"])) + drift_block(ctx)
