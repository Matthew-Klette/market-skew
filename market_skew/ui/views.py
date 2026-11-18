"""Server-rendered pages. Every number on screen comes straight from the saved report; nothing is recalculated here."""
from .. import gate, prediction, system
from . import levels_view, plan_view, prediction_view, research_view, swing_view
from .fmt import BUCKET_CLASS, count, cp_ratio, e, money, pct, tone, ticker_link

TABS = [("picks", "/", "Picks"), ("money", "/money", "Money"), ("overview", "/market", "Market"), ("research", "/research", "Research"), ("stocks", "/stocks", "Stocks"), ("backtest", "/backtest", "Track record"),
        ("how", "/how", "How it works")]
BUCKETS = ["Contrarian Bid", "Chase", "Hedged Rally", "Fear"]


def shell(view: str, title: str, body: str, report: dict | None, dates: list[str], token: str, theme: str,
          status: dict) -> str:
    tabs = "".join(f'<a href="{href}{_q(report, dates)}"{" aria-current=page" if key == view else ""}>{label}</a>'
                   for key, href, label in TABS)
    return f"""<!doctype html><html lang="en" data-theme="{e(theme)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="skew-token" content="{e(token)}">
<title>{e(title)} · Market Skew</title><link rel="stylesheet" href="/app.css"><script src="/app.js" defer></script></head>
<body data-view="{e(view)}" data-date="{e(report['date'] if report else '')}">
<header class="top">
  <div class="brand">Market Skew</div>
  {_date_nav(view, report, dates)}
  <div class="sync">{_run_box(status, report)}
    <button class="quiet theme-toggle" type="button" data-theme-next aria-label="Switch light or dark">{'Light' if theme == 'dark' else 'Dark' if theme == 'light' else 'Light or dark'}</button></div>
</header>
<nav class="tabs" aria-label="Pages">{tabs}</nav>
<main>{_progress(status)}{body}</main>
{_chat()}
</body></html>"""


def _q(report, dates) -> str:
    return f"?date={report['date']}" if report and dates and report["date"] != dates[0] else ""


def _date_nav(view: str, report: dict | None, dates: list[str]) -> str:
    if not report:
        return '<div class="months"><h1>No report yet</h1></div>'
    i = dates.index(report["date"]) if report["date"] in dates else 0
    path = dict((k, h) for k, h, _ in TABS)[view]
    older = f'<a class="nav-arrow" href="{path}?date={dates[i + 1]}" aria-label="Older report">‹</a>' if i + 1 < len(dates) else '<span class="nav-arrow off">‹</span>'
    newer = f'<a class="nav-arrow" href="{path}?date={dates[i - 1]}" aria-label="Newer report">›</a>' if i > 0 else '<span class="nav-arrow off">›</span>'
    return f'<div class="months">{older}<h1>{e(report["date"])}</h1>{newer}</div>'


def _run_box(status: dict, report: dict | None) -> str:
    running = status.get("state") == "running"
    done, total = status.get("done", 0), status.get("total", 0)
    progress = f"{status.get('step', '')} {done}/{total}" if running and total else status.get("step", "") if running else ""
    built = f"Built {e(report['built_at'][11:16])} · {report['with_skew']:,} names" if report else "Never run"
    failed = ' <span class="synced bad">Last run failed: ' + e(status.get("step", "")) + "</span>" if status.get("state") == "failed" else ""
    return (f'<span class="synced" data-run-status>{e(progress) if running else built}</span>{failed}'
            f'<button type="button" data-run{" disabled" if running else ""}>{"Scanning…" if running else "Run now"}</button>')


STAGES = {1: "Step 1 of 3 · Prices", 2: "Step 2 of 3 · Option bets", 3: "Step 3 of 3 · Retries"}


