"""One self-contained HTML file of the latest report: open it anywhere, no app or server needed."""
from pathlib import Path

from .. import store
from . import views
from .fmt import e

HERE = Path(__file__).resolve().parent
# The export keeps sorting, filters and the theme switch; the run button, stars and chat need the app.
STRIP = ("// Ask about this page.", "})();")


def _script() -> str:
    js = (HERE / "app.js").read_text()
    js = js.replace('document.querySelector(\'meta[name="skew-token"]\').content', '""')
    head, _, _ = js.partition(STRIP[0])
    return head + "})();"


def export_html(out: Path) -> Path:
    with store.connect() as conn:
        report = store.report(conn)
    if not report:
        raise SystemExit("No report yet. Run ./skew scan first.")
    css = (HERE / "app.css").read_text()
    body = views.overview(report) + views.stocks(report)
    html = f"""<!doctype html><html lang="en" data-theme="system"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="skew-token" content="">
<title>Market Skew · {e(report['date'])}</title><style>{css}
.chat-opener, .chat, [data-run], .star {{ display: none !important; }}</style></head>
<body data-view="export"><header class="top"><div class="brand">Market Skew</div><div class="months"><h1>{e(report['date'])}</h1></div>
<div class="sync"><span class="synced">Built {e(report['built_at'][:16].replace('T', ' '))}</span>
<button class="quiet" type="button" data-theme-next>Light or dark</button></div></header>
<main>{body}<p class="hint" style="margin-top:40px">For your own research. Not financial advice.</p></main>
<div hidden class="chat"><div class="chat-log"></div><form data-chat-form><textarea></textarea><button></button></form><button data-chat-close></button><button data-chat-clear></button></div><button hidden data-chat-open></button>
<script>{_script()}</script></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out
