"""Builds what the Money page and the Picks plan need from saved data only: holdings, cached prices and rand rate."""
import datetime as dt

from .. import fx, holdings as holdings_mod, jse, money_rules, rebalance
from . import goal_ctx


def closes(report: dict | None) -> dict:
    """Latest US closes in dollars from the saved report (stocks table, then fund prices)."""
    report = report or {}
    out = {s["symbol"]: s["close"] for s in report.get("stocks") or [] if s.get("close")}
    out.update({s: f["price"] for s, f in (report.get("funds") or {}).items() if f.get("price")})
    return out


def sleeves(report: dict | None, prefs: dict, mine: list[dict] | None = None) -> dict:
    """Values, weights, drift and the plan lean for the current holdings."""
    mine = holdings_mod.load() if mine is None else mine
    rate = (fx.cached() or {}).get("rate")
    quotes = jse.cached() or (report or {}).get("jse") or {}
    vals = rebalance.values(mine, closes(report), quotes, rate)
    w = rebalance.weights(vals)
    targets = rebalance.targets_from(prefs)
    rows = rebalance.drift(w["weights"], targets) if w["weights"] else []
    return {"holdings": mine, "values": vals, "weights": w, "targets": targets, "drift": rows, "rate": rate}


def plan_lean(report: dict | None, prefs: dict) -> dict:
    """Keys for the Picks plan: tilt for allocation.allocate and the one-line note (both empty when nothing drifts)."""
    rows = sleeves(report, prefs)["drift"]
    return {"drift_tilt": rebalance.tilt(rows), "drift_note": rebalance.note(rows)} if rows else {}


def page_ctx(report: dict | None, prefs: dict, amounts: dict, today: dt.date | None = None) -> dict:
    ctx = sleeves(report, prefs)
    inputs = money_rules.clean(prefs.get("money") or {}) or {}
    cash = amounts["tfsa"] + amounts["usd"]
    suggestion = rebalance.cash_flow(ctx["weights"]["values"], ctx["targets"], cash) if ctx["weights"]["weights"] else []
    return {**ctx, **goal_ctx.build(ctx, prefs, amounts, today), "inputs": inputs, "invested": cash, "cash": cash, "tfsa_monthly": amounts["tfsa"],
            "today": today or dt.date.today(), "suggestion": suggestion, "note": rebalance.note(ctx["drift"])}


POSTS = ("/holdings", "/money", "/targets", "/goal", "/milestones")


def post(path: str, data: dict, save_prefs) -> tuple[int, dict]:
    """The token-protected saves of the Money tab; returns (status, json body). `save_prefs` writes under the prefs lock."""
    if path == "/holdings":
        try:
            return 200, {"holdings": holdings_mod.save(data.get("holdings"))}
        except ValueError as error:
            return 400, {"error": str(error)}
    if path == "/money":
        values = money_rules.clean(data.get("money"))
        if values is None:
            return 400, {"error": "Use plain numbers from 0 up."}
        save_prefs({"money": values})
        return 200, {"saved": True}
    if path == "/goal":
        return goal_ctx.post(data, save_prefs)
    if path == "/milestones":
        return goal_ctx.post_milestones(data, save_prefs)
    shares = rebalance.clean_targets(data.get("targets"))
    if shares is None:
        return 400, {"error": "Each target is 0 to 100 and the three must add up to 100."}
    save_prefs({"targets": shares})
    return 200, {"targets": shares}