def _progress(status: dict) -> str:
    """A loader with time left. app.js keeps it moving; this is the first frame."""
    running = status.get("state") == "running"
    done, total = status.get("done", 0), status.get("total", 0)
    share = done / total if total else 0
    return f"""<section class="progress" data-progress{'' if running else ' hidden'} aria-live="polite">
<div class="progress-head"><span class="progress-stage" data-p-stage>{e("Step 3 of 3 · Google's prediction" if str(status.get('step', '')).startswith('Google') else STAGES.get(status.get('stage'), 'Starting'))}</span>
<span class="progress-eta" data-p-eta>{_eta(status.get('eta'))}</span></div>
<div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{share * 100:.0f}" data-p-bar>
<span class="progress-fill" style="width:{share * 100:.1f}%"></span></div>
<div class="progress-note" data-p-note>{e(status.get('step', ''))}{f' · {done:,} of {total:,}' if total else ''}</div>
<p class="hint">Runs only while the app is open. Close it and it stops; it picks up next time.</p></section>"""


def _eta(seconds) -> str:
    if not seconds:
        return "Working out time left…"
    if seconds < 60:
        return "Less than a minute left"
    return f"About {round(seconds / 60)} min left"


def empty_state() -> str:
    return """<section class="empty"><h2>No report yet</h2>
<p>Press <b>Run now</b>. The first run looks up every stock's sector once, then reads about 2,000 option chains.
Expect 15 to 30 minutes. After that it scans once per US trading day, the first time you open the app after the New York close, and only while the app is open.</p></section>"""


def overview(r: dict) -> str:
    tiles = "".join(_tile(t) for t in r["kpis"])
    read = "".join(f"<li>{e(line)}</li>" for line in r["read"])
    failed = f", {r['failed_count']} chains failed" if r.get("failed_count") else ""
    meta = (f"Universe: top {r['universe']:,} US stocks by 21-day dollar volume. Skew read for {r['with_skew']:,}{failed}. "
            f"Options expiry {e(r.get('expiry') or '–')}. Prices to the {e(r['date'])} close.")
    intraday = ('<p class="notice">Built while New York was still trading, so today\'s moves and volumes are partial. '
                'The evening run replaces it.</p>' if r.get("intraday") else "")
    return f"""<p class="meta">{meta}</p>{intraday}
<section class="tiles">{tiles}</section>
<section class="block"><div class="block-head"><h2>Today's read</h2><span class="hint">Written by fixed rules from the tables below, the same way every day.</span></div>
<ul class="read">{read}</ul></section>
<section class="block"><div class="block-head"><h2>Where money is flowing</h2><span class="hint">Themes, dollar-volume weighted, no name over 25%. Click a heading to sort.</span></div>
{group_table(r['themes'], 'Theme')}</section>
<section class="block"><div class="block-head"><h2>Sectors</h2><span class="hint">The 11 GICS sectors built from the same names.</span></div>
{group_table(r['sectors'], 'Sector', skew=True)}</section>
<section class="block"><div class="block-head"><h2>Weekly relative return</h2><span class="hint">Each sector ETF's week minus SPY's. Green beat the market, red lagged it.</span></div>
{heatmap(r['heatmap'])}</section>"""


def _tile(t: dict) -> str:
    if t["kind"] == "pct":
        value = f'<span class="{tone(t["value"])}">{pct(t["value"])}</span>'
    elif t["kind"] == "pct_plain":
        value = pct(t["value"], signed=False)
    else:
        value = e(t["value"])
    return f'<div class="tile"><div class="tile-label">{e(t["label"])}</div><div class="tile-value">{value}</div><div class="tile-note">{e(t["note"])}</div></div>'


def _bar(value: float, scale: float) -> str:
    width = min(abs(value) / scale, 1) * 50 if scale else 0
    side = "right" if value >= 0 else "left"
    return f'<span class="bar"><span class="bar-fill {tone(value)}" style="--w:{width:.1f}%;--side:{side}"></span></span>'


