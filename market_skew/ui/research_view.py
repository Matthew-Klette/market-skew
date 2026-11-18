"""The Research tab: the Quality score board (every scored company) and one company's card. Reads saved scores only."""
from .. import breaking, sentinel
from . import levels_view, prediction_view, value_view
from .fmt import BUCKET_CLASS, e, money, pct, tone

EMPTY = ("No company numbers yet. They come from the SEC: add your email under Settings on the How it works tab, then run a scan; "
         "they download weekly after that.")
LABEL_CLASS = {"WATCH": "fresh", "OK": "crowded", "PASS": "tighten"}
NOT_ENOUGH = "not enough filings"
STREET_NOTE = ("We have no free analyst data for thousands of companies, so this pillar is a stand-in: how the price did against its "
               "sector over three months, and which way the options market is leaning.")


def big(value) -> str:
    if value is None:
        return "–"
    sign, v = ("-" if value < 0 else ""), abs(value)
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if v >= size:
            return f"{sign}${v / size:,.1f}{suffix}"
    return f"{sign}${v:,.0f}"


def _arrow(row: dict) -> str:
    if row["accelerating"] is None:
        return ""
    return '<span class="up" title="growth is speeding up">▲</span>' if row["accelerating"] else '<span class="down" title="growth is slowing">▼</span>'


def _delta(change) -> str:
    if change is None:
        return '<span class="muted delta">new</span>'
    return f'<span class="delta {tone(change, 0.5)}">{change:+d}</span>' if change else '<span class="muted delta">±0</span>'


def chip(entry: dict | None, symbol: str) -> str:
    """'Quality score 76 → 56' for a Picks card, linking to the company's card. Nothing when the company has no score."""
    if not entry:
        return ""
    raw, now = entry.get("raw"), entry["score"]
    text = f"{raw} → {now}" if raw not in (None, now) else str(now)
    unchecked = ' <span class="muted">not yet checked by Claude</span>' if entry.get("checked") is False else ""
    return (f'<a class="sentinel-chip" href="/research/{e(symbol)}" title="Quality score after Claude\'s counter-argument. Open the company card.">'
            f'Quality score {e(text)}</a>{unchecked}')


def _was(row: dict) -> str:
    """The raw score as a small strikethrough, only when Claude took points off."""
    return f' <s class="was muted" title="before Claude\'s deductions">{row["raw_score"]}</s>' if row.get("raw_score") not in (None, row["score"]) else ""


def _score_bar(row: dict) -> str:
    return f'<span class="sbar{" thin" if row["thin"] or row["gaps"] else ""}"><span style="width:{row["score"]}%"></span></span>'


def _history_cell(row: dict) -> str:
    own = row["own_history_pct"]
    if own is None:
        return '<span class="muted">–</span>'
    return f'<span class="{"up" if own <= -0.10 else "down" if own >= 0.10 else "flat"}">{own * 100:+.0f}% {e(row["own_history_label"])}</span>'


def _chip(text: str, key: str, count: int | None = None, on: bool = False) -> str:
    n = f' <span class="muted">{count}</span>' if count is not None else ""
    return f'<button type="button" class="chip-filter" aria-pressed="{"true" if on else "false"}" data-filter="{e(key)}">{e(text)}{n}</button>'


def _board_row(r: dict) -> str:
    cy, gap = r["cash_yield"], r["vs_sector_1m"]
    grey = r["thin"] or bool(r["gaps"])
    why = NOT_ENOUGH if r["thin"] else f'missing numbers: {", ".join(r["gaps"])}'
    thin_attr = f' class="thin" title="{e(why)}"' if grey else ""
    return (
        f'<tr data-bucket="{e(r["label"])}" data-sector="{e(r["sector"])}" data-symbol="{e(r["symbol"])}" data-name="{e(r["name"].upper())}">'
        f'<td data-v="{r["rank"]}" class="muted">{r["rank"]}</td>'
        f'<td data-v="0"><a class="tlink" href="/research/{e(r["symbol"])}"><b>{e(r["symbol"])}</b></a> {f'<span class="muted">{e(r["name"])}</span>' if r["name"] != r["symbol"] else ""}'
        f'<div class="leaders">{big(r["market_cap"])} · {e(r["sector"])}</div></td>'
        f'<td data-v="{r["score"]}"{thin_attr}>'
        f'{_score_bar(r)} <b>{r["score"]}</b>{_was(r)} {_delta(r["change"])}'
        f'{f"<div class=leaders>{e(why)}</div>" if grey else ""}</td>'
        f'<td data-v="{r["growth"] if r["growth"] is not None else -9}">{pct(r["growth"], False, 0)} {_arrow(r)}</td>'
        f'<td data-v="{cy if cy is not None else -9}">{pct(cy, False)}</td>'
        f'<td data-v="{r["own_history_pct"] if r["own_history_pct"] is not None else 9}">{_history_cell(r)}</td>'
        f'<td data-v="{gap if gap is not None else 0}">{e(r["together"] or "–")}</td>'
        f'<td data-v="{value_view.sort_key(r)}">{value_view.cell(r)}</td>'
        f'<td data-v="{["Thin", "Medium", "Deep"].index(r["depth"])}">{e(r["depth"])}</td></tr>')


