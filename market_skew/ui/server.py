"""Local dashboard on 127.0.0.1. Read-only views plus four small actions: run a scan, star a ticker, theme, ask."""
import datetime
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import atomic, breaking, funds, fx, holdings, jse, prediction, recommend_run, scan, store
from ..backtest import summary
from ..picks import holdings_check, without
from . import money_ctx, money_view, plan_view, research_view, routes, views

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PREFS = ROOT / "config" / "prefs.json"
STATIC = {"/app.css": ("app.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8")}
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin", "Cache-Control": "no-store",
}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TICKER = holdings.TICKER
WATCH_LOCK = threading.Lock()
PREFS_LOCK = threading.Lock()
MAX_BODY = 32 * 1024
TOKEN = secrets.token_urlsafe(24)
VIEW_PATHS = {"/": "picks", "/money": "money", "/market": "overview", "/research": "research", "/stocks": "stocks", "/backtest": "backtest", "/how": "how"}
CARD = re.compile(r"/research/([^/]+)")


def prefs() -> dict:
    try:
        return json.loads(PREFS.read_text())
    except (OSError, ValueError):
        return {}


def update_prefs(change) -> None:
    """Read, change and write prefs under one lock; the write is a temp file renamed into place, so a crash or a second
    request never leaves a half-written file. `change(saved)` returns the keys to set."""
    with PREFS_LOCK:
        merged = {**prefs(), **change(prefs())}
        temp = PREFS.with_name(PREFS.name + ".tmp")
        temp.write_text(json.dumps(merged))
        os.replace(temp, PREFS)


def save_prefs(values: dict) -> None:
    update_prefs(lambda _saved: values)


def month_key(today: datetime.date | None = None) -> str:
    return (today or datetime.date.today()).strftime("%Y-%m")


def amounts_for(month: str, saved: dict | None = None) -> dict:
    """This month's TFSA and USD amounts in rand; unset values fall back to the defaults."""
    stored = ((saved if saved is not None else prefs()).get("amounts") or {}).get(month) or {}
    out = {}
    for key, default in plan_view.DEFAULT_AMOUNTS.items():
        value = stored.get(key)
        out[key] = float(value) if isinstance(value, (int, float)) and value >= 0 else default
    return out


def amounts_set(month: str, saved: dict | None = None) -> bool:
    """False on a fresh install: nothing saved for this month yet, so Picks asks instead of assuming."""
    stored = ((saved if saved is not None else prefs()).get("amounts") or {}).get(month) or {}
    return any(isinstance(stored.get(k), (int, float)) and stored[k] > 0 for k in plan_view.DEFAULT_AMOUNTS)


def save_amounts(month: str, values: dict) -> dict:
    """Merge into that month's amounts (other months untouched) and return them."""
    merged: dict = {}

    def change(saved: dict) -> dict:
        merged.update(amounts_for(month, saved), **values)
        return {"amounts": {**(saved.get("amounts") or {}), month: dict(merged)}}
    update_prefs(change)
    return merged


LENSES = routes.LENSES


def lens_choice(month: str, saved: dict | None = None) -> str:
    """What you picked for this month: "auto" (follow Recommended), "mine" (Steady picks) or "his" (swing trades)."""
    value = ((saved if saved is not None else prefs()).get("lens") or {}).get(month)
    return value if value in LENSES else "auto"


def lens_for(month: str, saved: dict | None = None, recommended: str = "mine") -> str:
    """The lens the USD plan follows: your pick, or the recommendation when you left it on auto."""
    choice = lens_choice(month, saved)
    return recommended if choice == "auto" else choice


def save_lens(month: str, choice: str) -> str:
    update_prefs(lambda saved: {"lens": {**(saved.get("lens") or {}), month: choice}})
    return choice


def toggle_watch(symbol: str) -> bool:
    with WATCH_LOCK:
        return _toggle(symbol)


def _toggle(symbol: str) -> bool:
    current = [line for line in (scan.WATCHLIST.read_text().splitlines() if scan.WATCHLIST.exists() else [])]
    tickers = {line.strip().upper() for line in current if line.strip() and not line.startswith("#")}
    on = symbol not in tickers
    kept = [line for line in current if line.strip().upper() != symbol]
    atomic.write_text(scan.WATCHLIST, "\n".join(kept + ([symbol] if on else [])) + "\n")
    return on


_scan_child: list[subprocess.Popen] = []


