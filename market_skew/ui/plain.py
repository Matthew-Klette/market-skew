"""Plain-English answers ("Yes, because ...") built from the saved report, for people who don't speak finance.
Wording only: every number is read straight from the report."""
from ..funds import NEW_MONEY
from .fmt import e

SECTOR_WORDS = {
    "Info Tech": "Tech companies", "Materials": "Mining and chemicals", "Energy": "Oil and gas",
    "Industrials": "Factories, planes and trucks", "Health Care": "Health care and medicine", "Financials": "Banks and insurers",
    "Staples": "Everyday basics (food, drinks, soap)", "Cons Disc": "Shops, cars and travel",
    "Comm Svcs": "Internet and media (Google, Meta, Netflix)", "Utilities": "Electricity and water", "Real Estate": "Property",
}
PILL = {"yes": "fresh", "no": "fear", "mixed": "tighten", "info": "crowded"}
NOT_ADVICE = "These answers come from fixed rules applied to public prices. They're a starting point, not advice."


def word(sector: str) -> str:
    return SECTOR_WORDS.get(sector, sector)


def inline(sector: str) -> str:
    """The everyday name mid-sentence: only the first letter drops, so Google stays Google."""
    text = word(sector)
    return text[:1].lower() + text[1:]


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def plan_funds(r: dict) -> dict:
    return {s: f for s, f in (r.get("funds") or {}).items() if s in NEW_MONEY}


def size(value: float) -> str:
    v = abs(value) * 100
    return f"{v:.0f}%" if v >= 1 else f"{v:.1f}%"


def moved(value: float) -> str:
    return f"up {size(value)}" if value >= 0 else f"down {size(value)}"


def card(question: str, answer: str, kind: str, because: list[str], more: str = "") -> str:
    items = "".join(f"<li>{e(b)}</li>" for b in because if b)
    return (f'<article class="answer"><h3 class="answer-q">{e(question)}</h3>'
            f'<p class="answer-a"><span class="pill {PILL[kind]}">{e(answer)}</span>'
            f'{" because" if items else ""}</p><ul class="because">{items}</ul>{more}</article>')


def market_up(r: dict) -> str:
    spy = (r.get("indexes") or {}).get("SPY") or {}
    m = spy.get("ret_1m")
    if m is None:
        return ""
    answer, kind = ("Yes", "yes") if m > 0.01 else ("No", "no") if m < -0.01 else ("Flat", "mixed")
    week = f" and {moved(spy['ret_1w'])} this week" if spy.get("ret_1w") is not None else ""
    lines = [f"The S&P 500 (the 500 biggest US companies, what VOO holds) is {moved(m)} this month{week}."]
    off = spy.get("off_high")
    if off is not None:
        if off > -0.005:
            lines.append("It's at its highest price of the past year.")
        else:
            lines.append(f"It's {size(off)} below its highest price of the past year."
                         + (" Drops of 10% or more happen fairly often, roughly once every year or two." if off <= -0.10 else ""))
    sectors = r.get("sectors") or []
    if sectors:
        up = sum(s["rel_1m"] + m > 0 for s in sectors)
        lines.append(f"{up} of {len(sectors)} kinds of business are up this month.")
    rsp = ((r.get("indexes") or {}).get("RSP") or {}).get("ret_1m")
    if rsp is not None and rsp - m >= 0.02:
        lines.append("The biggest companies are falling more than the average company, so it's not as bad as the headline number.")
    elif rsp is not None and m - rsp >= 0.02:
        lines.append("Only the biggest companies are pulling it up; the average company is doing worse.")
    return card("Is the stock market up this month?", answer, kind, lines)


def nervous(r: dict) -> str:
    ix = r.get("indexes") or {}
    vix, spy = ix.get("VIX") or {}, ix.get("SPY") or {}
    m = vix.get("ret_1m")
    if m is None:
        return ""
    if m > 0.25 or (vix.get("ret_1w") or 0) > 0.2:
        answer, kind = "Yes", "no"
    elif m < -0.10:
        answer, kind = "No, they're calm", "yes"
    else:
        answer, kind = "A little", "mixed"
    lines = [f"The \"fear gauge\" (VIX) is {moved(m)} this month. It rises when people expect big price swings."]
    d = vix.get("ret_1d")
    if d is not None and abs(d) >= 0.05:
        lines.append(f"It {'jumped' if d > 0 else 'dropped'} {size(d)} today alone.")
    if spy.get("ret_1d") is not None:
        lines.append(f"The S&P 500 is {moved(spy['ret_1d'])} today.")
    if kind == "no":
        lines.append("Nervous markets are bumpy, but prices are lower. The US market has always recovered so far, sometimes after months or years.")
    return card("Are investors nervous?", answer, kind, lines)