def board(rows: list[dict]) -> str:
    if not rows:
        return f'<section class="empty"><h2>Research</h2><p>{e(EMPTY)}</p></section>'
    counts = {k: sum(r["label"] == k for r in rows) for k in LABEL_CLASS}
    sectors = sorted({r["sector"] for r in rows})
    chips = _chip("All", "all", len(rows), True) + "".join(_chip(k, k, counts[k]) for k in LABEL_CLASS)
    select = ('<label class="select"><span class="sr-only">Sector</span><select data-sector><option value="">All sectors</option>'
              + "".join(f'<option value="{e(s)}">{e(s)}</option>' for s in sectors) + "</select></label>")
    head = ('<tr><th data-sort="num" aria-sort="ascending">#</th><th data-sort="text">Company</th><th data-sort="num">Score</th>'
            '<th data-sort="num">Sales growth</th><th data-sort="num">Cash yield</th><th data-sort="num">Price vs own history</th>'
            '<th data-sort="num">1M vs sector</th><th data-sort="num">Price vs range</th><th data-sort="num">Depth</th></tr>')
    body = "".join(_board_row(r) for r in rows)
    return f"""<section class="block"><div class="block-head"><h2>The Board</h2>
<span class="hint">Every company with SEC numbers, best score first. A place to look, not a buy list. Click a heading to sort.</span></div>
<div class="filters"><div class="chips" role="group" aria-label="Filter by label">{chips}</div>
<div class="filter-right">{select}<label class="search"><span class="sr-only">Find a company</span><input type="search" placeholder="Find a company" data-search autocomplete="off" spellcheck="false"></label></div></div>
<div class="table-wrap"><table class="data sortable stocks board">{head}<tbody>{body}</tbody></table></div>
<p class="hint">{len(rows):,} companies. WATCH is 80 and up, OK 65 to 79, PASS below 65. Greyed scores rest on too few filings to trust. Market's view is a proxy (see How it works).</p></section>"""


def _tile(label: str, value: str, notes: list[str]) -> str:
    return (f'<div class="tile"><div class="tile-label">{e(label)}</div><div class="tile-value">{value}</div>'
            + "".join(f'<div class="tile-note">{n}</div>' for n in notes) + "</div>")


def _tiles(r: dict) -> str:
    m, g = r["metrics"], r["growth"]
    rank = {p["key"]: p for p in r["pillars"]["protected"]["parts"]}["sector_rank"]["pts"]
    cents = None if m.get("fcf_margin") is None else m["fcf_margin"] * 100
    debt = m.get("debt_to_fcf")
    growing = _tile("Is it growing?", f'{pct(g, False, 0)}', [
        f"sales, year on year {_arrow(r)}" + (f" (a year ago {pct(r['growth_prior'], False, 0)})" if r["growth_prior"] is not None else ""),
        f"free cash per share {pct(m.get('fcf_per_share_growth'))}"])
    keeps = _tile("Does it keep cash?", "–" if cents is None else f"{cents:.0f}¢", [
        "of every $1 of sales becomes free cash",
        f"better than {rank / 5 * 100:.0f}% of {e(r['sector'])} peers" if rank is not None else "no sector rank (too few peers)"])
    paying = _tile("What are you paying?", pct(r["cash_yield"], False), [
        f"free cash yield against {r['treasury'] * 100:.1f}% on 10-year Treasuries" + (
            "" if r["beats_treasury"] is None else (" (above)" if r["beats_treasury"] else " (below)")),
        "pays " + ("–" if r["pfcf"] is None else f"{r['pfcf']:.0f}x") + " its yearly free cash"])
    net = m.get("net_cash")
    survive = _tile("Can it survive?", big(net), [
        "net cash" if net is not None and net >= 0 else "net debt (cash minus debt)",
        "debt is " + ("–" if debt is None else f"{debt:.1f} years") + " of free cash"])
    return f'<section class="tiles four">{growing}{keeps}{paying}{survive}</section>'


