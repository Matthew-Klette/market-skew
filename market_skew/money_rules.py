"""Common money rules of thumb, worked out from a few numbers the user types in. Pure: no network, no disk.

These are "a common rule of thumb", not advice: invest about 20% of take-home, keep 3 months of expenses as an emergency
fund, keep rent to about 35% of take-home, living costs to about 50%, and about 5% for fun. TFSA limits are the SARS
figures (R36,000 a tax year, R500,000 for life); check with SARS before relying on them.
"""
import datetime as dt

FIELDS = ("take_home", "expenses", "rent", "emergency", "tfsa_year", "tfsa_life")
MAX_VALUE = 1e9
TFSA_YEAR, TFSA_LIFE = 36000.0, 500000.0
INVEST_SHARE, EMERGENCY_MONTHS, RENT_SHARE, LIVING_SHARE, FUN_SHARE = 0.20, 3.0, 0.35, 0.50, 0.05


def tax_year_label(today: dt.date) -> str:
    """The SARS tax year runs March to February: 2026-11-18 is in 2026/27."""
    start = today.year if today.month >= 3 else today.year - 1
    return f"{start}/{str(start + 1)[2:]}"


def clean(values) -> dict | None:
    """Keep the known fields as floats in [0, 1e9]. None if any given value is not a plain number in range."""
    if not isinstance(values, dict):
        return None
    out = {}
    for key in FIELDS:
        if key not in values or values[key] in (None, ""):
            continue
        raw = values[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return None
        try:
            number = float(raw)
        except ValueError:
            return None
        if not 0 <= number <= MAX_VALUE or number != number:
            return None
        out[key] = number
    return out


def _share(part: float | None, whole: float | None) -> float | None:
    return part / whole if whole and part is not None else None


def _status(actual: float | None, target: float, kind: str) -> str:
    """kind "min": at or above target is ok; "max": at or below is ok; "near": ok within 25% either side."""
    if actual is None:
        return "unknown"
    if kind == "min":
        return "ok" if actual >= target else "low"
    return "ok" if actual <= target else "high"


def rules(inputs: dict, invested: float) -> list[dict]:
    """Rows for the progress bars. `invested` is this month's TFSA + USD amount in rand. Each row has key, label, actual,
    target, unit ("share" or "months"), status (ok, low, high, unknown) and, for fun money, an amount."""
    take, spend, rent = inputs.get("take_home"), inputs.get("expenses"), inputs.get("rent")
    fund = inputs.get("emergency")
    months = _share(fund, spend)
    return [
        {"key": "invested", "label": "Invested each month", "actual": _share(invested, take), "target": INVEST_SHARE,
         "unit": "share", "status": _status(_share(invested, take), INVEST_SHARE, "min"), "kind": "min"},
        {"key": "emergency", "label": "Emergency fund", "actual": months, "target": EMERGENCY_MONTHS,
         "unit": "months", "status": _status(months, EMERGENCY_MONTHS, "min"), "kind": "min"},
        {"key": "rent", "label": "Rent", "actual": _share(rent, take), "target": RENT_SHARE,
         "unit": "share", "status": _status(_share(rent, take), RENT_SHARE, "max"), "kind": "max"},
        {"key": "living", "label": "Living costs", "actual": _share(spend, take), "target": LIVING_SHARE,
         "unit": "share", "status": _status(_share(spend, take), LIVING_SHARE, "max"), "kind": "max"},
        {"key": "fun", "label": "Fun money", "actual": None, "target": FUN_SHARE, "unit": "share", "status": "unknown",
         "kind": "suggest", "amount": take * FUN_SHARE if take else None},
    ]


def tfsa(inputs: dict, monthly: float, today: dt.date | None = None) -> dict:
    """TFSA room left this tax year and for life, a line about the monthly amount, and a warning when over."""
    today = today or dt.date.today()
    year, life = inputs.get("tfsa_year", 0.0), inputs.get("tfsa_life", 0.0)
    year_left, life_left = max(TFSA_YEAR - year, 0.0), max(TFSA_LIFE - life, 0.0)
    yearly = monthly * 12
    if yearly == TFSA_YEAR:
        line = f"At R{monthly:,.0f} a month you'll use R{TFSA_YEAR:,.0f} a year, exactly the yearly limit."
    elif yearly < TFSA_YEAR:
        line = f"At R{monthly:,.0f} a month you'll use R{yearly:,.0f} a year, leaving R{TFSA_YEAR - yearly:,.0f} of the limit unused."
    else:
        line = f"At R{monthly:,.0f} a month you'd put in R{yearly:,.0f} a year, R{yearly - TFSA_YEAR:,.0f} over the yearly limit."
    months_left = (2 - today.month) % 12 + 1  # this month through February
    projected = year + monthly * months_left
    over = year > TFSA_YEAR or life > TFSA_LIFE or projected > TFSA_YEAR or life + monthly * months_left > TFSA_LIFE
    warning = ("Over the limit: SARS taxes money put in above the TFSA limit at 40% of the excess. This is a plain fact "
               "of the rules, so check with SARS before you go over.") if over else None
    return {"year_label": tax_year_label(today), "year_left": year_left, "life_left": life_left,
            "room": min(year_left, life_left), "monthly_line": line, "months_left": months_left,
            "projected_year": projected, "warning": warning}
