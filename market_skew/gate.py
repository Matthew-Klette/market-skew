"""the quality-score gates. The quality score says whether a company is attractive; the skew scan says when. Pure: no files, no network.

  His way (swing)   adjusted score >= 60 and depth not Thin, then the timing rules in swing.py
  My way (Steady)   adjusted score >= 50, companies only (funds are exempt)
The adjusted score is the raw score minus Claude's saved deductions (breaking.apply). A company Claude has not argued
against yet uses its raw score and says so ("not yet checked by Claude"); the next app open has the answer.
"""
HIS_WAY_MIN, STEADY_MIN = 60, 50  # 70/60 left both lists empty with Claude's deductions (2026-11-18)


def line(row: dict) -> str:
    """'Quality score 82 → 74: growing 18% and speeding up; keeps 25c of every $1 as free cash'."""
    raw, score = row.get("raw_score", row["score"]), row["score"]
    head = f"Quality score {raw} → {score}" if raw != score else f"Quality score {score}"
    if not row.get("breaking"):
        head += " (not yet checked by Claude)"
    facts = []
    growth = row.get("growth")
    if growth is not None and growth > 0:
        facts.append(f"growing {growth * 100:.0f}%" + (" and speeding up" if row.get("accelerating") else ""))
    margin = (row.get("metrics") or {}).get("fcf_margin")
    if margin is not None and margin > 0:
        facts.append(f"keeps {margin * 100:.0f}c of every $1 as free cash")
    return head + (": " + "; ".join(facts) if facts else "") + "."


def top_reason(row: dict) -> str | None:
    """The biggest deduction Claude saved for this company, in its own words, or None when it took nothing off."""
    items = (row.get("breaking") or {}).get("deductions") or []
    return max(items, key=lambda d: d["points"])["reason"].rstrip(".") if items else None


def table(rows: list[dict]) -> dict[str, dict]:
    """symbol -> what the gates need from each (adjusted) Quality score row."""
    return {r["symbol"]: {"score": r["score"], "raw": r.get("raw_score", r["score"]), "checked": bool(r.get("breaking")),
                          "thin": bool(r.get("thin")), "line": line(r), "why": top_reason(r)} for r in rows}


def passes_swing(entry: dict | None) -> bool:
    return bool(entry) and entry["score"] >= HIS_WAY_MIN and not entry["thin"]


def passes_steady(symbol: str, entry: dict | None, funds=()) -> bool:
    return symbol in funds or (bool(entry) and entry["score"] >= STEADY_MIN)
