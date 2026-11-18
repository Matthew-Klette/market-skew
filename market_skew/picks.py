"""The timing words (Contrarian Bid, Chase, ...) and the warning lights for the stocks you own. The Picks list itself is swing.py."""
import pandas as pd


FUNDS = ("QQQ", "SCHD", "VOO", "VOOG")  # same list as funds.FUNDS (funds.py imports this module, so it is not imported back)

TIMING = {
    "Contrarian Bid": ("add", "Good time to add", "It dipped this month and options traders are betting on a bounce."),
    "Chase": ("wait", "OK, but no rush", "It's been popular lately. Buying in small monthly amounts beats buying all at once here."),
    "Hedged Rally": ("hold", "Don't add now", "It's up, but traders are buying insurance against a drop. Wait for that to calm down."),
    "Fear": ("hold", "Don't add now", "It's falling and traders expect more. No need to sell a long-term holding, but don't add yet."),
}


def timing(bucket: str) -> tuple[str, str, str]:
    return TIMING.get(bucket, ("wait", "No signal", "No options reading today."))


def holdings_check(scored: pd.DataFrame, mine: set[str]) -> list[dict]:
    """A warning light for each stock you own (your starred stocks)."""
    rows = scored[scored["symbol"].isin(mine)]
    out = []
    for r in rows.to_dict("records"):
        kind, label, why = timing(r["bucket"])
        out.append({"symbol": r["symbol"], "name": r.get("name") or r["symbol"], "light": kind, "label": label,
                    "why": why, "price": float(r["close"]), "ret_1m": float(r["ret_1m"])})
    missing = sorted(mine - set(rows["symbol"]))
    out += [{"symbol": s, "name": s, "light": "none", "label": "No reading", "why": "Not in today's scan (no usable option quotes).",
             "price": None, "ret_1m": None} for s in missing]
    order = {"hold": 0, "add": 1, "wait": 2, "none": 3}
    return sorted(out, key=lambda x: order[x["light"]])


def without(picks: list[dict], excluded: set[str]) -> list[dict]:
    """Saved picks minus tickers you can't buy, so a click takes effect before the next scan."""
    return [p for p in picks if p["symbol"] not in excluded]