def stop_scan() -> None:
    """The scan belongs to the app: quitting the app stops it, so nothing keeps working in the background."""
    stopped = False
    for child in _scan_child:
        if child.poll() is None:
            stopped = True
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
    if stopped:
        scan.LOCK.unlink(missing_ok=True)
        scan.write_status(state="stopped", step="Stopped when the app closed. It picks up again next time you open it.")


def start_scan() -> bool:
    _scan_child[:] = [child for child in _scan_child if child.poll() is None]  # forget finished scans
    if _scan_child or scan.read_status().get("state") == "running":
        return False
    log = (ROOT / "data" / "logs")
    log.mkdir(parents=True, exist_ok=True)
    python = ROOT / ".venv" / "bin" / "python"
    child = subprocess.Popen([str(python if python.exists() else sys.executable), "-B", str(ROOT / "skew"), "scan"], cwd=ROOT,
                             stdout=open(log / "scan.log", "a"), stderr=subprocess.STDOUT,
                             preexec_fn=lambda: os.nice(10))  # low priority so the Mac stays responsive
    _scan_child.append(child)
    scan.write_status(state="running", step="Starting", done=0, total=0)
    return True


def _picks(report: dict) -> str:
    """Rand rate and JSE prices come from the saved caches (the scan refreshes them); the page never waits on the network."""
    rate = fx.cached()
    quotes = jse.cached() or report.get("jse") or {}
    mine = holdings.rows(holdings.load(), report.get("holdings") or [], quotes)
    rec = report["recommendation"]
    choice = lens_choice(month_key())
    buys = {h["symbol"]: holdings.buy_price(h) for h in holdings.load() if holdings.buy_price(h)}
    shown = {**report, **money_ctx.plan_lean(report, prefs()), "jse": quotes, "holdings": mine, "last_buys": buys, "rate_date": (rate or {}).get("date"),
             "forecaster_missing": not prediction.available() and not report.get("predictions")}
    return views.picks_page(shown, amounts_for(month_key()), (rate or {}).get("rate"),
                            lens_for(month_key(), recommended=rec["lens"]), choice, rec, amounts_set(month_key()))


def sentinel_chip(row: dict) -> dict:
    """What a Picks card needs from a company's adjusted Quality score row."""
    return {"score": row["score"], "raw": row["raw_score"], "label": row["label"], "checked": row.get("breaking") is not None}


def sentinel_brief(report: dict, scores: list[dict]) -> list[dict]:
    """The adjusted score and what_breaks of each Steady pick and swing trade, for the chat brief."""
    shown = {x["symbol"] for x in (report.get("picks") or []) + (report.get("swing") or [])}
    return [{**sentinel_chip(r), "symbol": r["symbol"], "what_breaks": (r.get("breaking") or {}).get("what_breaks")}
            for r in scores if r["symbol"] in shown]


def on_screen(report: dict) -> dict:
    """What the Picks page and the /plan table both use: picks and swing trades without the names you can't buy,
    plus the Steady record and the recommendation. Reads saved data only."""
    skip = holdings.excluded()
    report = {**report, "picks": without(report.get("picks") or [], skip)}
    if report.get("swing") is not None:
        report = {**report, "swing": without(report["swing"], skip)}
    with store.connect() as conn:
        return recommend_run.enrich(conn, report)


def plan_rows(amount: float) -> str:
    """USD table rows for an amount, from the latest report (same lens and exclusions as the page)."""
    with store.connect() as conn:
        report = store.report(conn) or {}
    report = on_screen(report) if report.get("date") else report
    rec = report.get("recommendation") or {"lens": "mine"}
    rate = (fx.cached() or {}).get("rate")
    report = {**report, **money_ctx.plan_lean(report, prefs())}
    return plan_view.usd_body(plan_view.usd_lines(report, amount, lens_for(month_key(), recommended=rec["lens"]), rate), rate)


