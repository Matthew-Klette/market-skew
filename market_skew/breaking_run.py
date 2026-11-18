"""Runs the counter-argument for the names on screen and keeps the answers in SQLite, one per company per data version.
Sequential, one `claude -p` call each, a failed call is skipped. Never fails the scan; never runs while a page renders."""
from . import breaking, funds, holdings, store

BOARD_TOP = 20


def on_screen(report: dict, rows: list[dict], owned: list[dict] | None = None, skip: set[str] | None = None) -> list[str]:
    """Steady picks, swing trades, US holdings that are companies and the Board's top WATCH names (by raw score), minus the
    tickers you can't buy. Order: picks, swing, holdings, board; no repeats."""
    skip = skip if skip is not None else holdings.excluded()
    owned = holdings.load() if owned is None else owned
    scored = {r["symbol"] for r in rows}
    board = [r["symbol"] for r in sorted(rows, key=lambda r: r["rank"]) if r["label"] == "WATCH"][:BOARD_TOP]
    wanted = ([p["symbol"] for p in report.get("picks") or []] + [t["symbol"] for t in report.get("swing") or []]
              + [h["symbol"] for h in owned if h["account"] == "usd" and h["symbol"] not in funds.FUNDS] + board)
    return [s for s in dict.fromkeys(wanted) if s in scored and s not in skip]


def run(conn, rows: list[dict], symbols: list[str], ask=breaking.ask, log=print) -> dict:
    """Asks for each symbol whose stored answer is missing or built on older numbers. Returns {asked, cached, failed}."""
    by_symbol = {r["symbol"]: r for r in rows}
    have = store.breaking(conn)
    asked = cached = failed = 0
    for symbol in symbols:
        row = by_symbol.get(symbol)
        if not row:
            continue
        if (have.get(symbol) or {}).get("version") == breaking.version(row):
            cached += 1
            continue
        try:
            answer = ask(row)
        except Exception as error:
            failed += 1
            log(f"breaking: {symbol} skipped ({error})"[:200])
            continue
        store.save_breaking(conn, symbol, breaking.version(row), answer)
        conn.commit()
        asked += 1
    return {"asked": asked, "cached": cached, "failed": failed}

