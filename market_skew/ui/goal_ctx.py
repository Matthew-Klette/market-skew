"""What the goal projection and the bad-year card need on the Money tab, from saved data only: prefs "goal", holdings values,
the sleeve targets and the cached monthly history. The Monte Carlo runs here at render with a fixed seed (about a tenth of a
second, and the page never jumps between reloads); nothing is fetched."""
import datetime as dt

from .. import goal, history, milestones, money_rules, portfolio, risk

SEED = 2026
MILESTONE_YEARS, MILESTONE_PATHS = 30, 1500  # the dates are read off a longer, lighter run than the goal fan
DEFAULT_VALUE = 10000.0
NO_HISTORY = "No price history saved yet. Run ./skew history once (the weekly scan keeps it fresh)."
TOO_SHORT = "Not enough shared price history yet to resample."


def saved(prefs: dict) -> dict:
    """The goal typed last time, cleaned again (None-safe); empty until one is saved."""
    raw = prefs.get("goal") if isinstance(prefs.get("goal"), dict) else {}
    if isinstance(raw.get("inflation"), (int, float)):
        raw = {**raw, "inflation": round(raw["inflation"] * 100, 6)}
    return goal.clean(raw) or {}


def post(data: dict, save_prefs) -> tuple[int, dict]:
    values = goal.clean(data.get("goal"))
    if values is None:
        return 400, {"error": "Target in rand, years from 1 to 40, and plain numbers from 0 up (inflation 0 to 20)."}
    save_prefs({"goal": values})
    return 200, {"saved": True}


def post_milestones(data: dict, save_prefs) -> tuple[int, dict]:
    items = milestones.clean(data.get("milestones"))
    if items is None:
        return 400, {"error": "Each milestone needs a name, a kind and a number in range (up to 10)."}
    save_prefs({"milestones": items})
    return 200, {"milestones": items}


def _milestones(prefs: dict, mixed: list, resolved: dict, fee: float, today: dt.date | None) -> list[dict]:
    """Rows for the milestone list: both median paths come from a 30-year run, cautious and past decade, same seed as the goal."""
    returns = [r for _, r in mixed]
    paths = {}
    if len(returns) >= goal.MIN_MONTHS:
        for key, cut in (("cautious", goal.CAUTIOUS_MONTHLY), ("past", 0.0)):
            run = goal.simulate(returns, MILESTONE_YEARS, resolved["start"], resolved["monthly"], fee, resolved["inflation"], 1.0,
                                paths=MILESTONE_PATHS, seed=SEED, haircut=cut)
            paths[key] = run["median_path"]
    money = money_rules.clean(prefs.get("money") or {}) or {}
    return milestones.rows(milestones.saved(prefs), resolved["start"], money.get("expenses"), money.get("emergency"),
                           paths.get("cautious"), paths.get("past"), today or dt.date.today())


def _mix(ctx: dict, actual: bool) -> tuple[dict, str]:
    mine = portfolio.holding_weights(ctx["values"]) if actual else {}
    if mine:
        return mine, "your actual split"
    return portfolio.target_weights(ctx["targets"]), "your sleeve targets"


def _series(weights: dict) -> tuple[list, dict, str | None]:
    hist = history.cached()
    if not hist:
        return [], {}, NO_HISTORY
    filled, notes = history.with_proxies(history.rand_returns(hist["levels"]))
    if not all(f in filled for f in weights):
        return [], {}, NO_HISTORY
    mixed = portfolio.series(filled, weights)
    return mixed, notes, None if mixed else TOO_SHORT


def build(ctx: dict, prefs: dict, amounts: dict, today: dt.date | None = None) -> dict:
    """{"goal": ..., "risk": ...} for money_view. `ctx` is money_ctx.sleeves(...) (values, weights, targets)."""
    form = saved(prefs)
    total = ctx["weights"]["total"]
    weights, label = _mix(ctx, bool(form.get("actual")))
    mixed, notes, reason = _series(weights)
    inflation = form.get("inflation", goal.INFLATION)
    resolved = {"target": form.get("target"), "years": form.get("years"), "start": form.get("start", total),
                "monthly": form.get("monthly", amounts["tfsa"] + amounts["usd"]), "inflation": inflation, "actual": bool(form.get("actual"))}
    fee = portfolio.fee_pct(weights)
    result = past = fv = None
    if form and not reason:
        args = ([r for _, r in mixed], form["years"], resolved["start"], resolved["monthly"], fee, inflation, form["target"])
        result = goal.simulate(*args, seed=SEED, haircut=goal.CAUTIOUS_MONTHLY)  # the default view
        past = goal.simulate(*args, seed=SEED)
        net = resolved["monthly"] * (1 - fee)
        nominal = goal.fv_steady(resolved["start"], net, goal.STEADY, form["years"])
        fv = {"rate": goal.STEADY, "nominal": nominal, "real": goal.deflate(nominal, inflation, form["years"] * 12)}
    cagr = None
    if mixed:
        growth = 1.0
        for _, r in mixed:
            growth *= 1 + r
        cagr = growth ** (12 / len(mixed)) - 1
    value = total if total > 0 else DEFAULT_VALUE
    return {"goal": {"form": resolved, "saved": bool(form), "weights": weights, "label": label, "notes": notes, "reason": reason,
                     "result": result, "past": past, "fv": fv, "milestones": _milestones(prefs, mixed, resolved, fee, today), "fee": fee, "cagr": cagr, "defaults": {"start": total, "monthly": amounts["tfsa"] + amounts["usd"]}},
            "risk": {"stats": None if reason else risk.analyse(mixed, value), "reason": reason, "value": value, "assumed": total <= 0,
                     "label": label, "notes": notes}}
