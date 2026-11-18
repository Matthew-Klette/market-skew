"""Money tab: "What a bad year looks like", from the mix's own history in rand. Historical, not a bell curve."""
from .fmt import e
from .goal_view import NOT_A_FORECAST, rand


GAIN = " In rand it was a gain: a weaker rand lifts dollar funds."


def _month(m: str) -> str:
    return f"{('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[int(m[5:7]) - 1]} {m[:4]}"


def _loss(x: dict) -> str:
    return f"{rand(abs(x['rand']))} ({abs(x['pct']) * 100:.1f}%)"


def _tile(label: str, value: str, note: str) -> str:
    return f'<div class="tile"><div class="tile-label">{e(label)}</div><div class="tile-value">{e(value)}</div><div class="tile-note">{e(note)}</div></div>'


def _drawdown(d: dict) -> str:
    if d["recovered"]:
        return (f"Fell from {_month(d['peak'])} to {_month(d['trough'])}, back at the old high in {_month(d['recovered'])}: "
                f"{d['months_to_recover']} months from the bottom, {d['months_underwater']} from the peak.")
    return f"Fell from {_month(d['peak'])} to {_month(d['trough'])} and has not got back to the old high yet."


def block(r: dict) -> str:
    head = f'<div class="block-head"><h2>What a bad year looks like</h2><span class="hint">{e(NOT_A_FORECAST)}</span></div>'
    if r["reason"] or not r["stats"]:
        return f'<section class="block">{head}<p class="notice" role="note">{e(r["reason"] or "Not enough shared price history yet.")}</p></section>'
    s = r["stats"]
    basis = (f"No holdings valued yet, so this uses {rand(r['value'])} as an example." if r["assumed"]
             else f"On your holdings, about {rand(r['value'])}.")
    tiles = "".join((
        _tile("A bad month (1 in 20)", _loss(s["var"]), "Value at risk, 95%: you lose at least this in about 1 month in 20."),
        _tile("When it is that bad", _loss(s["cvar"]), "Average loss in those worst months (CVaR, 95%)."),
        _tile("Worst month", _loss(s["worst_month"]), _month(s["worst_month"]["month"])),
        _tile("Worst 12 months", _loss(s["worst_12"]) if s["worst_12"] else "–",
              f"{_month(s['worst_12']['from'])} to {_month(s['worst_12']['to'])}" if s["worst_12"] else "")))
    stress = "".join(f"<li>{e(x['label'])} again would {'cost' if x['rand'] < 0 else 'add'} {e(rand(abs(x['rand'])))} ({abs(x['pct']) * 100:.1f}%).{GAIN if x['rand'] >= 0 else ''}</li>" for x in s["stress"])
    stress = f'<h3 class="plan-sub">If an old fall came back</h3><ul class="prose">{stress}</ul>' if stress else \
        '<p class="hint">The saved history is too short to replay 2022 or March 2020.</p>'
    proxy = " ".join(f"{n} before {v['from']} is {v['proxy']} in rand." for n, v in r["notes"].items() if v.get("from"))
    return (f'<section class="block">{head}<p class="prose">{e(basis)} Amounts are in rand, from {e(_month(s["from"]))} to {e(_month(s["to"]))} '
            f'({s["months"]} months of {e(r["label"])}). {e(proxy)}</p>'
            f'<div class="tiles four">{tiles}</div>'
            f'<h3 class="plan-sub">Biggest fall</h3><p class="prose"><b>{e(f"{s["drawdown"]["depth"] * 100:.1f}%")}</b> down. {e(_drawdown(s["drawdown"]))}</p>{stress}'
            f'<p class="hint">Worked out from what really happened, not a bell curve, because bad months come in clumps. Dividends are included; fees are not.</p></section>')