def _pillars(r: dict) -> str:
    out = []
    for key, p in r["pillars"].items():
        parts = "".join(
            f'<li><span>{e(x["label"])}</span><span class="muted">{"no data" if x["pts"] is None else f"{x["pts"]:g}"} / {x["max"]}</span></li>'
            for x in p["parts"])
        note = f'<p class="hint">{e(STREET_NOTE)}</p>' if key == "street" else ""
        out.append(f'<div class="pillar"><div class="pillar-head"><span>{e(p["label"])}</span><b>{p["pts"]} <span class="muted">/ {p["max"]}</span></b></div>'
                   f'<div class="pillar-track"><span style="width:{p["pts"] / p["max"] * 100:.0f}%"></span></div>'
                   f'<details><summary>What counted</summary><ul class="parts">{parts}</ul>{note}</details></div>')
    return f'<section class="block"><div class="block-head"><h2>The four pillars</h2><span class="hint">Added up, they make the score out of 100.</span></div><div class="pillars">{"".join(out)}</div></section>'


def _checks(r: dict) -> str:
    peg = "–" if r["peg"] is None else f'{r["peg"]:.1f} <span class="muted">({e(r["peg_label"])}; 1 or less is cheap for its growth)</span>'
    peer = "–" if r["peer_pct"] is None else f'{r["peer_pct"] * 100:+.0f}% {e(r["peer_label"])} <span class="muted">against the sector median</span>'
    rows = [
        ("Cash yield vs Treasuries", f'{pct(r["cash_yield"], False)} against {r["treasury"] * 100:.1f}%'),
        ("Price vs growth", f"price ÷ yearly free cash, divided by growth: {peg}"),
        ("Vs its own history", _history_cell(r) + ' <span class="muted">price per $1 of yearly cash against its own median</span>'),
        ("Vs sector peers", peer),
        ("Last month", e(r["together"] or "–") + ' <span class="muted">against its sector</span>')]
    items = "".join(f"<tr><th scope='row'>{e(k)}</th><td>{v}</td></tr>" for k, v in rows)
    return (f'<section class="block"><div class="block-head"><h2>Priced fair?</h2><span class="hint">Shown beside the score; not part of the 100.</span></div>'
            f'<div class="table-wrap"><table class="data checks"><tbody>{items}</tbody></table></div></section>')


def chart(row: dict) -> str:
    """What $1 of its yearly free cash costs, year by year, with today's price as the last point. Inline SVG, no libraries."""
    points = [(h["year"], h["pfcf"]) for h in row["history"]]
    if row["pfcf"]:
        points.append(("now", row["pfcf"]))
    if len(row["history"]) < 3 or len(points) < 4:
        return '<p class="hint">Needs at least three years of prices and free cash to draw this.</p>'
    w, h, left, bottom = 640, 220, 44, 28
    top = max(p[1] for p in points) * 1.15
    x = lambda i: left + i * (w - left - 16) / (len(points) - 1)
    y = lambda v: 12 + (h - 12 - bottom) * (1 - v / top)
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    med = row["median_pfcf"]
    dots = "".join(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="{5 if k == "now" else 3.5}" class="{"now" if k == "now" else ""}"><title>{e(k)}: ${v:,.1f}</title></circle>'
                   f'<text x="{x(i):.1f}" y="{h - 8}" text-anchor="middle">{e(k)}</text>' for i, (k, v) in enumerate(points))
    label = f"Price per $1 of yearly free cash, {points[0][0]} to now. Median ${med:,.1f}, now ${row['pfcf']:,.1f}."
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}">'
            f'<line class="median" x1="{left}" x2="{w - 16}" y1="{y(med):.1f}" y2="{y(med):.1f}"/>'
            f'<text x="{left - 6}" y="{y(med) + 4:.1f}" text-anchor="end" class="axis">${med:,.0f}</text>'
            f'<polyline points="{line}" class="line"/>{dots}</svg>')


