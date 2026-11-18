"""The POST side of the local server: the host check and one handler per path. `app` is the server module (its saves, locks and
scan control), passed in so this file never imports it. Every handler takes the parsed JSON object and returns (status, body)."""
import re

from .. import breaking, holdings, recommend_run, settings, store
from . import chat, money_ctx, plan_view

LOCAL_HOSTS = ("127.0.0.1", "localhost")
LENSES = ("auto", "mine", "his")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NOT_A_TICKER = (400, {"error": "Not a ticker."})
NOT_A_NUMBER = (400, {"error": "Not a number."})


def host_ok(header: str, port: int) -> bool:
    """The Host header must be exactly 127.0.0.1:<port> or localhost:<port> for this server's port: no suffixes, no userinfo."""
    host, sep, given = (header or "").strip().lower().rpartition(":")
    return bool(sep) and host in LOCAL_HOSTS and given.isascii() and given.isdigit() and int(given) == port and str(int(given)) == given


def _ticker(data: dict) -> str | None:
    symbol = str(data.get("symbol", "")).upper()
    return symbol if holdings.TICKER.fullmatch(symbol) else None


def _run(data, app):
    return 200, {"started": app.start_scan()}


def _watch(data, app):
    symbol = _ticker(data)
    return (200, {"on": app.toggle_watch(symbol)}) if symbol else NOT_A_TICKER


def _exclude(data, app):
    symbol = _ticker(data)
    if not symbol:
        return NOT_A_TICKER
    with app.WATCH_LOCK:
        holdings.exclude(symbol)
    return 200, {"excluded": symbol}


def _accept(data, app):
    import datetime as dt
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    app.save_prefs({"accepted_terms": stamp})
    return 200, {"accepted": stamp}


def _theme(data, app):
    theme = "dark" if data.get("theme") == "dark" else "light"
    app.save_prefs({"theme": theme})
    return 200, {"theme": theme}


def _settings(data, app):
    contact = str(data.get("sec_contact", "")).strip()
    if contact and not settings.valid_email(contact):
        return 400, {"error": "That doesn't look like an email address."}
    app.save_prefs({"sec_contact": contact})
    return 200, {"sec_contact": contact}


def _amounts(data, app):
    values = {}
    for key in plan_view.DEFAULT_AMOUNTS:
        if key in data:
            try:
                values[key] = max(0.0, min(float(data[key]), 1e9))
            except (TypeError, ValueError):
                return NOT_A_NUMBER
    return 200, {"amounts": app.save_amounts(app.month_key(), values)}


def _lens(data, app):
    if data.get("lens") not in LENSES:
        return 400, {"error": "Not a choice."}
    return 200, {"lens": app.save_lens(app.month_key(), data["lens"])}


def _plan(data, app):
    try:
        amount = max(0.0, min(float(data.get("usd", 0)), 1e9))
    except (TypeError, ValueError):
        return NOT_A_NUMBER
    return 200, {"rows": app.plan_rows(amount)}


def _ask(data, app):
    view = data.get("view") if data.get("view") in app.VIEW_PATHS.values() and data.get("view") != "money" else "overview"
    date = data.get("date") if isinstance(data.get("date"), str) and DATE.match(data["date"]) else None
    raw = data.get("turns") if isinstance(data.get("turns"), list) else []
    turns = [(t[0][:600], t[1][:4000]) for t in raw[-chat.MAX_TURNS:]
             if isinstance(t, list) and len(t) == 2 and all(isinstance(x, str) for x in t)]
    with store.connect() as conn:
        report = store.report(conn, date) or store.report(conn)
        history = store.history(conn) if view == "backtest" else None
        if report and view == "picks":
            report = recommend_run.enrich(conn, report)
            scores = breaking.apply(store.sentinel(conn, report["date"])[1], store.breaking(conn))
            report = {**report, "sentinel_brief": app.sentinel_brief(report, scores)}
    if not report:
        return 400, {"error": "There is no report to ask about yet."}
    try:
        return 200, {"answer": chat.ask(str(data.get("question", "")), turns, chat.brief(view, report, history))}
    except chat.ChatError as error:
        return 200, {"error": str(error)}


ROUTES = {"/accept": _accept, "/run": _run, "/watch": _watch, "/exclude": _exclude, "/theme": _theme, "/settings": _settings, "/amounts": _amounts,
          "/lens": _lens, "/plan": _plan, "/ask": _ask}


def dispatch(path: str, data: dict, app) -> tuple[int, dict]:
    if path in ROUTES:
        return ROUTES[path](data, app)
    if path in money_ctx.POSTS:
        return money_ctx.post(path, data, app.save_prefs)
    return 404, {"error": "Not found."}