def group_table(rows: list[dict], label: str, skew: bool = False) -> str:
    if not rows:
        return '<p class="hint">Not enough names yet.</p>'
    scale = max(abs(r["rel_1m"]) for r in rows) or 1
    head = (f'<tr><th data-sort="text">{label}</th><th data-sort="num" aria-sort="descending">1M vs SPY</th><th data-sort="num">1W vs SPY</th>'
            f'<th data-sort="num">Today</th><th data-sort="num">Vol today</th><th data-sort="text">Trend</th>'
            f'<th data-sort="num">$ flow</th><th data-sort="num">Breadth</th>{"<th data-sort=num>Skew</th>" if skew else ""}</tr>')
    body = []
    for r in rows:
        trend = "▲ improving" if r["trend"] == "improving" else "▼ fading"
        body.append(
            f'<tr><td><b>{e(r["name"])}</b> <span class="muted">{r["count"]}</span><div class="leaders">{e(", ".join(r["leaders"]))}</div></td>'
            f'<td data-v="{r["rel_1m"]:.6f}">{_bar(r["rel_1m"], scale)}<span class="{tone(r["rel_1m"])}">{pct(r["rel_1m"])}</span></td>'
            f'<td data-v="{r["rel_1w"]:.6f}" class="{tone(r["rel_1w"])}">{pct(r["rel_1w"])}</td>'
            f'<td data-v="{r["today"]:.6f}" class="{tone(r["today"])}">{pct(r["today"])}</td>'
            f'<td data-v="{r["vol_today"]:.4f}">{r["vol_today"]:.1f}×</td>'
            f'<td class="{"up" if r["trend"] == "improving" else "down"}">{trend}</td>'
            f'<td data-v="{r["flow_bps"]:.4f}">{r["flow_bps"]:+.1f} bps</td>'
            f'<td data-v="{r["breadth"]:.4f}">{pct(r["breadth"], False, 0)}</td>'
            + (f'<td data-v="{r["skew"]:.6f}">{pct(r["skew"], False)}</td>' if skew else "") + "</tr>")
    return f'<div class="table-wrap"><table class="data sortable"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def heatmap(h: dict) -> str:
    if not h or not h.get("rows"):
        return '<p class="hint">Not enough weeks yet.</p>'
    weeks = h["weeks"]
    head = "<tr><th></th>" + "".join(f"<th>{e(w)}{'<br><span class=muted>newest</span>' if i == len(weeks) - 1 else ''}</th>" for i, w in enumerate(weeks)) + "<th>1M rel</th></tr>"
    rows = []
    for name, values in sorted(h["rows"].items(), key=lambda kv: -h["rel_1m"].get(kv[0], 0)):
        cells = "".join(f'<td class="heat" style="--a:{min(abs(v) / 0.06, 1):.2f}" data-tone="{tone(v)}">{pct(v)}</td>' for v in values)
        m = h["rel_1m"].get(name, 0)
        rows.append(f'<tr><th scope="row">{e(name)}</th>{cells}<td class="{tone(m)}"><b>{pct(m)}</b></td></tr>')
    return f'<div class="table-wrap"><table class="data heatmap">{head}{"".join(rows)}</table></div>'


