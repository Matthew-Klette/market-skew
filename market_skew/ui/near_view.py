"""The 'closest candidates' block shown under an empty list. Labelled as not picks: no money, no paper record."""
from .. import closest
from .fmt import e


def block(items: list[dict] | None) -> str:
    if not items:
        return ""
    rows = "".join(f'<li><b>{e(x["symbol"])}</b> <span class="muted">{e(x["name"])}</span>: {e(x["text"])}</li>' for x in items)
    return f'<div class="near" data-not-picks><p class="hint"><b>{e(closest.LABEL)}</b></p><ul class="near-list">{rows}</ul></div>'
