"""The daily run: listing -> prices -> top 2000 by dollar volume -> option chains -> report. About 10-20 minutes."""
import datetime as dt
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from . import breaking_run, earnings, fundamentals_run, funds, sentinel_run, fx, history, holdings, jse, levels_run, market, prediction, recommend_run, report, selection, steady_record, store, swing_run
from .sectors import INDEXES, SECTOR_ETFS, VOL_INDEX

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / "data" / "status.json"
LOCK = ROOT / "data" / "run.lock"
THEMES = ROOT / "config" / "themes.json"
WATCHLIST = ROOT / "config" / "watchlist.txt"
UNIVERSE = 2000
CANDIDATES = 3000
WORKERS = 3          # 6 got the session throttled after ~1,000 chains on 2026-11-18
RETRY_WORKERS = 1
RETRY_PAUSE_SECONDS = 30
FINISH_SECONDS = 15          # building the report after the last chain
PRICE_SECONDS = 75           # listing + prices, measured on 2026-11-18
CHAINS_PER_SECOND = 2.8      # the pace limit in market.py; used for the estimate before the first chain lands
MAX_FAIL_SHARE = 0.30  # a run that loses more chains than this is throttled, not a real read; keep the old report


def themes() -> dict[str, list[str]]:
    return {k: v for k, v in json.loads(THEMES.read_text()).items() if not k.startswith("_")}


def watchlist() -> set[str]:
    if not WATCHLIST.exists():
        return set()
    return {line.strip().upper() for line in WATCHLIST.read_text().splitlines() if line.strip() and not line.startswith("#")}


def write_status(**fields) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    temp = STATUS.with_suffix(".tmp")
    temp.write_text(json.dumps({**fields, "updated": dt.datetime.now().isoformat(timespec="seconds")}))
    temp.replace(STATUS)


def _lock_alive() -> bool:
    try:
        os.kill(int(LOCK.read_text().strip() or "0"), 0)
        return True
    except (OSError, ValueError):
        return False


def read_status() -> dict:
    try:
        status = json.loads(STATUS.read_text())
    except (OSError, ValueError):
        return {"state": "idle"}
    started = dt.datetime.fromisoformat(status.get("updated", "1970-01-01T00:00:00"))
    fresh = (dt.datetime.now() - started).total_seconds() < 60  # a run just launched may not hold the lock yet
    if status.get("state") == "running" and not _lock_alive() and not fresh:
        return {**status, "state": "failed", "step": "The last run stopped before finishing (Mac asleep or closed?)."}
    return status


def _take_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        pid = LOCK.read_text().strip() or "0"
        try:
            os.kill(int(pid), 0)
            return False  # a run is already going
        except (OSError, ValueError):
            LOCK.unlink(missing_ok=True)  # stale lock from a run that died
            return _take_lock()
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def market_open(now: dt.datetime | None = None) -> bool:
    """True while New York trades (9:30-16:00 ET, weekdays). Today's bar is partial then."""
    from zoneinfo import ZoneInfo
    ny = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return ny.weekday() < 5 and dt.time(9, 30) <= ny.time() < dt.time(16, 0)


def _fetch(symbols, spots, today, readings, workers, label, log, stage=2, retries=market.RETRIES) -> list[str]:
    """Fills readings[symbol] = (reading, expiry). Returns the symbols that failed."""
    failed = []
    phase_start = time.time()
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(market.chain_skew, s, spots[s], today, retries): s for s in symbols}
        for n, future in enumerate(as_completed(futures), 1):
            symbol = futures[future]
            try:
                readings[symbol] = future.result()
            except Exception as error:
                failed.append(symbol)
                if len(failed) <= 10:
                    log(f"chain failed: {error}"[:300])
            if n % 10 == 0 or n == len(futures):
                rate = n / max(time.time() - phase_start, 1e-6)
                eta = (len(futures) - n) / rate + FINISH_SECONDS
                write_status(state="running", step=label, done=n, total=len(futures), stage=stage, eta=round(eta))
    return failed


def last_close(now: dt.datetime | None = None) -> dt.date:
    """The New York session whose close is the newest one that has happened (weekends skipped, holidays not)."""
    from zoneinfo import ZoneInfo
    ny = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    day = ny.date() if ny.time() >= dt.time(16, 0) else ny.date() - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def is_stale(report: dict | None, now: dt.datetime | None = None) -> bool:
    """Once a day: scan on open only if no report has been built since the latest New York close
    (16:00 New York = 23:00 SAST, 22:00 while the US is on daylight time). Reopening the app does nothing until the next close.
    `covers` is the close a report was built for, so a US holiday costs one scan, not one per open."""
    if not report:
        return True
    covers = report.get("covers") or ("" if report.get("intraday") else report["date"])
    return not covers or dt.date.fromisoformat(covers) < last_close(now)