def stocks(r: dict) -> str:
    counts = r.get("buckets", {})
    chips = ['<button type="button" class="chip-filter" aria-pressed="true" data-filter="all">All</button>']
    chips += [f'<button type="button" class="chip-filter" aria-pressed="false" data-filter="{e(b)}">{e(b)} <span class="muted">{counts.get(b, 0)}</span></button>' for b in BUCKETS]
    chips.append('<button type="button" class="chip-filter" aria-pressed="false" data-filter="watch">★ Watchlist</button>')
    rows = []
    for s in r["stocks"]:
        cls = BUCKET_CLASS.get(s["bucket"], "")
        rows.append(
            f'<tr data-bucket="{e(s["bucket"])}" data-watch="{1 if s["watch"] else 0}" data-symbol="{e(s["symbol"])}">'
            f'<td><button type="button" class="star" aria-pressed="{"true" if s["watch"] else "false"}" aria-label="Watch {e(s["symbol"])}" data-star="{e(s["symbol"])}">★</button></td>'
            f'<td><b>{ticker_link(s["symbol"])}</b><div class="leaders">{e(s["sector"])}</div></td>'
            f'<td><span class="action {cls}">{e(s["action"])}</span></td>'
            f'<td data-v="{s["asym"]}"><b>{s["asym"]}</b></td>'
            f'<td data-v="{s["close"]}">{money(s["close"])}</td>'
            f'<td data-v="{s["ret_1d"]:.6f}" class="{tone(s["ret_1d"])}">{pct(s["ret_1d"])}</td>'
            f'<td data-v="{s["ret_1w"]:.6f}" class="{tone(s["ret_1w"])}">{pct(s["ret_1w"])}</td>'
            f'<td data-v="{s["ret_1m"]:.6f}" class="{tone(s["ret_1m"])}">{pct(s["ret_1m"])}</td>'
            f'<td data-v="{s["skew"]:.6f}">{pct(s["skew"], False)}</td>'
            f'<td data-v="{s["atm"] or 0:.6f}">{pct(s["atm"], False, 0)}</td>'
            f'<td data-v="{(s["call_volume"] or 0) / max(s["put_volume"] or 0, 1):.4f}" title="{count(s["call_volume"])} calls / {count(s["put_volume"])} puts">{cp_ratio(s["call_volume"], s["put_volume"])}</td></tr>')
    head = ('<tr><th><span class="sr-only">Watch</span></th><th data-sort="text">Name</th><th data-sort="text">What to do</th>'
            '<th data-sort="num" aria-sort="descending">Asym</th><th data-sort="num">Price</th><th data-sort="num">Today</th>'
            '<th data-sort="num">1W</th><th data-sort="num">1M</th><th data-sort="num">Skew</th><th data-sort="num">ATM IV</th>'
            '<th data-sort="num">Call/put vol</th></tr>')
    return f"""<section class="block"><div class="block-head"><h2>Most asymmetric positioning first</h2>
<span class="hint">Asym ranks names where the options bets lean bullish against a weak or flat price, plus a bonus when a falling name bounced today. Bearish set-ups score 0; use the Fear and Hedged Rally filters for those. A place to look, not a call.</span></div>
<div class="filters"><div class="chips" role="group" aria-label="Filter by bucket">{"".join(chips)}</div>
<label class="search"><span class="sr-only">Find a ticker</span><input type="search" placeholder="Find a ticker" data-search autocomplete="off" spellcheck="false"></label></div>
<div class="table-wrap"><table class="data sortable stocks">{head}<tbody>{"".join(rows)}</tbody></table></div>
<p class="hint">Showing the top {len(r["stocks"]):,} by Asym plus your watchlist. Every name is in the saved data.</p></section>"""


def backtest(result: dict) -> str:
    blocks = []
    for horizon, h in result["horizons"].items():
        if not h["ready"]:
            blocks.append(f'<div class="horizon"><h3>{horizon} sessions later</h3><p class="hint">Needs {h["needs"]} more daily run{"s" if h["needs"] != 1 else ""}.</p></div>')
            continue
        rows = "".join(f'<tr><td>{e(x["group"])}</td><td>{x["n"]:,}</td><td class="{tone(x["mean"])}">{pct(x["mean"], digits=2)}</td><td>{pct(x["hit"], False, 0)}</td></tr>' for x in h["rows"])
        blocks.append(f'<div class="horizon"><h3>{horizon} sessions later <span class="muted">· {h["dates"]} start dates</span></h3>'
                      f'<table class="data"><tr><th>Group</th><th>Cases</th><th>Avg vs average stock</th><th>Beat the average</th></tr>{rows}</table></div>')
    return f"""<section class="block"><div class="block-head"><h2>Track record</h2>
<span class="hint">{result["days"]} daily run{"s" if result["days"] != 1 else ""} saved.</span></div>
<p class="prose">Old option chains are not free, so there is no ten-year backtest. Every daily run is kept instead, and this page checks
what each bucket did over the next week (about 5 sessions) and month (about 20) against the average stock in the universe on the same days. Treat any
result under about 60 start dates as noise.</p><div class="horizons">{"".join(blocks)}</div></section>"""


def settings_block(contact: str) -> str:
    return f"""<section class="block prose"><h2>Settings</h2>
<form data-settings><label>Email for SEC downloads <input type="email" name="sec_contact" maxlength="254" value="{e(contact)}" autocomplete="email"></label>
<button type="submit">Save</button> <span class="hint" data-settings-status></span></form>
<p class="hint">sec.gov requires a contact address from automated downloads of company filings. It is stored only on this {system.DEVICE} and sent only to sec.gov.</p></section>"""


