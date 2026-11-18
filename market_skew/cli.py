"""./skew scan | ui | status | export

No background schedule on purpose: the app scans when you open it (if the data is stale) and stops when you quit."""
import argparse
import datetime as dt
import sys
from pathlib import Path

from . import gate, holdings, scan, seed, store

ROOT = Path(__file__).resolve().parent.parent
def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv if venv.exists() else sys.executable)


def cmd_scan(args) -> int:
    scan.run(limit=args.limit)
    return 0


def cmd_status(_args) -> int:
    print(scan.read_status())
    with store.connect() as conn:
        body = store.report(conn)
    if not body:
        print("No report yet. Run ./skew scan")
        return 0
    print(f"\nReport {body['date']} ({body['with_skew']} of {body['universe']} names)\n")
    for line in body["read"]:
        print(" ·", line)
    return 0


def cmd_ui(args) -> int:
    from .ui.server import serve
    serve(port=args.port, exit_with_parent=args.exit_with_parent)
    return 0


def cmd_picks(_args) -> int:
    """Steady picks and His way trades for the latest report, through the quality-score gates (adjusted scores where Claude has
    checked, raw scores marked "not yet checked" otherwise), from stored data. No scan."""
    from . import earnings, market, selection, swing_run
    with store.connect() as conn:
        body = store.report(conn)
        if not body:
            print("No report yet. Run ./skew scan")
            return 1
        day = store.stocks_on(conn, body["date"]).merge(market.listings()[["symbol", "name", "market_cap"]], on="symbol", how="left")
        day["name"] = day["name"].str.replace(r"\s+(Common Stock|Class [A-C].*|Ordinary Shares.*|American Depositary.*)$", "", regex=True)
        entries = selection.gate_for(conn, body["date"])
        if not entries:
            print("No Quality scores yet, so nothing passes the gates. Run ./skew sentinel first.")
            return 1
        chosen = selection.choose_all(body, day, entries, holdings.excluded(), earnings.cached())
        if True:  # always let Claude check what was chosen
            from . import breaking_run
            rows, asked = store.sentinel(conn, body["date"])[1], set()
            for _ in range(6):  # Claude checks every chosen name, then the lists are picked again until they stop changing
                names = set(breaking_run.on_screen({**body, **chosen}, rows))
                if names <= asked:
                    break
                breaking_run.run(conn, rows, sorted(names - asked))
                earnings.refresh(sorted(names - asked))  # dates for the chosen names (cached a day, one a second)
                asked |= names
                chosen = selection.choose_all(body, day, selection.gate_for(conn, body["date"]), holdings.excluded(), earnings.cached())
        body = {**body, **chosen}
        store.drop_unselected(conn, body["date"], [p["symbol"] for p in body["picks"]], [t["symbol"] for t in body["swing"]])
        spy = None
        try:
            close, _ = market.prices(["SPY"], period="1mo")
            series = close["SPY"].dropna()
            spy = float(series[series.index.date <= dt.date.fromisoformat(body["date"])].iloc[-1])
        except Exception as error:
            print(f"warning: no SPY close for the paper record ({error})")
        store.add_paper(conn, body["date"], body["picks"], spy)
        body["swing_record"] = swing_run.update(conn, body["date"], body["swing"])
        store.save_report(conn, body["date"], body["built_at"], body)
    print("Steady picks:")
    for p in body["picks"]:
        print(f"  {p['symbol']:6} {p['timing_label']:18} {p['reasons'][0]}")
    print("His way:" + ("" if body["swing"] else f" none pass (Quality score {gate.HIS_WAY_MIN}+ and not Thin, then the timing rules); the 30% slice goes to the funds"))
    for t in body["swing"]:
        print(f"  {t['symbol']:6} entry ${t['entry']:,.2f}  stop ${t['stop']:,.2f}  target ${t['target']:,.2f}  {t['reasons'][0]}")
    return 0


def cmd_history(_args) -> int:
    """Ten years of monthly prices for your funds and USD/ZAR (Yahoo, no account), for the Money tab's goal and risk cards. No scan."""
    from . import history
    saved = history.refresh(force=True)
    for name in history.NAMES:
        levels = saved["levels"].get(name) or {}
        print(f"{name:7} {len(levels):3} months" + (f" ({min(levels)} to {max(levels)})" if levels else "  NOT FETCHED"))
    return 0 if all(saved["levels"].get(n) for n in history.NAMES) else 1


def cmd_read(_args) -> int:
    """Rebuilds Today's read for the latest report from its saved tables, with the rotation sentence (one small SPY 1y
    download for the 52-week high). No scan."""
    import pandas as pd
    from . import market, narrative
    with store.connect() as conn:
        body = store.report(conn)
        if not body:
            print("No report yet. Run ./skew scan")
            return 1
        high = market.spy_off_high()
        indexes = {**body["indexes"], "SPY": {**body["indexes"]["SPY"], **({"off_high": high} if high is not None else {})}}
        scored = store.stocks_on(conn, body["date"])
        read = narrative.todays_read(indexes, pd.DataFrame(body["themes"]), pd.DataFrame(body["sectors"]), scored, scan.watchlist())
        store.save_report(conn, body["date"], body["built_at"], {**body, "indexes": indexes, "read": read})
    for line in read:
        print(" ·", line)
    return 0