def _levels(names: list[str], long_close) -> dict:
    """Candidate buy levels + one-year chart series from the closes already downloaded. A failure leaves them out."""
    try:
        return levels_run.build(names, long_close)
    except Exception as error:
        print(f"levels step skipped: {error}"[:300], flush=True)
        return {}


def _earnings(body: dict) -> dict:
    """Next earnings date and track record for the on-screen stocks (sequential, paced, cached; funds are marked as funds)."""
    try:
        names = prediction.screen_symbols(body)
        write_status(state="running", step="Earnings dates", done=0, total=len(names), stage=3, eta=len(names) * 3)
        return earnings.refresh(names)
    except Exception as error:
        print(f"earnings step skipped: {error}"[:300], flush=True)
        return {}


def _names(body: dict) -> list[str]:
    """The Picks page names. If the full list (which reads the holdings file) fails, the funds, picks and swing trades still count."""
    try:
        return prediction.screen_symbols(body)
    except Exception as error:
        print(f"screen names fell back to funds, picks and swing trades: {error}"[:300], flush=True)
        return list(dict.fromkeys(list(funds.FUNDS) + [p["symbol"] for p in body.get("picks") or []]
                                  + [t["symbol"] for t in body.get("swing") or []]))


def _dates(body: dict, done: set[str]) -> bool:
    """Fetch earnings dates (cached for a day) for on-screen names not yet fetched in this scan. True when any were new."""
    try:
        new = [n for n in _names(body) if n not in done]
        if not new:
            return False
        write_status(state="running", step="Earnings dates", done=0, total=len(new), stage=3, eta=len(new) * 3)
        earnings.refresh(new)
        done.update(new)
        return True
    except Exception as error:
        print(f"earnings dates step skipped: {error}"[:300], flush=True)
        return False


def _predict(body: dict, close, date: str, fetch=market.prices, runner=None) -> dict:
    """Google's prediction for the Picks page names. It needs about two years of closes, so those names are fetched
    again at that length (the scan's own frame only holds four months). Levels are saved before the forecast starts and
    each step fails alone: slow or broken never fails the scan, and a failed forecast never drops the levels."""
    names = _names(body)
    try:
        write_status(state="running", step="Google's prediction", done=0, total=len(names), stage=3, eta=len(names) * 8)
        try:
            long_close, _ = fetch(names, period="2y")
        except Exception as error:
            print(f"2-year prices failed ({error}); using the scan's own closes"[:300], flush=True)
            long_close = close
        body["levels"] = _levels(names, long_close)
    except Exception as error:
        print(f"levels step skipped: {error}"[:300], flush=True)
        return {}
    try:
        return prediction.forecast_many(
            names, long_close, runner or prediction.run_wrapper, on_done=lambda n, total: write_status(
                state="running", step="Google's prediction", done=n, total=total, stage=3, eta=(total - n) * 8))
    except Exception as error:
        print(f"prediction step skipped: {error}"[:300], flush=True)
        return {}


def _paper(conn, body: dict, close, symbols, date: str, fetch=market.prices) -> None:
    """Steady paper record upkeep. Picks that have left the scan universe still get a close (small fetch, saved in the
    report as paper_closes) so their rows don't silently drop; settled picks are frozen at their day-28 close."""
    try:
        rows = store.paper_rows(conn)
        if not rows:
            return
        outside = [r["symbol"] for r in rows if r["symbol"] not in set(symbols)]
        have = [s for s in outside if s in close and not close[s].dropna().empty]
        lacking = [s for s in outside if s not in have]
        extra = fetch(lacking, period="6mo")[0] if lacking else pd.DataFrame()
        frame = close.join(extra.drop(columns=[c for c in extra if c in close]), how="outer").sort_index() if len(extra.columns) else close
        body["paper_closes"] = {s: float(frame[s].dropna().iloc[-1]) for s in outside if s in frame and not frame[s].dropna().empty}
        voo = frame["VOO"] if "VOO" in frame else None
        for symbol, pick, compare in steady_record.freezes(rows, frame, voo, date):
            store.freeze_paper(conn, symbol, pick, compare)
    except Exception as error:
        print(f"paper record step skipped: {error}"[:300], flush=True)


def refresh_caches(day: str) -> dict:
    """The only place (with the predict/funds/swing commands) that fetches the rand rate, JSE prices and VOO closes.
    The page reads what this saves. Returns the JSE quotes."""
    for step in (fx.refresh, lambda: recommend_run.refresh_voo(day), history.refresh):  # history: at most weekly
        try:
            step()
        except Exception as error:
            print(f"cache refresh skipped: {error}"[:200], flush=True)
    try:
        return jse.refresh()
    except Exception as error:
        print(f"JSE refresh skipped: {error}"[:200], flush=True)
        return jse.cached()


