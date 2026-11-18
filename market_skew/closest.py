"""Closest candidates: when the Picks list is empty, the 3 names that came nearest and what kept each out. Pure, no files.
These are NOT picks: they are never in report["swing"] (the Picks list), so they get no money and no paper record."""
import pandas as pd

from . import gate, picks, swing

SHOW = 3
LABEL = "Not picks: the closest ones and why they missed"


def _sentinel_miss(entry: dict | None, need: int) -> tuple[str | None, int]:
    """(reason text or None when it passes, points short)."""
    if entry is None:
        return "no Quality score yet", need
    if entry["score"] >= need:
        return None, 0
    short = need - entry["score"]
    if entry["checked"]:
        head = f"Quality score {entry['score']} after Claude (needs {need})"
        return head + (f": {entry['why']}" if entry.get("why") else ""), short
    return f"Quality score {entry['score']}, not yet checked by Claude (needs {need})", short


def _swing_misses(r, entry) -> list[str]:
    out = []
    if r["bucket"] != "Contrarian Bid":
        out.append("timing: not a Contrarian Bid today")
    if r["close"] < swing.MIN_PRICE or r["dvol_21"] < swing.MIN_DOLLAR_VOLUME or r["source"] != "mid":
        out.append("not liquid enough to trade")
    if r["atm"] > swing.MAX_ATM_IV or r["ret_1m"] <= swing.WORST_MONTH:
        out.append("too wild: options move or monthly drop over the limit")
    if entry and entry["thin"]:
        out.append("too few filings (Thin) to trust the score")
    return out


def _near(scored: pd.DataFrame, entries: dict, excluded, need: int, misses, skip=()) -> list[dict]:
    ranked = []
    for r in scored.to_dict("records"):
        sym = r["symbol"]
        if sym in excluded or sym in skip or sym not in entries:  # funds have no Quality score row and are exempt, so they are not "misses"
            continue
        entry = entries[sym]
        s_text, short = _sentinel_miss(entry, need)
        reasons = ([s_text] if s_text else []) + misses(r, entry)
        if reasons:
            ranked.append((len(reasons), short, -entry["score"], sym, r.get("name") or sym, "; ".join(reasons)))
    ranked.sort()
    return [{"symbol": x[3], "name": x[4], "text": x[5]} for x in ranked[:SHOW]]


def nearest(scored: pd.DataFrame, entries: dict, excluded=frozenset(), earnings: dict | None = None,
            today: str | None = None) -> list[dict]:
    def misses(r, entry) -> list[str]:
        wait = swing.wait_note((earnings or {}).get(r["symbol"]), today) if earnings and today else None
        return ([wait] if wait else []) + _swing_misses(r, entry)
    return _near(scored, entries, excluded, gate.HIS_WAY_MIN, misses, skip=picks.FUNDS)
