"""Quietly breaking: Claude argues AGAINST one company from its saved numbers and takes points off its Quality score.
One `claude -p` call per company on the user's Claude plan (haiku, every tool off, no session, no API key). Pure parts
(brief, parse, version, apply) sit here; storage and the on-screen list are in breaking_run.py. Never runs at page render."""
import json
import subprocess
import tempfile

from . import claude_cli, sentinel

TIMEOUT_SECONDS = 60
MODEL = "haiku"
MAX_POINTS, MAX_TOTAL, MAX_ITEMS, MAX_WORDS, MAX_BREAKS = 8, 20, 5, 20, 240  # 30 took ~25-30 off nearly everything (2026-11-18)
SYSTEM_PROMPT = (
    "You are a skeptical analyst. Argue AGAINST buying this company using only the numbers given. Return JSON only: "
    '{"deductions":[{"points":int 1-10,"reason":str (plain English, <= 20 words)}], "what_breaks": str (one sentence)}. '
    "Max total 20 points. Calibrate: a healthy, fairly priced company loses 0-5; a company with one real weakness 6-12; "
    "only clear red flags (shrinking sales, cash burn, heavy debt, extreme price for the growth) justify 13-20. "
    "Do not invent facts beyond the numbers. "
    "Do NOT deduct for missing or unreported numbers (n/a, gaps, thin history): those are gaps in our data, not the company's. "
    "Deduct only for weaknesses visible in the numbers given.")
PROMPT_VERSION = "p3"  # bump when SYSTEM_PROMPT changes so every saved answer is asked again
NOTE = "Claude argued against this company using its filed numbers only, not news."


class BreakingError(Exception):
    pass


def _pc(v, digits=0) -> str:
    return "n/a" if v is None else f"{v * 100:.{digits}f}%"


def _big(v) -> str:
    if v is None:
        return "n/a"
    sign, a = ("-" if v < 0 else ""), abs(v)
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= size:
            return f"{sign}${a / size:.1f}{suffix}"
    return f"{sign}${a:,.0f}"


def _x(v, unit="") -> str:
    return "n/a" if v is None else f"{v:.1f}{unit}"


def version(row: dict) -> str:
    """The data version a cached answer belongs to: the prompt version, the filing period of its numbers and its raw Quality score."""
    return f"{PROMPT_VERSION}|{row.get('as_of')}|{row.get('raw_score', row['score'])}"


def brief(row: dict) -> str:
    """A compact numbers-only brief: filed metrics, Quality score pillars, price checks and the skew bucket. No prices from outside the saved data."""
    m = row["metrics"]
    pillars = "; ".join(f"{p['label']} {p['pts']}/{p['max']}" for p in row["pillars"].values())
    lines = [
        f"{row['symbol']} ({row['name']}), sector {row['sector']}, market value {_big(row.get('market_cap'))}.",
        f"Quality score {row.get('raw_score', row['score'])}/100 ({row['label']}). Pillars: {pillars}.",
        f"Filed numbers to {row.get('as_of')} ({row['depth']} data, {m.get('quarters', 0)} quarters, {m.get('years', 0)} years):",
        f"- sales last 12 months {_big(m.get('ttm_revenue'))}; growth {_pc(m.get('revenue_growth'))} (a year earlier {_pc(m.get('revenue_growth_prior'))})",
        f"- gross margin {_pc(m.get('gross_margin'))}; free cash flow {_big(m.get('fcf'))}, free cash margin {_pc(m.get('fcf_margin'))}",
        f"- free cash per share growth {_pc(m.get('fcf_per_share_growth'))}; share count change over a year {_pc(m.get('share_change'), 1)}",
        f"- net cash (cash minus debt) {_big(m.get('net_cash'))}; debt is {_x(m.get('debt_to_fcf'), ' years')} of free cash",
        "Price checks:",
        f"- free cash yield {_pc(row.get('cash_yield'), 1)} against {_pc(row.get('treasury'), 1)} on 10-year Treasuries",
        f"- price per $1 of yearly free cash {_x(row.get('pfcf'), 'x')}; vs its own history {_pc(row.get('own_history_pct'))}; "
        f"vs sector peers {_pc(row.get('peer_pct'))}; price vs growth {_x(row.get('peg'))}",
        f"- last month {_pc(row.get('ret_1m'), 1)} ({row.get('together') or 'n/a'}); options market bucket {row.get('bucket') or 'n/a'}",
    ]
    if row.get("flags"):
        lines.append("Flags: " + " ".join(row["flags"]))
    if row.get("gaps"):
        lines.append("Missing numbers: " + ", ".join(row["gaps"]))
    return "\n".join(lines)


