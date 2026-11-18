"""Ask about this page: one `claude -p` call on your Claude plan, every tool off, no session kept."""
import subprocess
import tempfile

from .. import claude_cli, gate
from ..backtest import summary
from .fmt import pct

TIMEOUT_SECONDS = 120
MAX_QUESTION = 600
MAX_TURNS = 6
SYSTEM_PROMPT = (
    "You answer questions about a stock-market dashboard called Market Skew. You only see the figures in <page>. "
    "Answer plainly and briefly, cite the numbers you use, and say when the page does not hold the answer. "
    "Skew = (25-delta put IV - 25-delta call IV) / ATM IV. Buckets: Contrarian Bid (price down, calls bid), "
    "Fear (down, puts bid), Chase (up, calls bid), Hedged Rally (up, puts bid). Asym ranks lopsided set-ups. "
    "The user is a beginner investing long term with low risk tolerance. Explain in plain words, no jargon without a "
    "definition. You can explain the page's rule-based picks and why the rules chose them, but be honest that nothing is "
    "guaranteed and that a broad index fund is the sensible core.")


class ChatError(Exception):
    pass


def _lens_lines(report: dict) -> list[str]:
    rec = report.get("recommendation")
    if not rec:
        return []
    names = {"mine": "My way (Steady picks)", "his": "His way (swing trades)"}
    return [f"Recommended lens this month: {names[rec['lens']]}. {rec['reason']}",
            "My way = steady, calm big companies. His way = a swing-trading creator's method, as trades with an entry, stop and target. "
            "The page shows the user's own choice (Recommended, My way or His way) at the top; the USD plan follows it."]


def _sentinel_lines(report: dict) -> list[str]:
    """Each on-screen company's adjusted Quality score and what breaks the call (from report["sentinel_brief"], built at render)."""
    return [f"- {x['symbol']}: Quality score {x['score']}" + (f" (was {x['raw']} before Claude's deductions)" if x["raw"] != x["score"] else "")
            + ("" if x["checked"] else " (not yet checked by Claude)") + (f"; what breaks: {x['what_breaks']}" if x.get("what_breaks") else "")
            for x in report.get("sentinel_brief") or []]


def brief(view: str, report: dict, history=None) -> str:
    lines = [f"Page: {view}. Report date {report['date']}, universe {report['universe']}, with skew {report['with_skew']}."]
    lines += ["Today's read:"] + [f"- {x}" for x in report["read"]]
    lines += ["Tiles:"] + [f"- {t['label']}: {t['value'] if t['kind'] == 'text' else pct(t['value'])} ({t['note']})" for t in report["kpis"]]
    if view == "picks":
        lines.append("Steady picks (long-term, low volatility; timing from the options gaps):")
        lines += [f"- {p['symbol']} {p['name']} ({p['sector']}): {p['timing_label']}; IV {pct(p['iv'], False, 0)}; 1M {pct(p['ret_1m'])}; "
                  + " ".join(p["reasons"]) for p in report.get("picks", [])]
        lines.append("User's own stocks (warning lights):")
        lines += [f"- {h['symbol']}: {h['label']} - {h['why']}" for h in report.get("holdings", [])]
        lines.append("Paper record (Steady picks, after fees, vs VOO same period): " + "; ".join(
            f"{x['symbol']} since {x['date']} {pct(x['ret'])} vs VOO {pct(x['voo_ret'])}" for x in report.get("paper", [])))
        lines.append(f"His way (swing trades; each needs Quality score {gate.HIS_WAY_MIN}+ after deductions and enough filings, then the timing rules): "
                     + (", ".join(t["symbol"] for t in report.get("swing") or []) or "none today"))
        lines.append(f"Quality scores of the on-screen companies (Steady picks need {gate.STEADY_MIN}+, His way {gate.HIS_WAY_MIN}+):")
        lines += _sentinel_lines(report)
        lines += _lens_lines(report)
        lines.append("The user is a beginner building a long-term, low-volatility portfolio; the page suggests ~80% in a broad index fund.")
    if view in ("overview", "how"):
        lines.append("Themes (name, 1M vs SPY, 1W vs SPY, today, trend, flow bps, breadth, leaders):")
        lines += [f"- {t['name']}: {pct(t['rel_1m'])}, {pct(t['rel_1w'])}, {pct(t['today'])}, {t['trend']}, {t['flow_bps']:+.1f}, "
                  f"{pct(t['breadth'], False, 0)}, {', '.join(t['leaders'])}" for t in report["themes"]]
        lines.append("Sectors:")
        lines += [f"- {t['name']}: {pct(t['rel_1m'])} 1M vs SPY, skew {pct(t['skew'], False)}, flow {t['flow_bps']:+.1f} bps" for t in report["sectors"]]
    top = report["stocks"][:80 if view == "stocks" else 25]
    lines.append("Stocks by Asym (symbol, sector, bucket, asym, 1D, 1M, skew, ATM IV, watchlist):")
    lines += [f"- {s['symbol']} {s['sector']} {s['bucket']} {s['asym']} {pct(s['ret_1d'])} {pct(s['ret_1m'])} "
              f"{pct(s['skew'], False)} {pct(s['atm'], False, 0)}{' *' if s['watch'] else ''}" for s in top]
    if view == "backtest" and history is not None:
        lines.append(f"Track record: {summary(history)}")
    return "\n".join(lines)


def _claude() -> str:
    try:
        return claude_cli.find()
    except claude_cli.NotFound as error:
        raise ChatError(str(error)) from None


def ask(question: str, turns: list, page: str, run=subprocess.run) -> str:
    question = question.strip()[:MAX_QUESTION]
    if not question:
        raise ChatError("Type a question first.")
    past = "\n".join(f"Question: {q}\nAnswer: {a}" for q, a in turns[-MAX_TURNS:])
    prompt = f"<page>\n{page}\n</page>\n\n" + (f"<conversation>\n{past}\n</conversation>\n\n" if past else "") + f"Question: {question}"
    env = claude_cli.subprocess_env()  # no API key, so it can only use your Claude plan
    command = [_claude(), "-p", "--safe-mode", "--no-session-persistence", "--tools", "", "--strict-mcp-config",
               "--model", "sonnet", "--system-prompt", SYSTEM_PROMPT, "--output-format", "text"]
    with tempfile.TemporaryDirectory() as empty:
        try:
            done = run(command, input=prompt, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, cwd=empty, env=env)
        except subprocess.TimeoutExpired:
            raise ChatError("That took too long. Try again.") from None
    answer = (done.stdout or "").strip()
    if done.returncode != 0 or not answer:
        if "not logged in" in f"{answer} {done.stderr}".lower():
            raise ChatError("Claude Code is signed out. Sign in, then ask again.")
        raise ChatError("Claude could not answer just now. Try again in a moment.")
    return answer
