"""One-year price chart with the candidate buy levels as dashed lines, plus the levels, add-on and earnings lines.
Inline SVG, no libraries; reads only what the scan saved. Candidate areas to watch, not buy signals."""
import datetime as dt

from .. import earnings, levels
from .fmt import e, money

NOTE = "Candidate areas where the price has stopped before, not buy signals. Add in pieces."


def _svg(symbol: str, where: str, data: dict, last_buy: float | None, compact: bool) -> str:
    closes, found, last = data["closes"], data.get("levels") or [], data["last"]
    w, h = (240, 64) if compact else (360, 120)
    pad_l, pad_r, pad_t, pad_b = 4, 46, 8, 8
    marks = [x["level"] for x in found] + ([last_buy] if last_buy else [])
    lo, hi = min(closes + marks), max(closes + marks)
    span = (hi - lo) or 1.0
    x = lambda i: pad_l + i * (w - pad_l - pad_r) / max(len(closes) - 1, 1)
    y = lambda v: pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / span)
    step = max(1, len(closes) // 120)
    pts = [*range(0, len(closes), step), len(closes) - 1]
    line = " ".join(f"{x(i):.1f},{y(closes[i]):.1f}" for i in dict.fromkeys(pts))
    guides = "".join(
        f'<line class="lv-floor" x1="{pad_l}" x2="{w - pad_r}" y1="{y(f["level"]):.1f}" y2="{y(f["level"]):.1f}"/>'
        f'<text class="lv-label" x="{w - pad_r + 4}" y="{y(f["level"]) + 3.5:.1f}">${e(money(f["level"]))}</text>' for f in found)
    if last_buy:
        guides += (f'<line class="lv-buy" x1="{pad_l}" x2="{w - pad_r}" y1="{y(last_buy):.1f}" y2="{y(last_buy):.1f}"/>'
                   f'<text class="lv-label" x="{w - pad_r + 4}" y="{y(last_buy) + 3.5:.1f}">your buy</text>')
    levels_text = (", ".join(f"${money(f['level'])}" for f in found) + ".") if found else "none found."
    title = f"{symbol}: one year of closing prices"
    desc = (f"Line chart from {data['start']} to {data['end']}, ending at ${money(last)} today. "
            f"Candidate levels, shown as dashed lines: {levels_text}")
    tid, did = f"lv-t-{e(symbol)}-{where}", f"lv-d-{e(symbol)}-{where}"
    return (f'<svg class="lv-chart{" compact" if compact else ""}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="{tid} {did}">'
            f'<title id="{tid}">{e(title)}</title><desc id="{did}">{e(desc)}</desc>{guides}'
            f'<polyline class="lv-line" points="{line}"/>'
            f'<circle class="lv-now" cx="{x(len(closes) - 1):.1f}" cy="{y(last):.1f}" r="3"/>'
            f'<text class="lv-label now" x="{w - pad_r + 4}" y="{y(last) + 3.5:.1f}">${e(money(last))}</text></svg>')


def _lines(found: list[dict], last_buy: float | None) -> str:
    out = []
    if found:
        text = " and ".join(f"<b>${e(money(f['level']))}</b> <span class=\"muted\">({f['touches']} touches, {f['distance_pct']:.0f}% below)</span>"
                            for f in found)
        out.append(f"<div>Candidate areas to add: {text}</div>")
    else:
        out.append('<div class="muted">No clear floor 5% to 40% below today.</div>')
    nxt = levels.next_add(last_buy)
    if nxt is not None:
        out.append(f'<div>Next add only below <b>${e(money(nxt))}</b> <span class="muted">(5% under your last buy, ${e(money(last_buy))})</span></div>')
    return "".join(out)


def earnings_line(result: dict | None, today: dt.date | None = None) -> str:
    """The earnings sentence, with a flag when the report is within two weeks. Empty for funds and names with no data."""
    if not result or result.get("kind") == "fund":
        return ""
    flag = ' <span class="action tighten lv-soon">Earnings within 2 weeks</span>' if earnings.soon(result.get("next_date"), today) else ""
    return f'<div class="lv-earn">{e(earnings.line(result))}{flag}</div>'


def block(symbol: str, report: dict, where: str, last_buy: float | None = None, compact: bool = False,
          today: dt.date | None = None) -> str:
    """Empty when the scan saved no closes for this name."""
    data = (report.get("levels") or {}).get(symbol)
    if not data or not data.get("closes"):
        return ""
    result = (report.get("earnings") or {}).get(symbol)
    text = "" if compact else f'<div class="lv-text">{_lines(data.get("levels") or [], last_buy)}<div class="hint">{e(NOTE)}</div></div>'
    short = ""
    if compact:
        found = data.get("levels") or []
        nxt = levels.next_add(last_buy)
        bits = ([f"Areas: {', '.join('$' + money(f['level']) for f in found)}"] if found else []) + ([f"next add below ${money(nxt)}"] if nxt else [])
        short = f'<div class="lv-text muted">{e(" · ".join(bits))}</div>' if bits else ""
    return f'<div class="lv" data-levels="{e(symbol)}">{_svg(symbol, where, data, last_buy, compact)}{text}{short}{earnings_line(result, today)}</div>'
