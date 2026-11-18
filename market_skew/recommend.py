"""Which way to lean this month: My way (Steady picks) or His way (swing trades). Pure: no network, no disk.

Each record is a list of paper results: {"date": start day, "ret": return after fees, "voo_ret": VOO over the same
period, "settled": True once the result is final (swing trade closed, Steady pick held a month)}.

Rules, in order:
  1. The 90-day rule: fewer than 90 days since the first record entry on either side: not enough evidence, My way.
  2. The 5-result rule: fewer than 5 settled results on either side (inside the last 90 days): not enough evidence, My way.
     A result is settled once a Steady pick has had 28 days or a swing trade has hit its stop, target or time limit.
  3. The nervous-market rule (S&P 500 down 5%+ over a month and VIX up 5%+ today, or the tape reads risk-off): My way.
  4. Otherwise the side with the higher average result over VOO (after fees, last 90 days) wins, but His way must
     win by at least 1 percentage point (the 1-point margin); less than that is not worth the extra trading.
"""
import datetime as dt

MIN_DAYS, MIN_SETTLED, WINDOW_DAYS, MARGIN = 90, 5, 90, 0.01
NERVOUS_MONTH, NERVOUS_VIX = -0.05, 0.05


def is_nervous(mood: dict) -> bool:
    spy, vix = mood.get("spy_1m"), mood.get("vix_1d")
    numbers = spy is not None and vix is not None and spy <= NERVOUS_MONTH and vix >= NERVOUS_VIX
    return bool(numbers or mood.get("risk_off"))


def _days(entries: list[dict], today: dt.date) -> int:
    """Days since the first record entry on either side."""
    return (today - min(dt.date.fromisoformat(x["date"]) for x in entries)).days if entries else 0


def _usable(entries: list[dict], today: dt.date) -> list[dict]:
    start = today - dt.timedelta(days=WINDOW_DAYS)
    return [x for x in entries if x.get("settled") and x.get("ret") is not None and x.get("voo_ret") is not None
            and dt.date.fromisoformat(x["date"]) >= start]


def _average(entries: list[dict]) -> float | None:
    return sum(x["ret"] - x["voo_ret"] for x in entries) / len(entries) if entries else None


def _points(value: float) -> str:
    return f"{value * 100:+.1f}%"


def recommend(mine_record: list[dict], his_record: list[dict], mood: dict, today: str) -> dict:
    now = dt.date.fromisoformat(today)
    mine, his = _usable(mine_record, now), _usable(his_record, now)
    days = _days(mine_record + his_record, now)
    evidence = {"days": days, "mine_settled": len(mine), "his_settled": len(his),
                "mine_avg": _average(mine), "his_avg": _average(his), "nervous": is_nervous(mood)}
    if days < MIN_DAYS or len(mine) < MIN_SETTLED or len(his) < MIN_SETTLED:
        if days < MIN_DAYS:
            reason = f"Not enough evidence yet: {days} days of record; needs about 3 months."
        else:
            reason = (f"Not enough evidence yet: only {min(len(mine), len(his))} settled results on the thinner side; "
                      f"needs at least {MIN_SETTLED} on each side.")
        return {"lens": "mine", "reason": reason, "evidence": evidence}
    if evidence["nervous"]:
        return {"lens": "mine", "reason": "Nervous market: swing trades are riskier now. Stay with My way.", "evidence": evidence}
    gap = evidence["his_avg"] - evidence["mine_avg"]
    numbers = (f"Over the last 3 months, after fees and against VOO, My way averaged {_points(evidence['mine_avg'])} "
               f"and His way {_points(evidence['his_avg'])}.")
    if gap >= MARGIN:
        return {"lens": "his", "reason": f"His way has been ahead. {numbers}", "evidence": evidence}
    if gap > 0:
        reason = f"{numbers} His way is ahead by less than 1 point, which is not worth the extra trading. Stay with My way."
    else:
        reason = f"My way has been ahead. {numbers}"
    return {"lens": "mine", "reason": reason, "evidence": evidence}