def monthly(r: dict) -> str:
    spy = (r.get("indexes") or {}).get("SPY") or {}
    m = spy.get("ret_1m")
    funds = plan_funds(r)
    if m is None and not funds:
        return ""
    lines = []
    if m is not None and m < -0.02:
        lines.append(f"Prices are about {size(m)} lower than a month ago, so this month's money buys more.")
    elif m is not None and m > 0.05:
        lines.append(f"Prices are up {size(m)} this month. Stick to your normal amount; don't add extra.")
    elif m is not None:
        lines.append("Prices haven't moved much, so nothing special: just your normal amount.")
    add = [s for s, f in sorted(funds.items()) if f.get("timing") == "add"]
    hold = [s for s, f in sorted(funds.items()) if f.get("timing") == "hold"]
    if add:
        lines.append(f"For {listed(add)}, people betting with options expect a bounce. This app counts that as a good time to add.")
    if hold:
        lines.append(f"For {listed(hold)}, people are betting on more drops, so the plan puts less there this month.")
    lines.append("Putting in the same amount every month means you never have to guess the best day.")
    return card("Should I still put in my monthly money?", "Yes", "yes", lines)


def money_flow(r: dict) -> str:
    sectors = r.get("sectors") or []
    if not sectors:
        return ""
    into = max(sectors, key=lambda s: s["flow_bps"])
    away = min(sectors, key=lambda s: s["flow_bps"])
    best = max(sectors, key=lambda s: s["rel_1m"])
    worst = min(sectors, key=lambda s: s["rel_1m"])
    lines = [f"More of this week's trading moved into {inline(into['name'])} than anywhere else.",
             f"The most moved away from {inline(away['name'])}.",
             f"Best this month: {inline(best['name'])}, {size(best['rel_1m'])} {'better' if best['rel_1m'] >= 0 else 'worse'} than the market.",
             f"Worst this month: {inline(worst['name'])}, {size(worst['rel_1m'])} {'worse' if worst['rel_1m'] < 0 else 'better'} than the market."]
    themes = r.get("themes") or []
    if themes and themes[0]["rel_1m"] > 0:
        t = themes[0]
        lines.append(f"Hottest smaller group: {t['name']} ({', '.join(t['leaders'])}), {size(t['rel_1m'])} better than the market this month.")
    return card("Where is the money going?", f"Into {inline(into['name'])}", "info", lines)


def funds_view(r: dict) -> str:
    funds = plan_funds(r)
    if not funds:
        return ""
    add = sum(f.get("timing") == "add" for f in funds.values())
    answer, kind = (("Mostly a good time", "yes") if add * 2 > len(funds) else
                    ("Mostly wait", "no") if sum(f.get("timing") == "hold" for f in funds.values()) * 2 > len(funds) else ("Mixed", "mixed"))
    lines = [f"{s} ({f.get('name', s)}): {f['label']}. {f['why']}" for s, f in sorted(funds.items())]
    more = ('<p class="hint">Options are bets people pay for on where a price goes next. When they pay up for "it will rise" bets on '
            'something that just fell, that\'s a sign they expect a bounce.</p>')
    return card("What are people betting on for the funds in your plan?", answer, kind, lines, more)


def answers(r: dict) -> str:
    cards = "".join(x for x in (monthly(r), market_up(r), nervous(r), funds_view(r), money_flow(r)) if x)
    if not cards:
        return ""
    return f'<section class="answers">{cards}</section><p class="hint">{e(NOT_ADVICE)}</p>'


def streaks(h: dict, sectors: list[dict]) -> str:
    """The weekly grid, as one line per kind of business: a dot per week, green when it beat the market."""
    rows, weeks = (h or {}).get("rows") or {}, (h or {}).get("weeks") or []
    if not rows or not weeks:
        return '<p class="hint">Not enough weeks yet.</p>'
    month = {s["name"]: s["rel_1m"] for s in sectors} or (h.get("rel_1m") or {})
    order = sorted(rows.items(), key=lambda kv: (-sum(v > 0 for v in kv[1]), -month.get(kv[0], 0)))
    out = []
    for name, values in order:
        beat = sum(v > 0 for v in values)
        dots = "".join(f'<span class="dot {"up" if v > 0 else "down"}" title="{e(w)}: {"beat" if v > 0 else "trailed"} the market by {size(v)}"></span>'
                       for w, v in zip(weeks, values))
        verdict = ("Beat the market every week" if beat == len(values) else "Trailed the market every week" if beat == 0
                   else f"Beat the market {beat} of the last {len(values)} weeks")
        out.append(f'<li><span class="streak-name"><b>{e(word(name))}</b> <span class="muted">{e(name)}</span></span>'
                   f'<span class="dots" role="img" aria-label="{e(verdict)}">{dots}</span><span class="streak-say">{e(verdict)}</span></li>')
    return (f'<p class="prose">Each dot is one week, oldest on the left. <span class="up">Green</span> means that kind of business did better '
            f'than the S&amp;P 500 that week; <span class="down">red</span> means it did worse. Lots of green in a row means it\'s on a run.</p>'
            f'<ul class="streaks">{"".join(out)}</ul>')