def cmd_predict(_args) -> int:
    """Fills Google's prediction for the latest report without a new scan (about 2 years of closes for ~10 names)."""
    import time
    from . import market, prediction
    started = time.time()
    with store.connect() as conn:
        body = store.report(conn)
        if not body:
            print("No report yet. Run ./skew scan")
            return 1
        names = prediction.screen_symbols(body)
        close, _ = market.prices(names, period="2y")
        body["predictions"] = prediction.forecast_many(names, close)
        scan.refresh_caches(body["date"])
        store.save_report(conn, body["date"], body["built_at"], body)
    for symbol, p in body["predictions"].items():
        print(f"{symbol:6} ${p['low']:,.2f} / ${p['mid']:,.2f} / ${p['high']:,.2f} (now ${p['last']:,.2f})  {p['verdict']}")
    print(f"{len(body['predictions'])} of {len(names)} names in {time.time() - started:.0f}s")
    return 0


def cmd_levels(_args) -> int:
    """Candidate buy levels and one-year chart data for the latest report's on-screen names (one 2-year price download). No scan."""
    from . import levels_run, market, prediction
    with store.connect() as conn:
        body = store.report(conn)
        if not body:
            print("No report yet. Run ./skew scan")
            return 1
        names = prediction.screen_symbols(body)
        close, _ = market.prices(names, period="2y")
        body["levels"] = levels_run.build(names, close)
        store.save_report(conn, body["date"], body["built_at"], body)
    for symbol, item in body["levels"].items():
        found = ", ".join(f"${x['level']:,.0f} ({x['touches']} touches, {x['distance_pct']:.0f}% below)" for x in item["levels"])
        print(f"{symbol:6} now ${item['last']:,.2f}  {found or 'no candidate floor'}")
    print(f"{len(body['levels'])} of {len(names)} names")
    return 0


def cmd_earnings(_args) -> int:
    """Next earnings date and track record for the latest report's on-screen names (paced, one name a second). No scan."""
    import time
    from . import earnings, prediction
    started = time.time()
    with store.connect() as conn:
        body = store.report(conn)
        if not body:
            print("No report yet. Run ./skew scan")
            return 1
        names = prediction.screen_symbols(body)
        body["earnings"] = earnings.refresh(names)
        store.save_report(conn, body["date"], body["built_at"], body)
    for symbol in names:
        print(f"{symbol:6} {earnings.line(body['earnings'].get(symbol)) or 'no earnings data'}")
    print(f"{len(body['earnings'])} of {len(names)} names in {time.time() - started:.0f}s")
    return 0


def cmd_funds(_args) -> int:
    """Fund timing signals for the latest report (4 option chains, paced) plus predictions for funds and swing names
    that lack one. No scan."""
    import time
    from . import funds, market, prediction
    started = time.time()
    with store.connect() as conn:
        body = store.report(conn)
        if not body:
            print("No report yet. Run ./skew scan")
            return 1
        names = list(dict.fromkeys(list(funds.FUNDS) + ["SPY"]))
        close, volume = market.prices(names, period="4mo")
        stats = market.price_stats(close, volume)
        spots = dict(zip(stats["symbol"], stats["close"]))
        today, readings = dt.date.today(), {}
        for symbol in names:
            try:
                readings[symbol], _ = market.chain_skew(symbol, spots[symbol], today)
            except Exception as error:
                print(f"{symbol}: no chain ({error})"[:200])
        body["funds"] = funds.compute(readings, stats, store.recent_reports(conn, body["date"]))
        wanted = [s for s in prediction.screen_symbols(body) if s not in (body.get("predictions") or {})]
        if wanted:
            long_close, _ = market.prices(wanted, period="2y")
            body["predictions"] = {**(body.get("predictions") or {}), **prediction.forecast_many(wanted, long_close)}
        scan.refresh_caches(body["date"])
        store.save_report(conn, body["date"], body["built_at"], body)
    for symbol, f in body["funds"].items():
        print(f"{symbol:5} {f['label']:18} skew {f['skew']*100:5.1f}% vs {f['baseline']*100:5.1f}% ({f['basis']})  1M {f['ret_1m']*100:+.1f}%  {f['bucket']}")
    print(f"predictions now: {', '.join(sorted(body.get('predictions') or {}))}  ({time.time() - started:.0f}s)")
    return 0