def how(sec_contact: str = "") -> str:
    return settings_block(sec_contact) + research_view.HOW + """<section class="block prose"><h2>How it works</h2>
<p><b>Two inputs per stock.</b> Price is what already happened; it shows where the money has been. Options are what people are
willing to pay for next. When the two agree there is no edge. When they disagree, that is where to look.</p>
<h3>Price</h3><p>One-month return minus SPY's, scaled by how spread out the whole universe is. Above zero beat the market.</p>
<h3>Options bets</h3><p>From the option expiry nearest 30 days out, each out-of-the-money option's implied volatility is solved from
its mid price (Yahoo's own figure is used only when quotes are empty), its delta is worked out with Black-Scholes, and the
25-delta put and 25-delta call are interpolated. <b>Skew</b> = (put IV − call IV) ÷ at-the-money IV. High skew means people are
paying for crash protection; low means they are paying for upside. The bet score combines skew against the sector's median,
skew against the stock's own last five readings (once there is history), and today's call/put volume at half weight.</p>
<h3>Four buckets</h3><ul>
<li><b>Contrarian Bid</b>: down, but call buyers are stepping in. Someone is betting on a bounce.</li>
<li><b>Fear</b>: down and put buyers agree. The market believes the drop.</li>
<li><b>Chase</b>: up and calls are bid. Trend confirmed, but crowded.</li>
<li><b>Hedged Rally</b>: up, but put protection is being bought. Nervous holders; a spot to tighten up on longs.</li></ul>
<p><b>Relative, not absolute.</b> The bet score is measured against the rest of the universe on the same day, so about half
the names always lean bullish. In a market-wide panic, "bullish" means "less scared than the rest". Index skew in the tiles is
the absolute read.</p>
<h3>Asym</h3><p>50 × (bet score − ½ × price score), plus 25 when a falling name was up on the day, floored at zero. It ranks
bullish-leaning set-ups only: every bearish name scores 0, so use the Fear and Hedged Rally filters for those.</p>
<h3>Where the data comes from</h3><p>Nasdaq's public stock list, Yahoo Finance prices and option chains. No account or key. Yahoo
quotes can be stale or thin for small names; those fall out rather than being guessed.</p>
<h3>The Picks method, in one flow</h3><ol>
<li><b>Quality.</b> The quality score says whether a company is attractive: growth, free cash, debt and how much filing history there is. A Quality score of @HIS@ or more is needed, and the score must not be marked Thin (too few filings to trust it).</li>
<li><b>Claude argues against it.</b> Claude makes the case against each company and takes points off. The score that counts is the one after that counter-argument. A score Claude has not checked yet counts at its raw score and is marked "not yet checked by Claude"; it is checked after the next scan or app open.</li>
<li><b>Timing from the options scan.</b> Attractive says what; the scan says when. Only a Contrarian Bid qualifies: down against the market this month while options bets lean bullish. The stock must also be liquid and not wild (share price $5+, $50M+ traded a day, implied volatility 100% a year or less, not down more than 35% in a month).</li>
<li><b>Buy levels, in pieces.</b> Each pick shows price levels where the stock has stopped and bounced before. Buy in pieces down that ladder instead of all at once.</li>
<li><b>Stop, target and a time limit.</b> <b>Sell if below</b> is the bigger of 4% or 1.2 times the move options expect over two weeks. <b>Take profit at</b> is twice that distance above the entry. If neither is hit, give it until the date shown (28 days).</li>
<li><b>Earnings guard.</b> A company reporting within 7 days is not offered; the card says "Wait until after results". A missing date never blocks, it just says it is unknown.</li></ol>
<p>If no company passes, the page says so and shows the three closest candidates and what kept each out. They are not picks.</p>
<h3>Your plan</h3><p>Your plan this month is the recommendation built from all of it. Of the USD money, QQQ, SCHD and VOO each get at least 15%, and what is left above that leans towards the funds whose options signal says it is a good time to add. Single stocks get 30%, split across the top two Picks; with no Picks, that 30% goes back to the funds. VOOG gets nothing new. The TFSA money goes to the Sygnia S&amp;P 500 fund. Nothing is bought for you.</p>
<h3>Track record of the picks</h3><p>Each pick joins a paper record the day it is first picked and settles when it hits its stop, its target or its time limit. Results are after EasyEquities fees and shown next to VOO over the same stretch. If the picks don't beat VOO over a few months, keep it simple and stay in the index fund.</p>
<p class="hint">For your own research. Not financial advice.</p></section>""".replace("@HIS@", str(gate.HIS_WAY_MIN))