def _select(conn, body: dict, scored, date: str) -> None:
    """Both lists, through the quality-score gates (adjusted scores where Claude has checked, raw scores marked as such where not).
    A failure keeps whatever lists the body already has."""
    try:
        body.update(selection.choose_all(body, scored, selection.gate_for(conn, date), holdings.excluded(), earnings.cached()))
    except Exception as error:
        print(f"selection step skipped: {error}"[:300], flush=True)


def _swing(conn, body: dict, close, date: str) -> None:
    """His way: the final trades go into the paper table and open ones settle. A failure never fails the scan."""
    try:
        body["swing_record"] = swing_run.update(conn, date, body["swing"], close)
    except Exception as error:
        print(f"swing step skipped: {error}"[:300], flush=True)


SELECT_ROUNDS = 6  # 2 left unchecked names in the lists on 2026-11-18


def _screened(conn, body: dict, scored, date: str) -> None:
    """Order that makes the gates work on the first scan of a week: (weekly numbers and Quality score already done) select with
    the fresh Quality score -> Claude argues against the on-screen names -> select again with the adjusted scores, and once more
    for any name that only appeared after that. Names Claude has not reached yet stay at their raw score."""
    asked: set[str] = set()
    dated: set[str] = set()
    for _ in range(SELECT_ROUNDS):  # each round can only lower scores, so the lists settle once every chosen name is checked
        _select(conn, body, scored, date)
        names = set(breaking_run.on_screen(body, store.sentinel(conn, date)[1]))
        fresh = _dates(body, dated)  # earnings dates for the chosen names, so the 7-day guard bites on a name's first day
        if names <= asked and not fresh:
            break
        if not names <= asked:
            _breaking(conn, body, date)
            asked |= names
    _select(conn, body, scored, date)


def _fundamentals(conn, symbols: list[str]) -> None:
    """Weekly: company numbers from SEC EDGAR (cached frames; nothing is fetched while they are under a week old).
    A failure never fails the scan."""
    try:
        write_status(state="running", step="Company numbers (weekly)", done=0, total=0, stage=3, eta=60)
        out = fundamentals_run.refresh(conn, symbols)
        print(f"company numbers: {out['rows']} of {out['universe']} names, {out['requests']} requests", flush=True)
    except Exception as error:
        print(f"company numbers step skipped: {error}"[:300], flush=True)


def _sentinel(conn, scored, close, date: str) -> None:
    """Scores every company that has company numbers (none until the SEC download has run). A failure never fails the scan."""
    try:
        write_status(state="running", step="Quality scores", done=0, total=0, stage=3, eta=30)
        count = sentinel_run.refresh(conn, date, scored, close)
        print(f"quality scores: {count} companies", flush=True)
    except Exception as error:
        print(f"quality score step skipped: {error}"[:300], flush=True)


def _breaking(conn, body: dict, date: str) -> list[str]:
    """Claude argues against each on-screen company (saved per data version; only changed numbers are asked again).
    Returns the names it went through. A failure never fails the scan."""
    try:
        rows = store.sentinel(conn, date)[1]
        names = breaking_run.on_screen(body, rows)
        write_status(state="running", step="Claude's counter-argument", done=0, total=len(names), stage=3, eta=len(names) * 12)
        out = breaking_run.run(conn, rows, names)
        print(f"counter-arguments: {out['asked']} asked, {out['cached']} cached, {out['failed']} skipped", flush=True)
        return names
    except Exception as error:
        print(f"counter-argument step skipped: {error}"[:300], flush=True)
        return []


