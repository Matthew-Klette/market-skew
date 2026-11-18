"""The "Google's prediction" block: a one-month range bar (low, middle, high) with today's price marked, and the track-record verdict."""
from .fmt import e, money

LABEL = "Google's prediction"


def _pos(value: float, lo: float, hi: float) -> float:
    return 0.0 if hi <= lo else min(100.0, max(0.0, (value - lo) / (hi - lo) * 100))


def block(p: dict | None) -> str:
    if not p:
        return ""
    low, mid, high, last = (float(p[k]) for k in ("low", "mid", "high", "last"))
    pad = (max(high, last) - min(low, last)) * 0.06
    lo, hi = min(low, last) - pad, max(high, last) + pad
    a, b, m, t = (_pos(v, lo, hi) for v in (low, high, mid, last))
    return f"""<div class="predict" data-predict>
<div class="predict-title">{LABEL} <span class="muted">({e(p.get("model", "TimesFM 2.5"))})</span> <span class="muted">· one month out</span></div>
<div class="predict-bar" role="img" aria-label="Range {e(f"${money(low)} to ${money(high)}")}, middle {e(f"${money(mid)}")}, today {e(f"${money(last)}")}">
<span class="predict-range" style="left:{a:.1f}%;width:{max(b - a, 0.5):.1f}%"></span>
<span class="predict-mid" style="left:{m:.1f}%"></span><span class="predict-now" style="left:{t:.1f}%"></span></div>
<div class="predict-nums"><span>{e(f"${money(low)}")} <span class="muted">low</span></span><span><b>{e(f"${money(mid)}")}</b> <span class="muted">middle</span></span>
<span>{e(f"${money(high)}")} <span class="muted">high</span></span></div>
<div class="predict-note muted">Dark tick marks today, {e(f"${money(last)}")}. A projection, not a promise.</div>
<div class="predict-verdict">{e(p.get("verdict", ""))}</div></div>"""
