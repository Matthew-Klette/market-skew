"""Milestones on the road to the goal (spec story 17): an editable list saved in prefs "milestones", each with how far along it is
and, for the invested ones, a date band from the median of the cautious and the past-decade paths. Pure: no network, no disk."""
import datetime as dt
import math

DEFAULTS = [{"label": "Emergency fund", "kind": "emergency", "value": 3.0},
            {"label": "R100,000 invested", "kind": "invested", "value": 1e5},
            {"label": "R500,000 invested", "kind": "invested", "value": 5e5},
            {"label": "R1,000,000 invested", "kind": "invested", "value": 1e6}]
KINDS = {"invested": (1.0, 1e10), "emergency": (0.5, 60.0)}  # rand, or months of expenses
MAX_ITEMS, MAX_LABEL = 10, 40


def clean(raw) -> list[dict] | None:
    """Typed milestones -> [{label, kind, value}]; None when anything is not a label, a known kind and a number in range."""
    if not isinstance(raw, list) or len(raw) > MAX_ITEMS:
        return None
    out = []
    for item in raw:
        if not isinstance(item, dict) or item.get("kind") not in KINDS:
            return None
        label, value = item.get("label"), item.get("value")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > MAX_LABEL:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            number = float(value)
        except ValueError:
            return None
        low, high = KINDS[item["kind"]]
        if not math.isfinite(number) or not low <= number <= high:
            return None
        out.append({"label": label.strip(), "kind": item["kind"], "value": number})
    return out


def saved(prefs: dict) -> list[dict]:
    """The list saved last time, or the four defaults when none is saved (an empty saved list stays empty)."""
    cleaned = clean(prefs.get("milestones")) if "milestones" in prefs else None
    return DEFAULTS if cleaned is None else cleaned


def month_label(today: dt.date, months: int) -> str:
    index = today.year * 12 + today.month - 1 + months
    return dt.date(index // 12, index % 12 + 1, 1).strftime("%b %Y")


def _first(path, value: float) -> int | None:
    return next((m for m, v in enumerate(path) if v >= value), None)


def _band(item_path: dict, today: dt.date, horizon: int) -> tuple[dict, str]:
    eta = {k: (None if m is None else month_label(today, m)) for k, m in item_path.items()}
    names = {"cautious": "cautious", "past": "past decade"}
    if all(v is None for v in eta.values()):
        return eta, f"not within {horizon} years"
    if eta["cautious"] == eta["past"]:
        return eta, f"about {eta['cautious']} (cautious and past decade agree)"
    if all(eta.values()):
        return eta, f"about {eta['cautious']} ({names['cautious']}) to {eta['past']} ({names['past']})"
    parts = [f"about {eta[k]} ({names[k]})" if eta[k] else f"not within {horizon} years ({names[k]})" for k in ("cautious", "past")]
    return eta, "; ".join(parts)


def rows(items: list[dict], invested: float, expenses: float | None, emergency: float | None, cautious, past,
         today: dt.date) -> list[dict]:
    """One row per milestone: label, kind, target (rand), pct (0..1 or None), status (done/open/unknown), eta ({cautious, past} month labels, or None) and
    band (the words). `cautious` and `past` are median value paths by month in today's rand; `invested` is what is held now."""
    out = []
    for item in items:
        base = {"label": item["label"], "kind": item["kind"], "value": item["value"]}
        if item["kind"] == "emergency":
            target = item["value"] * expenses if expenses else None
            pct = min(emergency / target, 1.0) if target and emergency is not None else None
            band = ("Cash, so it is not part of the investment projection." if target else "Add your monthly expenses to see this.")
            out.append({**base, "target": target, "pct": pct, "status": "unknown" if pct is None else "done" if pct >= 1 else "open",
                        "eta": None, "band": band})
            continue
        target, pct = item["value"], min(invested / item["value"], 1.0)
        if invested >= target:
            out.append({**base, "target": target, "pct": 1.0, "status": "done", "eta": None, "band": "Reached"})
        elif not cautious or not past:
            out.append({**base, "target": target, "pct": pct, "status": "open", "eta": None, "band": "Needs saved price history for a date."})
        else:
            horizon = (len(cautious) - 1) // 12
            eta, band = _band({"cautious": _first(cautious, target), "past": _first(past, target)}, today, horizon)
            out.append({**base, "target": target, "pct": pct, "status": "open", "eta": eta, "band": band})
    return out