def render(path: str, query: dict) -> tuple[int, str]:
    card = CARD.fullmatch(path)
    symbol = card.group(1).upper() if card else None
    if card and not TICKER.fullmatch(symbol):
        return 404, "Not found"
    view = "research" if card else VIEW_PATHS.get(path)
    if not view:
        return 404, "Not found"
    date = query.get("date", [None])[0]
    date = date if date and DATE.match(date) else None
    with store.connect() as conn:
        dates = store.report_dates(conn)
        report = store.report(conn, date) or store.report(conn)
        history = store.history(conn) if view == "backtest" else None
        scores = []
        if view in ("research", "picks"):  # adjusted scores: the stored Quality score rows minus Claude's saved deductions
            scores = breaking.apply(store.sentinel(conn, report["date"] if report else None)[1], store.breaking(conn))
    if report:  # stars and warning lights follow the live watchlist, not the one saved with the scan
        watching = scan.watchlist()
        report = {**report, "stocks": [{**s, "watch": s["symbol"] in watching} for s in report["stocks"]]}
        if view == "picks":
            with store.connect() as conn:
                day = store.stocks_on(conn, report["date"])
            names = {s["symbol"]: s.get("name") for s in report["stocks"]}
            owned = {h["symbol"] for h in holdings.load() if h["account"] == "usd"}
            lights = holdings_check(day.assign(name=day["symbol"].map(names)), owned) if not day.empty else []
            fund_rows = {s: funds.as_holding(s, f) for s, f in (report.get("funds") or {}).items() if s in owned}
            report["holdings"] = [fund_rows.get(x["symbol"], x) if x["light"] == "none" else x for x in lights]
            report["holdings"] += [fund_rows[s] for s in sorted(fund_rows) if s not in {x["symbol"] for x in lights}]
            report = {**on_screen(report), "sentinel": {r["symbol"]: sentinel_chip(r) for r in scores}}
            report["sentinel_brief"] = sentinel_brief(report, scores)
    status = scan.read_status()
    theme = prefs().get("theme", "system")
    if not prefs().get("accepted_terms"):  # a one-time "not financial advice" screen before anything else
        body = views.accept_gate()
    elif view == "how":
        body = views.how(prefs().get("sec_contact") or "")
    elif view == "backtest":
        body = views.backtest(summary(history))
    elif view == "research":
        body = research_view.page(scores, report, symbol)
    elif view == "money":
        body = money_view.page(money_ctx.page_ctx(report, prefs(), amounts_for(month_key())))
    elif not report:
        body = views.empty_state() + (plan_view.first_run() if view == "picks" and not amounts_set(month_key()) else "")
    else:
        body = {"overview": views.overview, "stocks": views.stocks}.get(view, lambda r: _picks(r))(report)
    return 200, views.shell(view, dict((k, l) for k, _, l in views.TABS)[view], body, report, dates, TOKEN, theme, status)


class Handler(BaseHTTPRequestHandler):
    server_version = "MarketSkew"

    def log_message(self, *_):
        pass

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        for k, v in HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, value) -> None:
        self._send(code, json.dumps(value).encode(), "application/json; charset=utf-8")

    def _local(self) -> bool:
        return routes.host_ok(self.headers.get("Host", ""), self.server.server_address[1])

    def do_GET(self):
        if not self._local():
            return self._send(421, b"Wrong host", "text/plain")
        url = urllib.parse.urlsplit(self.path)
        if url.path in STATIC:
            name, kind = STATIC[url.path]
            return self._send(200, (HERE / name).read_bytes(), kind)
        if url.path == "/status":
            return self._json(200, scan.read_status())
        code, html = render(url.path, urllib.parse.parse_qs(url.query))
        self._send(code, html.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        sent = self.headers.get("X-Skew-Token", "").encode("utf-8", "replace")
        if not self._local() or not secrets.compare_digest(sent, TOKEN.encode()):
            return self._json(403, {"error": "The app restarted. Reload the page."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            return self._json(413, {"error": "Too long."})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "Bad request."})
        if not isinstance(data, dict):
            return self._json(400, {"error": "Bad request."})
        self._json(*routes.dispatch(urllib.parse.urlsplit(self.path).path, data, sys.modules[__name__]))


def _watch_parent() -> None:
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            stop_scan()
            os._exit(0)


def _scan_if_stale() -> None:
    with store.connect() as conn:
        latest = store.report(conn)
    if scan.is_stale(latest):
        start_scan()


def serve(port: int = 8765, exit_with_parent: bool = False) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(url, flush=True)
    if exit_with_parent:  # running inside the app: scan on open when needed, stop with the app
        threading.Thread(target=_watch_parent, daemon=True).start()
        import signal
        signal.signal(signal.SIGTERM, lambda *_: (stop_scan(), os._exit(0)))
        _scan_if_stale()
    httpd.serve_forever()
