"""The Money tab: rules of thumb with progress bars, TFSA room, then the holdings editor and drift (holdings_view).
Every number comes from the saved inputs and cached prices; nothing is fetched here."""
from .. import money_rules, system
from . import goal_view, holdings_view, risk_view
from .fmt import e

LABELS = {"take_home": "Monthly take-home", "expenses": "Monthly expenses", "rent": "Monthly rent",
          "emergency": "Emergency fund balance", "tfsa_year": "TFSA put in this tax year (Mar to Feb)",
          "tfsa_life": "TFSA put in, lifetime"}
NOTES = {"ok": "On track", "low": "Below the rule of thumb", "high": "Above the rule of thumb", "unknown": "Add your numbers"}


def rand(value: float) -> str:
    return f"R{value:,.0f}"


def _field(key: str, value) -> str:
    shown = "" if value is None else f"{value:.0f}"
    return (f'<label class="money-field"><span>{e(LABELS[key])}</span><span class="amount-box">R <input type="number" min="0" '
            f'step="100" inputmode="numeric" name="{key}" value="{shown}" aria-label="{e(LABELS[key])} in rand"></span></label>')


def meter(label: str, fill: float | None, mark: float, kind: str, status: str, value: str, target: str) -> str:
    """A bar filled to `fill` of its scale with a tick at the target. fill is 0..1 or None when unknown."""
    width = 0 if fill is None else max(0.0, min(fill, 1.0)) * 100
    return (f'<div class="meter" data-status="{e(status)}"><div class="meter-head"><b>{e(label)}</b>'
            f'<span class="muted">{e(value)}</span></div>'
            f'<div class="meter-track" role="img" aria-label="{e(label)}: {e(value)}, target {e(target)}">'
            f'<span class="meter-fill" style="width:{width:.1f}%"></span><span class="meter-mark" style="left:{mark * 100:.1f}%"></span></div>'
            f'<div class="meter-note">{e(NOTES[status])} · {e(target)}</div></div>')


def _rule(r: dict) -> str:
    if r["key"] == "fun":
        value = rand(r["amount"]) if r["amount"] else "–"
        return meter(r["label"], None, 0.5, "suggest", "unknown", value, "about 5% of take-home").replace(
            f'{NOTES["unknown"]} ·', "Suggestion ·")
    actual = r["actual"]
    if r["unit"] == "months":
        value = "–" if actual is None else f"{actual:.1f} months"
        target, scale = f"{r['target']:.0f} months", r["target"] * 2
    else:
        value = "–" if actual is None else f"{actual * 100:.0f}%"
        target = f"{'at least' if r['kind'] == 'min' else 'no more than'} {r['target'] * 100:.0f}% of take-home"
        scale = max(r["target"] * 2, (actual or 0) * 1.05)
    return meter(r["label"], None if actual is None else actual / scale, r["target"] / scale, r["kind"], r["status"], value, target)


def tfsa_block(room: dict) -> str:
    warn = f'<p class="notice" role="note">{e(room["warning"])}</p>' if room["warning"] else ""
    return f"""<section class="block"><div class="block-head"><h2>TFSA room</h2><span class="hint">Tax year {e(room["year_label"])}. SARS limits: R36,000 a year, R500,000 for life.</span></div>
<div class="tiles tiles-3"><div class="tile"><div class="tile-label">Left this tax year</div><div class="tile-value">{rand(room["year_left"])}</div></div>
<div class="tile"><div class="tile-label">Left for life</div><div class="tile-value">{rand(room["life_left"])}</div></div>
<div class="tile"><div class="tile-label">You can still put in</div><div class="tile-value">{rand(room["room"])}</div><div class="tile-note">the smaller of the two</div></div></div>
<p class="prose">{e(room["monthly_line"])}</p>{warn}</section>"""


def rules_block(inputs: dict, rows: list[dict], invested: float) -> str:
    fields = "".join(_field(k, inputs.get(k)) for k in ("take_home", "expenses", "rent", "emergency", "tfsa_year", "tfsa_life"))
    bars = "".join(_rule(r) for r in rows)
    return f"""<section class="block"><div class="block-head"><h2>Money rules</h2><span class="hint">A common rule of thumb, not advice. Your numbers stay on this {system.DEVICE}.</span></div>
<form class="money-form" data-money-form>{fields}<button type="submit">Save</button> <span class="hint" data-money-status></span></form>
<div class="meters">{bars}</div>
<p class="hint">Invested each month uses this month's TFSA and USD amounts from Picks ({rand(invested)}). Rules of thumb: invest about 20% of take-home, keep 3 months of expenses as an emergency fund, rent about 35% or less, living costs about 50%, about 5% for fun.</p></section>"""


def page(ctx: dict) -> str:
    rows = money_rules.rules(ctx["inputs"], ctx["invested"])
    room = money_rules.tfsa(ctx["inputs"], ctx["tfsa_monthly"], ctx["today"])
    return rules_block(ctx["inputs"], rows, ctx["invested"]) + tfsa_block(room) + holdings_view.page(ctx) + goal_view.block(ctx["goal"]) + risk_view.block(ctx["risk"])