def _chart_block(r: dict) -> str:
    return (f'<section class="block"><div class="block-head"><h2>What $1 of its yearly cash costs</h2>'
            f'<span class="hint">Price divided by free cash per share, each year-end, against its own median (dashed).</span></div>{chart(r)}</section>')


def _breaks(r: dict) -> str:
    b = r.get("breaking")
    if not b:
        return ('<div class="breaks"><h3>What breaks this call</h3><p class="muted">Claude has not argued against this company yet. '
                'It runs after each scan for the names on your screen.</p></div>')
    items = "".join(f'<li><b class="down">-{d["points"]}</b> {e(d["reason"])}</li>' for d in b["deductions"])
    lines = (f'<ul class="deductions">{items}</ul>' if items else '<p class="muted">Claude found nothing in the numbers to take points off for.</p>')
    what = f'<p class="what-breaks">{e(b["what_breaks"])}</p>' if b.get("what_breaks") else ""
    return (f'<div class="breaks"><h3>What breaks this call</h3>{what}{lines}'
            f'<p class="hint">Score {r["raw_score"]} minus {b["total"]} = {r["score"]}. {e(breaking.NOTE)}</p></div>')


def _headline(r: dict) -> str:
    return e(breaking.headline(r))


def card(r: dict, report: dict | None) -> str:
    pred = ((report or {}).get("predictions") or {}).get(r["symbol"])
    bucket = r.get("bucket")
    read = "".join(f"<p><b>{e(s.split(':', 1)[0])}</b>{e(':' + s.split(':', 1)[1])}</p>" for s in r["summary"])
    flags = "".join(f"<li>{e(f)}</li>" for f in r["flags"])
    thin = (f'<p class="notice">{NOT_ENOUGH.capitalize()}: only {r["metrics"].get("quarters", 0)} quarters and {r["metrics"].get("years", 0)} years of '
            "numbers, so treat this score as a rough sketch.</p>") if r["thin"] else (
        f'<p class="notice">Missing numbers for: {e(", ".join(r["gaps"]))}. That part scores 0, so the total is understated.</p>' if r["gaps"] else "")
    skew = (f'<p class="hint">Options market today: <span class="action {BUCKET_CLASS.get(bucket, "")}">{e(bucket)}</span></p>' if bucket else "")
    return f"""<p class="crumb"><a href="/research">‹ The Board</a></p>
<section class="card-head"><div><h2 class="card-title">{e(r["symbol"])} <span class="muted">{e(r["name"])}</span></h2>
<div class="leaders">{e(r["sector"])} · {big(r["market_cap"])} · numbers to {e(r["as_of"])} · {e(r["depth"])} data{f" · {pct(r['ret_1m'])} this month" if r["ret_1m"] is not None else ""}</div></div>
<div class="score-box{" thin" if r["thin"] or r["gaps"] else ""}"><div class="score-big">{_headline(r)}<span class="muted"> / 100</span></div>
<span class="action {LABEL_CLASS[r["label"]]}">{e(r["label"])}</span> {_delta(r["change"])}</div></section>{thin}
<section class="callouts">{_breaks(r)}
<div class="read"><h3>Read this first</h3>{read}</div></section>
{_tiles(r)}{_pillars(r)}{_checks(r)}{value_view.block(r)}{_chart_block(r)}
{f'<section class="block"><div class="block-head"><h2>Flags</h2></div><ul class="prose">{flags}</ul></section>' if flags else ""}
<section class="block"><div class="block-head"><h2>Beyond the numbers</h2></div>{levels_view.block(r["symbol"], report or {}, "research", ((report or {}).get("last_buys") or {}).get(r["symbol"]))}{prediction_view.block(pred) or '<p class="hint">No price prediction for this name.</p>'}{skew}
<p class="hint">This alone is not a buy: it says whether a company looks attractive, not when to get in. For your own research. Not financial advice.</p></section>"""


def missing(symbol: str) -> str:
    return (f'<p class="crumb"><a href="/research">‹ The Board</a></p><section class="empty"><h2>{e(symbol)}</h2>'
            f'<p>No company numbers for this ticker yet. {e(EMPTY)}</p></section>')


def page(rows: list[dict], report: dict | None, symbol: str | None) -> str:
    if symbol is None:
        return board(rows)
    found = next((r for r in rows if r["symbol"] == symbol), None)
    return card(found, report) if found else missing(symbol)