def cmd_fundamentals(_args) -> int:
    """Company numbers from SEC EDGAR for the latest report's names (cached frames, ~160 paced requests the first time)."""
    import time
    from . import fundamentals_run
    started = time.time()
    with store.connect() as conn:
        body = store.report(conn)
        symbols = store.stocks_on(conn, body["date"])["symbol"].tolist() if body else []
        if not symbols:
            print("No report yet. Run ./skew scan")
            return 1
        try:
            out = fundamentals_run.refresh(conn, symbols)
        except Exception as error:
            print(f"No company numbers: {error}"[:300])
            return 1
    print(f"{out['rows']} of {out['universe']} names have company numbers; {out['requests']} requests "
          f"({out['failed']} failed) in {time.time() - started:.0f}s")
    return 0


def cmd_sentinel(_args) -> int:
    """Rescore every company from the stored numbers and prices, without a scan."""
    from . import sentinel_run
    with store.connect() as conn:
        try:
            date, count = sentinel_run.recompute(conn)
        except RuntimeError as error:
            print(error)
            return 1
    print(f"Quality score: {count} companies scored for {date}." if count else
          "No company numbers yet. Add your email in Settings; they download weekly during the scan (or run ./skew fundamentals).")
    return 0


def cmd_value(_args) -> int:
    """Recompute each company's fair-value range (bear/base/bull) from the stored numbers and prices, without a scan."""
    from . import sentinel_run
    with store.connect() as conn:
        date, count, ranged = sentinel_run.revalue(conn)
    print(f"Fair-value range: {ranged} of {count} companies for {date}." if count else "No Quality scores yet. Run ./skew sentinel first.")
    return 0 if count else 1


def cmd_breaking(_args) -> int:
    """Claude argues against each on-screen company from its saved numbers (one `claude -p` call each, saved per data
    version; companies whose numbers have not changed are skipped). No scan."""
    import time
    from . import breaking_run
    started = time.time()
    with store.connect() as conn:
        body = store.report(conn)
        if not body:
            print("No report yet. Run ./skew scan")
            return 1
        rows = store.sentinel(conn, body["date"])[1]
        names = breaking_run.on_screen(body, rows)
        if not names:
            print("No on-screen company has a Quality score yet. Run ./skew sentinel first.")
            return 1
        print(f"{len(names)} on-screen companies: {', '.join(names)}", flush=True)
        out = breaking_run.run(conn, rows, names)
    print(f"Breaking: {out['asked']} asked, {out['cached']} already saved, {out['failed']} skipped in {time.time() - started:.0f}s.")
    return 0


def cmd_export(args) -> int:
    from .ui.export import export_html
    out = Path(args.out or ROOT / "data" / f"market-skew-{dt.date.today()}.html")
    export_html(out)
    print(out)
    return 0


def main(argv=None) -> int:
    seed.startup()
    parser = argparse.ArgumentParser(prog="skew", description="Market Skew: price vs options bets, every US stock that matters.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="run the daily scan now (10-20 min)")
    p.add_argument("--limit", type=int, default=scan.UNIVERSE)
    p.set_defaults(func=cmd_scan)
    sub.add_parser("status", help="last report's Today's read").set_defaults(func=cmd_status)
    p = sub.add_parser("ui", help="the dashboard on this Mac")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--exit-with-parent", action="store_true")
    p.set_defaults(func=cmd_ui)
    sub.add_parser("repick", help="same as picks").set_defaults(func=cmd_picks)
    sub.add_parser("picks", help="Steady picks + His way trades through the quality-score gates for the latest report, without a scan").set_defaults(func=cmd_picks)
    sub.add_parser("swing", help="same as picks (His way is chosen together with Steady)").set_defaults(func=cmd_picks)
    sub.add_parser("history", help="monthly price history for your funds (about 10 years) for the Money tab's goal and risk cards, without a scan").set_defaults(func=cmd_history)
    sub.add_parser("read", help="rebuild Today's read (with the rotation sentence) for the latest report, without a scan").set_defaults(func=cmd_read)
    sub.add_parser("predict", help="add Google's prediction to the latest report without a new scan").set_defaults(func=cmd_predict)
    sub.add_parser("levels", help="candidate buy levels + one-year charts for the latest report's names, without a scan").set_defaults(func=cmd_levels)
    sub.add_parser("earnings", help="next earnings date + track record for the latest report's names, without a scan").set_defaults(func=cmd_earnings)
    sub.add_parser("funds", help="fund timing signals + missing predictions for the latest report, without a new scan").set_defaults(func=cmd_funds)
    sub.add_parser("fundamentals", help="company numbers from SEC EDGAR for the latest report's names, without a scan").set_defaults(func=cmd_fundamentals)
    sub.add_parser("value", help="recompute each company's fair-value range from stored numbers, without a scan").set_defaults(func=cmd_value)
    sub.add_parser("sentinel", help="rescore every company (Quality score) from stored numbers, without a scan").set_defaults(func=cmd_sentinel)
    sub.add_parser("breaking", help="Claude argues against each on-screen company (Quality score deductions), without a scan").set_defaults(func=cmd_breaking)
    p = sub.add_parser("export", help="one self-contained HTML file of the latest report")
    p.add_argument("--out")
    p.set_defaults(func=cmd_export)
    args = parser.parse_args(argv)
    return args.func(args)
