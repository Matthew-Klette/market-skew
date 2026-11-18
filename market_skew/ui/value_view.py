"""The fair-value range on the Research tab: a band from bear to bull with today's price marked, shown as a range, never a target."""
from .fmt import e

TAG = {"below bear": ("below range", "down"), "in range": ("in range", "flat"), "above bull": ("above range", "up")}
ORDER = {"below bear": 0, "in range": 1, "above bull": 2}

HOW = """<h3>Fair-value range</h3>
<p>The Research card shows a <b>range</b> from three cases, never one target price. It starts from the company's free cash flow (operating cash
flow minus capex) and grows it for five years, then adds a long-run value, adds cash and takes off debt. <b>Bear</b> grows slower and discounts
harder, <b>base</b> sits in the middle, <b>bull</b> grows faster and discounts less. The marker shows where today's price sits against them.
Small changes in the assumptions move the answer a lot, especially when most of the value is far in the future, so treat it as a question to
ask, not an answer. Banks, insurers and property companies are skipped (cash flow does not describe them), as are companies with zero or negative
free cash flow or too few filings. There are no analyst estimates, and beta is assumed to be 1.0 because no price history is kept for it.</p>"""


def _money(v: float) -> str:
    return f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"


def sort_key(row: dict) -> int:
    v = row.get("value") or {}
    return ORDER[v["band"]] if v.get("ok") else -1


def cell(row: dict) -> str:
    v = row.get("value") or {}
    if not v.get("ok"):
        return '<span class="muted">–</span>'
    text, cls = TAG[v["band"]]
    return f'<span class="{cls}" title="{e(v["position"])}">{e(text)}</span>'


def band_svg(v: dict) -> str:
    """Horizontal bear-base-bull band with today's price marked. Inline SVG, theme tokens only."""
    w, h, pad = 640, 86, 24
    lo, hi = min(v["bear"], v["price"]), max(v["bull"], v["price"])
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.08, hi + span * 0.08
    x = lambda value: pad + (value - lo) / (hi - lo) * (w - 2 * pad)
    label = (f"Fair-value range: bear {_money(v['bear'])}, base {_money(v['base'])}, bull {_money(v['bull'])}. "
             f"Today's price {_money(v['price'])}; {v['position']}.")
    marks = "".join(f'<line class="fv-tick" x1="{x(v[k]):.1f}" x2="{x(v[k]):.1f}" y1="24" y2="46"/>'
                    f'<text class="fv-text" x="{x(v[k]):.1f}" y="62" text-anchor="middle">{k}</text>'
                    f'<text class="fv-num" x="{x(v[k]):.1f}" y="78" text-anchor="middle">{_money(v[k])}</text>' for k in ("bear", "base", "bull"))
    px = x(v["price"])
    return (f'<svg class="fv-band" viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}">'
            f'<rect class="fv-bar" x="{x(v["bear"]):.1f}" y="30" width="{x(v["bull"]) - x(v["bear"]):.1f}" height="10" rx="5"/>{marks}'
            f'<line class="fv-price" x1="{px:.1f}" x2="{px:.1f}" y1="14" y2="46"/>'
            f'<text class="fv-price-text" x="{px:.1f}" y="10" text-anchor="middle">price {_money(v["price"])}</text></svg>')


def block(row: dict) -> str:
    v = row.get("value")
    head = '<section class="block"><div class="block-head"><h2>Fair-value range</h2><span class="hint">A range from cash flows. Not a target price.</span></div>'
    if not v:
        return head + '<p class="hint">Not calculated yet. Run ./skew value.</p></section>'
    if not v["ok"]:
        return head + f'<p class="hint">No range for this company: {e(v["reason"])}</p></section>'
    flags = "".join(f'<li>{e(f)}</li>' for f in v["flags"])
    notes = f'<ul class="prose fv-flags">{flags}</ul>' if flags else ""
    assume = "".join(f"<li>{e(a)}</li>" for a in v["assumptions"])
    return (f'{head}<p class="fv-position"><b>{e(v["position"].capitalize())}.</b> '
            f'<span class="muted">Bear {_money(v["bear"])}, base {_money(v["base"])}, bull {_money(v["bull"])} a share.</span></p>'
            f'{band_svg(v)}{notes}<details><summary>What this assumes</summary><ul class="parts">{assume}</ul>'
            f'<p class="hint">Small changes in these numbers move the range a lot. For your own research. Not financial advice.</p></details></section>')
