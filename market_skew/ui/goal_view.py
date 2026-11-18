"""Money tab: "Will I get there?" form, the 10/50/90 fan (inline SVG, colours from the page tokens) and the plain numbers."""
from .. import goal, milestones
from .fmt import e

W, H, PAD_L, PAD_R, PAD_T, PAD_B = 640, 260, 62, 14, 14, 30
HOT = 0.12  # above this a year the sampled history was a strong stretch; the page says so
NOT_A_FORECAST = "Past returns, resampled; not a forecast."


def rand(value: float) -> str:
    return f"R{value:,.0f}"


def compact(value: float) -> str:
    if value >= 1e6:
        return f"R{value / 1e6:.1f}m"
    return f"R{value / 1e3:.0f}k" if value >= 1e3 else f"R{value:.0f}"


def fan_svg(fan: dict, target: float, top: float | None = None) -> str:
    """Band from the 10th to the 90th percentile, a line for the median, a dashed line at the target. Years along the bottom.
    `top` fixes the top of the scale, so two fans can share one."""
    years = fan["years"]
    top = top or max(max(fan["p90"]), target) * 1.05 or 1.0
    x = lambda i: PAD_L + (W - PAD_L - PAD_R) * i / max(len(years) - 1, 1)
    y = lambda v: PAD_T + (H - PAD_T - PAD_B) * (1 - v / top)
    line = lambda key: " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(fan[key]))
    band = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(fan["p90"])) + " " + \
        " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in reversed(list(enumerate(fan["p10"]))))
    yticks = "".join(f'<line class="fan-grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(top * f):.1f}" y2="{y(top * f):.1f}"/>'
                     f'<text class="fan-label" x="{PAD_L - 6}" y="{y(top * f) + 4:.1f}" text-anchor="end">{e(compact(top * f))}</text>' for f in (0, 0.25, 0.5, 0.75, 1))
    step = max(1, len(years) // 8)
    xticks = "".join(f'<text class="fan-label" x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">{years[i]}y</text>' for i in range(0, len(years), step))
    last = fan["p50"][-1]
    label = (f"Value in today's rand over {years[-1]} years. After {years[-1]} years: low {rand(fan['p10'][-1])}, "
             f"middle {rand(last)}, high {rand(fan['p90'][-1])}. Target {rand(target)}.")
    return (f'<svg class="fan" viewBox="0 0 {W} {H}" role="img" aria-label="{e(label)}">{yticks}{xticks}'
            f'<polygon class="fan-band" points="{band}"/><polyline class="fan-edge" points="{line("p10")}"/><polyline class="fan-edge" points="{line("p90")}"/>'
            f'<polyline class="fan-mid" points="{line("p50")}"/>'
            f'<line class="fan-target" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(target):.1f}" y2="{y(target):.1f}"/>'
            f'<text class="fan-label" x="{W - PAD_R}" y="{y(target) - 5:.1f}" text-anchor="end">Target {e(compact(target))}</text></svg>')


def _field(name: str, label: str, value, placeholder: str, suffix: str = "", step: str = "any") -> str:
    shown = "" if value is None else f"{value:.10g}"
    return (f'<label class="money-field"><span>{e(label)}</span><span class="amount-box">{suffix}<input type="number" min="0" step="{step}" '
            f'inputmode="decimal" name="{name}" value="{shown}" placeholder="{e(placeholder)}" aria-label="{e(label)}"></span></label>')


def form(g: dict) -> str:
    f, d = g["form"], g["defaults"]
    pct = None if f["inflation"] is None else round(f["inflation"] * 100, 4)
    return (f'<form class="money-form" data-goal-form>'
            f'{_field("target", "Target, in today\'s rand", f["target"], "2000000", "R ", "1000")}'
            f'{_field("years", "Years (1 to 40)", f["years"], "20", "", "1")}'
            f'{_field("start", "Starting value", f["start"] if g["saved"] else None, rand(d["start"]) + " (your holdings)", "R ", "100")}'
            f'{_field("monthly", "Added each month", f["monthly"] if g["saved"] else None, rand(d["monthly"]) + " (this month\'s plan)", "R ", "100")}'
            f'{_field("inflation", "Inflation a year", pct, "4.5", "", "0.1")}'
            f'<label class="money-field check"><span>Mix</span><span><input type="checkbox" name="actual"{" checked" if f["actual"] else ""}> use my actual split</span></label>'
            f'<button type="submit">Show me</button> <span class="hint" data-goal-status></span></form>')


def _mix_line(g: dict) -> str:
    parts = ", ".join(f"{name} {w * 100:.0f}%" for name, w in sorted(g["weights"].items(), key=lambda x: -x[1]))
    notes = " ".join(f"{n} before {v['from']} is {v['proxy']} in rand ({v['months']} months)." for n, v in g["notes"].items() if v.get("from"))
    stocks = "Single stocks are modelled as QQQ. " if "QQQ" in g["weights"] else ""
    cagr = g.get("cagr")
    grew = ""
    if cagr is not None:
        grew = f" The years being resampled grew {cagr * 100:.0f}% a year in rand before inflation and fees" + \
            (", a strong stretch for dollar funds, so the middle leans optimistic." if cagr > HOT else ".")
    return f"Mix: {g['label']} ({parts}). {stocks}{notes}{grew}"


def _column(title: str, r: dict, f: dict, top: float) -> str:
    fin = r["final"]
    nums = "".join(f'<div class="fan-num"><span class="tile-label">{label}</span><b>{rand(v)}</b></div>'
                   for label, v in (("Weak run", fin["p10"]), ("Middle", fin["p50"]), ("Strong run", fin["p90"])))
    chance = (f"In {r['paths']:,} resampled paths, {r['prob'] * 100:.0f}% reached {rand(f['target'])} in today's money "
              f"after {f['years']} years.")
    return (f'<div class="fan-col"><h3>{e(title)}</h3><p class="prose"><b>{e(chance)}</b></p><div class="fan-nums">{nums}</div>'
            f'{fan_svg(r["fan"], f["target"], top)}</div>')


def _why_cautious(g: dict) -> str:
    cagr = g.get("cagr")
    seen = f"your mix grew about {cagr * 100:.0f}% a year" if cagr is not None else "the past decade returned about 16% a year"
    return (f"Cautious is the default because the past decade's returns were unusually high: {seen} in rand before inflation and fees, "
            f"which is not a pace to plan on. Cautious takes {goal.CAUTIOUS_PP:.0f} points a year off every sampled month and keeps the ups, "
            f"downs and 12-month runs of the real history. Past decade is the same history untouched. Weak run is 1 in 10 lower, strong run 1 in 10 higher.")


def _results(g: dict) -> str:
    r, p, f, fv = g["result"], g["past"], g["form"], g["fv"]
    top = max(max(r["fan"]["p90"]), max(p["fan"]["p90"]), f["target"]) * 1.05
    plain = (f"For comparison, at a steady {fv['rate'] * 100:.0f}% a year (before inflation) you'd have {rand(fv['nominal'])}, "
             f"which is about {rand(fv['real'])} in today's money.")
    cost = (f"Each {rand(f['monthly'])} you add loses about {g['fee'] * 100:.1f}% to fees, so {rand(r['net_monthly'])} is invested "
            f"(rand to dollars and brokerage included). Contributions stay flat in rand; inflation is taken off at {f['inflation'] * 100:.1f}% a year.")
    return (f'<p class="prose">{e(_why_cautious(g))}</p><div class="fan-pair">{_column("Cautious (default)", r, f, top)}{_column("Past decade", p, f, top)}</div>'
            f'<p class="prose">{e(plain)}</p><p class="hint">{e(cost)}</p>')


def _milestone_row(m: dict | None) -> str:
    m = m or {"label": "", "kind": "invested", "value": None, "pct": None, "band": "", "status": "unknown"}
    kinds = "".join(f'<option value="{k}"{" selected" if m["kind"] == k else ""}>{n}</option>'
                    for k, n in (("invested", "Invested (rand)"), ("emergency", "Months of expenses")))
    value = "" if m["value"] is None else f"{m['value']:.10g}"
    pct = m["pct"]
    bar = ('<div class="meter-track" role="img" aria-label="' + (f"{pct * 100:.0f} percent complete" if pct is not None else "no progress yet") + '">'
           f'<span class="meter-fill" style="width:{(pct or 0) * 100:.1f}%"></span></div>')
    label = "–" if pct is None else f"{pct * 100:.0f}%"
    return (f'<tr data-milestone data-status="{"ok" if m["status"] == "done" else "unknown" if pct is None else "open"}">'
            f'<td><input type="text" data-f="label" value="{e(m["label"])}" maxlength="{milestones.MAX_LABEL}" aria-label="Milestone name"></td>'
            f'<td><select data-f="kind" aria-label="Kind">{kinds}</select></td>'
            f'<td><input type="number" min="0" step="any" inputmode="decimal" data-f="value" value="{value}" aria-label="Amount"></td>'
            f'<td class="milestone-progress">{bar}<span class="muted">{label} complete</span></td><td>{e(m["band"])}</td>'
            f'<td><button type="button" class="quiet small" data-remove-row aria-label="Remove milestone">Remove</button></td></tr>')


def milestones_block(rows: list[dict]) -> str:
    body = "".join(_milestone_row(r) for r in rows)
    return (f'<section class="block" data-milestones><div class="block-head"><h2>Milestones</h2>'
            f'<span class="hint">Dates are the middle path in today\'s rand, from the cautious and the past-decade views. Past returns, resampled; not a forecast.</span></div>'
            f'<div class="table-wrap"><table class="data milestones-edit"><thead><tr><th>Milestone</th><th>Kind</th><th>Amount</th><th>Progress</th><th>When</th><th></th></tr></thead>'
            f'<tbody data-rows>{body}</tbody></table></div><template data-row-template>{_milestone_row(None)}</template>'
            f'<p class="actions"><button type="button" class="quiet" data-add-row>Add milestone</button> <button type="button" data-save-milestones>Save milestones</button> '
            f'<span class="hint" data-milestones-status></span></p></section>')


def block(g: dict) -> str:
    if g["reason"]:
        body = f'<p class="notice" role="note">{e(g["reason"])}</p>'
    elif g["result"]:
        body = _results(g)
    else:
        body = '<p class="prose">Type a target and how many years to see the range of where you could end up.</p>'
    mix = f'<p class="hint">{e(_mix_line(g))}</p>' if g["weights"] and not g["reason"] else ""
    return (f'<section class="block"><div class="block-head"><h2>Will I get there?</h2>'
            f'<span class="hint">{e(NOT_A_FORECAST)} Your numbers stay on this Mac.</span></div>{form(g)}{body}{mix}</section>'
            + milestones_block(g.get("milestones") or []))
