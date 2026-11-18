"""The Recommended / My way / His way control at the top of Picks, and the section order it picks."""
from .fmt import e

OPTIONS = (("auto", "Recommended"), ("mine", "My way"), ("his", "His way"))
NAMES = {"mine": "My way", "his": "His way"}


def control(choice: str, rec: dict) -> str:
    buttons = "".join(
        f'<button type="button" class="seg" data-lens="{key}" aria-pressed="{"true" if key == choice else "false"}">{label}</button>'
        for key, label in OPTIONS)
    if choice == "auto":
        note = f'<b>Recommended: {e(NAMES[rec["lens"]])}.</b> {e(rec["reason"])}'
    else:
        note = (f'You chose {e(NAMES[choice])} for this month. The app would recommend <b>{e(NAMES[rec["lens"]])}</b>: '
                f'{e(rec["reason"])}')
    return f"""<section class="lens" data-lens-control><div class="segmented" role="group" aria-label="Which way to lean this month">{buttons}</div>
<p class="lens-note" aria-live="polite">{note}</p></section>"""


def arrange(lens: str, mine_html: str, his_html: str) -> str:
    """The chosen way in full; the other collapsed but still reachable."""
    first, other, other_name = (his_html, mine_html, "My way") if lens == "his" else (mine_html, his_html, "His way")
    return f'{first}<details class="other-way"><summary>Also see {other_name}</summary>{other}</details>'