HOW = f"""<section class="block prose"><h2>Quality score</h2>
<p>The Research tab scores each company out of 100 from its filings with the SEC (company numbers download weekly) and the scan's prices.
It answers three questions: is it a good business, is the price fair, and what could break it. It says whether a company looks
attractive. It never says when to buy; the options reading on the other tabs is for timing.</p>
<h3>Is the business growing? (35 points)</h3><ul>
<li><b>Sales growth, 12:</b> last twelve months against the year before. 0% scores 0, 25% or more scores all 12.</li>
<li><b>Speeding up, 9:</b> growth now minus growth a year ago. "30% sounds great until last year was 50": 10 points slower scores 0, 10 faster scores 9, level scores 4.5.</li>
<li><b>Free cash per share growth, 8:</b> 0% scores 0, 20% or more scores 8.</li>
<li><b>Not diluting, 6:</b> share count change over a year. Buying shares back (2.5% fewer) scores 6, flat scores 4, 5% more shares scores 0.</li></ul>
<h3>How protected is it? (25 points)</h3><ul>
<li><b>Gross margin, 8:</b> 60% or more scores 8.</li>
<li><b>Free cash margin, 8:</b> cents of free cash kept from each $1 of sales (operating cash flow minus capex, over sales). 25 cents or more scores 8.</li>
<li><b>Rank in its sector, 5:</b> that margin against the other companies in its sector (needs five or more).</li>
<li><b>Capex against operating cash flow, 4:</b> spending half or less of what the business makes scores 4; spending as much or more scores 0 and is flagged as "spending more than it makes".</li></ul>
<h3>Can it survive being wrong? (25 points)</h3><ul>
<li><b>Net cash, 10:</b> more cash than debt scores 10; net debt of half a year of sales or more scores 0.</li>
<li><b>Debt against free cash, 9:</b> paid off in one year of free cash or less scores 9, six years or more scores 0.</li>
<li><b>Free cash is positive, 6.</b></li></ul>
<h3>Market's view, a proxy (15 points)</h3>
<p>In the public checklist this score follows, this is what Wall Street analysts think. There is no free analyst data for thousands of companies, so this app uses a stand-in:
<b>three-month price against its sector's median (8)</b> and <b>which way the options market is leaning (7)</b>, the same bet score used on the Stocks tab.
It is labelled "Market's view (proxy)" everywhere. It is not analyst opinion.</p>
<h3>Labels, depth and change</h3>
<p>Our own bands: <b>WATCH</b> 80 or more, <b>OK</b> 65 to 79, <b>PASS</b> below 65. When a number is missing, that part is left out and the pillar is scaled up
from the rest (a pillar with under 40% of its points knowable scores 0, and the company is greyed with "missing numbers"). <b>Depth</b> counts the filings found: Deep is 8 quarters and 4 years or more, Medium 4 quarters or more,
otherwise Thin. Thin scores are greyed with "not enough filings". The small number beside a score is the change since the last stored run.</p>
<h3>Priced fair? (beside the score, not part of it)</h3><ul>
<li><b>Cash yield:</b> free cash over market value, against about {sentinel.TREASURY_10Y * 100:.1f}% on 10-year Treasuries (a fixed number in the code, update it when rates move).</li>
<li><b>Price vs growth:</b> price per $1 of yearly free cash, divided by sales growth in points. 1 or less is cheap for its growth, over 2 is rich.</li>
<li><b>Vs its own history:</b> price per $1 of yearly free cash now against its median over the years we have (needs three). 10% or more below is cheap, 10% or more above is rich.</li>
<li><b>Vs sector peers:</b> the same price per $1 of free cash against the sector's median. No earnings data is used, so this is not a P/E.</li>
<li><b>With sector or alone:</b> the stock's one-month return against its sector's median; a gap of 5 points or more is "alone".</li></ul>
<h3>What breaks this call</h3>
<p>After each scan, Claude (the small, fast model, on your own Claude plan) is asked to argue <i>against</i> every company on your screen using only the numbers on its card.
It returns up to six deductions of 1 to 10 points, 30 in total at most, each with a plain reason, plus one sentence on what would break the call.
The score is shown as "76 → 56" (raw, then adjusted) and the WATCH, OK and PASS labels follow the adjusted score. An answer is saved and only redone when
the company's numbers change. It reads the filed numbers, not news, so it cannot know about a lawsuit or a product recall.</p>
{value_view.HOW}
<p class="hint">Company numbers come from SEC filings and tag differently by company; foreign filers without US-GAAP numbers have no score.</p></section>"""
