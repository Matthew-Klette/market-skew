"""What EasyEquities and the bank take, per SPEC section 5. Rates are "about": VAT on JSE trades is unverified."""

USD_TRADE = (0.0025 + 0.0031) * 1.15  # 0.25% brokerage + 0.31% clearing, plus 15% VAT
RATES = {
    "usd_buy": USD_TRADE,
    "usd_sell": USD_TRADE,
    "fx_convert": 0.012,  # ~0.5% transfer + ~0.7% rate margin
    "jse_buy": 0.0025,
}
LABELS = {
    "usd_buy": "Buying US shares",
    "usd_sell": "Selling US shares",
    "fx_convert": "Rand to dollars",
    "jse_buy": "Buying on the JSE",
}
THRIVE_MONTHLY_FEE = 25  # rand, EasyEquities Thrive


def fee(amount: float, kind: str) -> dict:
    """One step: the fee and what is left after it."""
    rate = RATES[kind]
    amount = max(float(amount), 0.0)
    return {"kind": kind, "label": LABELS[kind], "rate": rate, "fee": amount * rate, "net": amount * (1 - rate)}


def _chain(amount: float, kinds: list[str]) -> dict:
    amount = max(float(amount), 0.0)
    steps, left = [], amount
    for kind in kinds:
        step = fee(left, kind)
        steps.append(step)
        left = step["net"]
    total = amount - left
    return {"amount": amount, "steps": steps, "fee": total, "invested": left,
            "fee_pct": total / amount if amount else 0.0}


def tfsa_line(amount: float) -> dict:
    return _chain(amount, ["jse_buy"])


def usd_line(amount: float) -> dict:
    """Rand converted to dollars, then the US buy fee."""
    return _chain(amount, ["fx_convert", "usd_buy"])


def net_return(entry: float, now: float, kinds: tuple[str, ...] = ("usd_buy", "usd_sell")) -> float:
    """Return on a position after the fee steps in `kinds` (default: a US buy and a US sell)."""
    held = now / entry
    for kind in kinds:
        held *= 1 - RATES[kind]
    return held - 1