def _first_object(text: str):
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                value, _ = decoder.raw_decode(text, i)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return None


def _points(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or value != value:
        return None
    return max(1, min(MAX_POINTS, int(round(value))))


def _words(text: str, limit: int) -> str:
    words = text.split()
    return " ".join(words[:limit]) + ("..." if len(words) > limit else "")


def parse(text: str) -> dict | None:
    """The first JSON object in Claude's reply, validated: {"deductions":[{"points":1-10,"reason":str}], "what_breaks":str, "total":int}.
    Items that are not {points, reason} are dropped, points are clamped to 1-8 and the total is capped at 20. None when there is no usable object."""
    data = _first_object(text)
    if not data or not isinstance(data.get("deductions"), list):
        return None
    items, total = [], 0
    for raw in data["deductions"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("reason"), str) or not raw["reason"].strip():
            continue
        points = _points(raw.get("points"))
        if points is None or len(items) >= MAX_ITEMS or total >= MAX_TOTAL:
            continue
        points = min(points, MAX_TOTAL - total)
        items.append({"points": points, "reason": _words(raw["reason"].strip(), MAX_WORDS)})
        total += points
    what = data.get("what_breaks")
    what = what.strip()[:MAX_BREAKS] if isinstance(what, str) else ""
    if not items and not what:
        return None
    return {"deductions": items, "what_breaks": what, "total": total}


def _claude() -> str:
    try:
        return claude_cli.find()
    except claude_cli.NotFound as error:
        raise BreakingError(str(error)) from None


def ask(row: dict, run=subprocess.run) -> dict:
    """One call for one company. Raises BreakingError on a timeout, a failed call or an unreadable reply."""
    env = claude_cli.subprocess_env()  # no API key, so it can only use your Claude plan
    command = [_claude(), "-p", "--safe-mode", "--no-session-persistence", "--tools", "", "--strict-mcp-config",
               "--model", MODEL, "--system-prompt", SYSTEM_PROMPT, "--output-format", "text"]
    with tempfile.TemporaryDirectory() as empty:
        try:
            done = run(command, input=brief(row), capture_output=True, text=True, timeout=TIMEOUT_SECONDS, cwd=empty, env=env)
        except subprocess.TimeoutExpired:
            raise BreakingError("timed out") from None
    if done.returncode != 0:
        raise BreakingError((done.stderr or "claude failed").strip()[:120])
    result = parse(done.stdout or "")
    if result is None:
        raise BreakingError("reply was not usable JSON")
    return result


def apply(rows: list[dict], answers: dict[str, dict]) -> list[dict]:
    """Adjusted scores for display. `answers` maps symbol -> stored {version, deductions, what_breaks, total}. An answer only counts
    when its version matches the row's current data. Labels and ranks follow the adjusted score; the raw score is kept as raw_score."""
    out = []
    for r in rows:
        a = answers.get(r["symbol"])
        if not a or a.get("version") != version(r):
            out.append({**r, "raw_score": r["score"], "breaking": None})
            continue
        score = max(0, r["score"] - int(a["total"]))
        out.append({**r, "raw_score": r["score"], "score": score, "label": sentinel.label(score), "breaking": a})
    out.sort(key=lambda r: (-r["score"], r["symbol"]))
    return [{**r, "rank": i} for i, r in enumerate(out, 1)]


def headline(row: dict) -> str:
    """'76 → 56' when points were taken off, else just the score."""
    return f"{row['raw_score']} → {row['score']}" if row.get("raw_score") not in (None, row["score"]) else str(row["score"])