def run(limit: int = UNIVERSE, log=print) -> dict:
    if not _take_lock():
        raise RuntimeError("A scan is already running.")
    started = time.time()
    try:
        first_eta = round(PRICE_SECONDS + (limit + 4) / CHAINS_PER_SECOND + FINISH_SECONDS)
        write_status(state="running", step="Listing US stocks", done=0, total=0, stage=1, eta=first_eta)
        listing = market.listings()
        candidates = listing["symbol"].head(max(CANDIDATES, limit + 500)).tolist()
        extras = list(dict.fromkeys(list(INDEXES) + list(SECTOR_ETFS.values()) + [VOL_INDEX] + list(funds.FUNDS)))
        write_status(state="running", step=f"Downloading prices for {len(candidates):,} stocks", done=0, total=0, stage=1,
                     eta=round(first_eta - (time.time() - started)))
        close, volume = market.prices(candidates + extras)
        covers = last_close()
        if market_open():  # New York is mid-session: use the last finished day, not a half-built one
            from zoneinfo import ZoneInfo
            ny_today = dt.datetime.now(ZoneInfo("America/New_York")).date()
            keep = close.index.date < ny_today
            close, volume = close[keep], volume[keep]
        stats = market.price_stats(close, volume)
        date = close.index[-1].date().isoformat()
        idx_stats = stats[stats["symbol"].isin(list(INDEXES) + [VOL_INDEX])].set_index("symbol")
        indexes = {("VIX" if k == VOL_INDEX else k): row[["ret_1d", "ret_1w", "ret_1m"]].astype(float).to_dict()
                   for k, row in idx_stats.iterrows()}
        high = market.spy_off_high()  # one small 1y download; left out of Today's read when it fails
        if high is not None and "SPY" in indexes:
            indexes = {**indexes, "SPY": {**indexes["SPY"], "off_high": high}}
        heatmap = market.weekly_relative(close, SECTOR_ETFS)
        stocks = stats[stats["symbol"].isin(candidates)].nlargest(limit, "dvol_21")
        stocks = stocks.merge(listing[["symbol", "name", "market_cap"]], on="symbol", how="left")
        stocks["name"] = stocks["name"].str.replace(r"\s+(Common Stock|Class [A-C].*|Ordinary Shares.*|American Depositary.*)$", "", regex=True)
        symbols = stocks["symbol"].tolist()
        with store.connect() as conn:
            sector_of = dict(zip(listing["symbol"], listing["sector"]))
            today = dt.date.today()
            spots = dict(zip(stats["symbol"], stats["close"]))
            targets = list(dict.fromkeys(list(INDEXES) + list(funds.FUNDS))) + symbols  # indexes first: SPY's expiry and the index skew tile need them
            readings, expiry = {}, None
            wanted = [s for s in targets if s in spots]
            failed = _fetch(wanted, spots, today, readings, WORKERS, "Reading option bets", log)
            if failed:
                write_status(state="running", step=f"Pausing so Yahoo doesn't block us, then retrying {len(failed)}", done=0,
                             total=len(failed), stage=3, eta=round(RETRY_PAUSE_SECONDS + len(failed) * 1.5 + FINISH_SECONDS))
                time.sleep(RETRY_PAUSE_SECONDS)
                failed = _fetch(failed, spots, today, readings, RETRY_WORKERS, "Retrying the ones that failed", log, stage=3, retries=1)
            expiry = readings.get("SPY")[1] if readings.get("SPY") else None
            readings = {s: r for s, (r, _) in readings.items()}
            futures = wanted
            share = len(failed) / max(len(futures), 1)
            if share > MAX_FAIL_SHARE:
                raise RuntimeError(f"Yahoo refused {len(failed)} of {len(futures)} option chains ({share:.0%}). "
                                   "Kept the previous report. Try again later.")
            index_skew = {k: readings[k].skew for k in INDEXES if readings.get(k)}
            prev = store.previous_skew(conn, date)
            body, scored = report.build(
                date, dt.datetime.now().isoformat(timespec="seconds"), stocks, readings, sector_of, themes(),
                indexes, index_skew, heatmap, prev, watchlist(), expiry, sorted(failed))
            body["history_days"] = len(store.report_dates(conn))
            body["seconds"] = round(time.time() - started)
            body["intraday"] = False  # prices always end at a finished session now
            body["covers"] = covers.isoformat()
            body["funds"] = funds.compute(readings, stats, store.recent_reports(conn, date))
            body["jse"] = refresh_caches(date)  # rand rate, rand prices for the TFSA fund and VOO closes, saved for the page
            store.save_stocks(conn, date, scored)
            body["picks"], body["swing"] = [], []  # nothing is on screen until the quality-score gates have run
            _fundamentals(conn, symbols)
            _sentinel(conn, scored, close, date)
            _screened(conn, body, scored, date)
            store.add_paper(conn, date, body["picks"], dict(zip(stats["symbol"], stats["close"])).get("SPY"))
            _paper(conn, body, close, symbols, date)
            _swing(conn, body, close, date)
            body["predictions"] = _predict(body, close, date)  # after selection, so His way names get a range too
            body["earnings"] = _earnings(body)
            store.save_report(conn, date, body["built_at"], body)
        write_status(state="done", step=f"Report for {date} ready", done=len(symbols), total=len(symbols), date=date)
        log(f"report {date}: {body['with_skew']} of {body['universe']} names with skew, {len(failed)} failed, {body['seconds']}s")
        return body
    except Exception as error:
        write_status(state="failed", step=str(error)[:300])
        raise
    finally:
        LOCK.unlink(missing_ok=True)