def _chat() -> str:
    return """<button type="button" class="chat-opener" data-chat-open>Ask about this page</button>
<aside class="chat" hidden aria-label="Ask about this page"><div class="chat-head"><div><div class="chat-title">Ask about this page</div>
<div class="chat-page">Claude reads what this page shows. Nothing is saved.</div></div>
<div class="chat-actions"><button type="button" class="quiet" data-chat-clear>Clear</button><button type="button" class="quiet" data-chat-close>Close</button></div></div>
<div class="chat-log" aria-live="polite"></div>
<div class="chat-start"><p class="chat-intro">Try:</p><div class="ask-suggestions">
<button type="button" class="quiet" data-suggest>Which contrarian bids are in sectors money is flowing into?</button>
<button type="button" class="quiet" data-suggest>Explain the top five Asym names in plain English.</button>
<button type="button" class="quiet" data-suggest>What would make today's read wrong?</button></div></div>
<form class="chat-form" data-chat-form><label class="sr-only" for="q">Question</label><textarea id="q" rows="2" maxlength="600" placeholder="Ask a question"></textarea><button type="submit">Ask</button></form>
</aside>"""


LIGHT_CLASS = {"add": "fresh", "wait": "crowded", "hold": "fear", "none": "crowded"}


def _holding_price(h: dict) -> str:
    if h.get("price") is None:
        return "–"
    return f"R{h['price']:,.2f}" if h.get("currency") == "ZAR" else f"${money(h['price'])}"


def picks_page(r: dict, amounts: dict, rate: float | None, amounts_set: bool = True) -> str:
    preds = r.get("predictions") or {}
    buys = r.get("last_buys") or {}
    plan = plan_view.plan(amounts, r, rate, r.get("jse") or {}) if amounts_set else plan_view.first_run()
    holdings = r.get("holdings") or []
    if holdings:
        mine = "".join(f"""<tr><td><b>{e(h["symbol"]) if h.get("currency") == "ZAR" else ticker_link(h["symbol"])}</b> <span class="muted">{e(h["name"])}</span></td>
<td>{_holding_price(h)}</td><td><span class="action {LIGHT_CLASS[h["light"]]}">{e(h["label"])}</span></td><td class="why">{e(h["why"])}{levels_view.block(h["symbol"], r, "own", buys.get(h["symbol"]), compact=True)}{prediction_view.block(preds.get(h["symbol"]))}</td></tr>""" for h in holdings)
        mine = f'<div class="table-wrap"><table class="data holdings"><tbody>{mine}</tbody></table></div>'
    else:
        mine = '<p class="hint">Add what you own to config/holdings.json and each one gets a warning light here.</p>'
    weather = e(r["read"][0].replace("The tape: ", "")) if r.get("read") else ""
    note = f'<p class="hint predict-missing">{e(prediction.MISSING_NOTE)}</p>' if r.get("forecaster_missing") else ""
    picks = swing_view.section(r)
    first, second = (picks, plan) if amounts_set else (plan, picks)
    return f"""{note}
{first}
{second}
<section class="block"><div class="block-head"><h2>Stocks you own</h2><span class="hint">Warning lights, not sell signals. Long-term holdings ride out bumps.</span></div>{mine}</section>
<section class="block"><div class="block-head"><h2>Market today</h2></div><p class="prose">{weather}</p>
<p class="hint">These are rules applied to public data, not advice from a person who knows your situation. Nothing here is guaranteed.
They tell you where to look, not what will happen.</p></section>"""


def accept_gate() -> str:
    """Shown once, before anything else, until the user accepts. Nothing here is advice."""
    return """<section class="block gate" aria-labelledby="gate-title"><div class="block-head"><h2 id="gate-title">Before you start</h2></div>
<div class="prose"><p><b>This is a research tool, not financial advice.</b> It applies fixed rules to free public data. It doesn't know your
income, debts, goals or tax position, and its data can be late or wrong.</p>
<p>The amounts, picks, scores, ranges and predictions are not recommendations from a licensed adviser and are not promises.
Nothing here buys or sells anything for you. Before you invest real money, check the facts yourself and, if you're unsure,
speak to a licensed financial adviser.</p>
<p>By continuing you accept that you use it at your own risk (see the licence: the software comes "as is", without warranty).</p>
<p><button type="button" data-accept>I understand, continue</button></p></div></section>"""
