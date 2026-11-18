"""SQLite on this Mac: one row per stock per day, the finished report per day, and the sector cache."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "skew.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
  date TEXT, symbol TEXT, sector TEXT, close REAL, ret_1d REAL, ret_1w REAL, ret_1m REAL,
  dvol_21 REAL, dvol_5 REAL, dvol_today REAL, skew REAL, put25 REAL, call25 REAL, atm REAL,
  call_volume REAL, put_volume REAL, source TEXT, price_z REAL, bet_z REAL, bucket TEXT, asym INTEGER,
  PRIMARY KEY (date, symbol));
CREATE TABLE IF NOT EXISTS reports (date TEXT PRIMARY KEY, built_at TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS paper (symbol TEXT PRIMARY KEY, date TEXT, entry REAL, spy_entry REAL);
CREATE TABLE IF NOT EXISTS swing_paper (symbol TEXT, date TEXT, entry REAL, stop REAL, target REAL, until TEXT, status TEXT,
  exit_date TEXT, exit_price REAL, net_ret REAL, spy_entry REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS fundamentals (symbol TEXT PRIMARY KEY, cik TEXT, as_of TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS sentinel (date TEXT, symbol TEXT, json TEXT, PRIMARY KEY (date, symbol));
CREATE TABLE IF NOT EXISTS breaking (symbol TEXT PRIMARY KEY, version TEXT, json TEXT);
"""
STOCK_COLUMNS = ["date", "symbol", "sector", "close", "ret_1d", "ret_1w", "ret_1m", "dvol_21", "dvol_5", "dvol_today",
                 "skew", "put25", "call25", "atm", "call_volume", "put_volume", "source", "price_z", "bet_z", "bucket",
                 "asym"]


@contextmanager
def connect(path: Path = DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn) -> None:
    """Older databases: the Steady paper table gets a VOO column (filled lazily; spy_entry stays as it was)."""
    have = {row[1] for row in conn.execute("PRAGMA table_info(paper)")}
    for column in ("voo_entry", "exit_close", "voo_exit"):  # exit_* freeze a settled pick at its day-28 close
        if column not in have:
            conn.execute(f"ALTER TABLE paper ADD COLUMN {column} REAL")


def save_stocks(conn, date: str, frame: pd.DataFrame) -> None:
    rows = frame.assign(date=date).reindex(columns=STOCK_COLUMNS)
    conn.execute("DELETE FROM stocks WHERE date = ?", (date,))
    conn.executemany(f"INSERT INTO stocks VALUES ({','.join('?' * len(STOCK_COLUMNS))})",
                     [tuple(None if pd.isna(v) else v for v in row) for row in rows.itertuples(index=False)])


def previous_skew(conn, date: str, sessions: int = 5) -> dict[str, float]:
    """Each stock's average skew over its last few stored days before `date`."""
    dates = [d for (d,) in conn.execute(
        "SELECT DISTINCT date FROM stocks WHERE date < ? ORDER BY date DESC LIMIT ?", (date, sessions))]
    if not dates:
        return {}
    marks = ",".join("?" * len(dates))
    return dict(conn.execute(
        f"SELECT symbol, AVG(skew) FROM stocks WHERE date IN ({marks}) AND skew IS NOT NULL GROUP BY symbol", dates))


def history(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT date, symbol, close, bucket, asym FROM stocks ORDER BY date", conn)


def save_report(conn, date: str, built_at: str, body: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO reports VALUES (?, ?, ?)", (date, built_at, json.dumps(body)))


def report(conn, date: str | None = None) -> dict | None:
    query = "SELECT body FROM reports " + ("WHERE date = ?" if date else "ORDER BY date DESC LIMIT 1")
    row = conn.execute(query, (date,) if date else ()).fetchone()
    return json.loads(row[0]) if row else None


def report_dates(conn) -> list[str]:
    return [d for (d,) in conn.execute("SELECT date FROM reports ORDER BY date DESC")]


def recent_reports(conn, before: str, count: int = 5) -> list[dict]:
    """The last few finished reports before `before`, oldest first."""
    rows = conn.execute("SELECT body FROM reports WHERE date < ? ORDER BY date DESC LIMIT ?", (before, count)).fetchall()
    return [json.loads(b) for (b,) in reversed(rows)]


def add_paper(conn, date: str, picks: list[dict], spy_price: float | None) -> None:
    """Each pick joins the paper record once, at the price on the day it was first picked."""
    conn.executemany("INSERT OR IGNORE INTO paper (symbol, date, entry, spy_entry) VALUES (?, ?, ?, ?)",
                     [(p["symbol"], date, p["price"], spy_price) for p in picks])


def drop_unselected(conn, date: str, pick_symbols: list[str], swing_symbols: list[str]) -> None:
    """Re-picking a report's own day: paper rows first added on `date` that the new rules no longer pick are removed
    (open swing trades only). Rows from earlier days are never touched."""
    picks_in = ",".join("?" * len(pick_symbols))
    swing_in = ",".join("?" * len(swing_symbols))
    conn.execute(f"DELETE FROM paper WHERE date = ? AND symbol NOT IN ({picks_in})", (date, *pick_symbols))
    conn.execute(f"DELETE FROM swing_paper WHERE date = ? AND status = 'open' AND symbol NOT IN ({swing_in})", (date, *swing_symbols))


def paper(conn) -> list[tuple]:
    return conn.execute("SELECT symbol, date, entry, spy_entry FROM paper ORDER BY date, symbol").fetchall()


PAPER_COLUMNS = ["symbol", "date", "entry", "spy_entry", "voo_entry", "exit_close", "voo_exit"]


def paper_rows(conn) -> list[dict]:
    rows = conn.execute(f"SELECT {','.join(PAPER_COLUMNS)} FROM paper ORDER BY date, symbol").fetchall()
    return [dict(zip(PAPER_COLUMNS, r)) for r in rows]


def set_paper_voo(conn, symbol: str, voo_price: float) -> None:
    conn.execute("UPDATE paper SET voo_entry = ? WHERE symbol = ? AND voo_entry IS NULL", (voo_price, symbol))


def freeze_paper(conn, symbol: str, exit_close: float | None, voo_exit: float | None) -> None:
    """Keeps the day-28 closes of a settled pick; a value already frozen is never overwritten."""
    conn.execute("UPDATE paper SET exit_close = COALESCE(exit_close, ?), voo_exit = COALESCE(voo_exit, ?) WHERE symbol = ?",
                 (exit_close, voo_exit, symbol))


def set_swing_voo(conn, symbol: str, date: str, voo_price: float) -> None:
    conn.execute("UPDATE swing_paper SET spy_entry = ? WHERE symbol = ? AND date = ? AND spy_entry IS NULL", (voo_price, symbol, date))


def stocks_on(conn, date: str) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM stocks WHERE date = ?", conn, params=(date,))


SWING_COLUMNS = ["symbol", "date", "entry", "stop", "target", "until", "status", "exit_date", "exit_price", "net_ret", "spy_entry"]


def add_swing(conn, date: str, trades: list[dict], voo_price: float | None) -> None:
    """A swing trade joins the paper table once per symbol while it is open. spy_entry holds VOO's close (the comparison fund)."""
    opened = {s for (s,) in conn.execute("SELECT symbol FROM swing_paper WHERE status = 'open'")}
    conn.executemany("INSERT OR IGNORE INTO swing_paper VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, NULL, NULL, ?)",
                     [(t["symbol"], date, t["entry"], t["stop"], t["target"], t["until"], voo_price)
                      for t in trades if t["symbol"] not in opened])


def swing_rows(conn) -> list[dict]:
    rows = conn.execute(f"SELECT {','.join(SWING_COLUMNS)} FROM swing_paper ORDER BY date DESC, symbol").fetchall()
    return [dict(zip(SWING_COLUMNS, r)) for r in rows]


def close_swing(conn, symbol: str, date: str, result: dict) -> None:
    conn.execute("UPDATE swing_paper SET status = ?, exit_date = ?, exit_price = ?, net_ret = ? WHERE symbol = ? AND date = ?",
                 (result["status"], result["exit_date"], result["exit_price"], result["net_ret"], symbol, date))


def save_fundamentals(conn, rows: list[tuple]) -> None:
    """rows: (symbol, cik, as_of, json). Replaces each symbol's row; a symbol missing from `rows` keeps its old one."""
    conn.executemany("INSERT OR REPLACE INTO fundamentals VALUES (?, ?, ?, ?)", rows)


def fundamentals(conn) -> dict[str, dict]:
    """symbol -> metrics (with 'cik' and 'as_of' added)."""
    out = {}
    for symbol, cik, as_of, blob in conn.execute("SELECT symbol, cik, as_of, json FROM fundamentals"):
        out[symbol] = {**json.loads(blob), "cik": cik, "as_of": as_of}
    return out


SENTINEL_RUNS_KEPT = 14  # full score rows are kept for this many report dates; older ones are dropped to keep the file small


def save_sentinel(conn, date: str, rows: list[dict]) -> None:
    """One row per company per report date. Saving a date again replaces it."""
    conn.execute("DELETE FROM sentinel WHERE date = ?", (date,))
    conn.executemany("INSERT INTO sentinel VALUES (?, ?, ?)",
                     [(date, r["symbol"], json.dumps(r, separators=(",", ":"))) for r in rows])
    conn.execute("DELETE FROM sentinel WHERE date NOT IN (SELECT DISTINCT date FROM sentinel ORDER BY date DESC LIMIT ?)",
                 (SENTINEL_RUNS_KEPT,))


def sentinel(conn, date: str | None = None) -> tuple[str | None, list[dict]]:
    """(date, rows) for the newest stored run on or before `date` (newest overall when None); rows are ranked best first."""
    query = "SELECT MAX(date) FROM sentinel" + (" WHERE date <= ?" if date else "")
    found = conn.execute(query, (date,) if date else ()).fetchone()[0]
    if not found:
        return None, []
    rows = [json.loads(b) for (b,) in conn.execute("SELECT json FROM sentinel WHERE date = ?", (found,))]
    return found, sorted(rows, key=lambda r: r["rank"])


def sentinel_scores(conn, before: str) -> dict[str, int]:
    """symbol -> score from the newest stored run strictly before `before` (for 'change since last run')."""
    found = conn.execute("SELECT MAX(date) FROM sentinel WHERE date < ?", (before,)).fetchone()[0]
    if not found:
        return {}
    return {s: json.loads(b)["score"] for s, b in conn.execute("SELECT symbol, json FROM sentinel WHERE date = ?", (found,))}


def save_breaking(conn, symbol: str, version: str, answer: dict) -> None:
    """Claude's counter-argument for one company, keyed to the data version (filing period | raw score) it was written for."""
    conn.execute("INSERT OR REPLACE INTO breaking VALUES (?, ?, ?)", (symbol, version, json.dumps(answer, separators=(",", ":"))))


def breaking(conn) -> dict[str, dict]:
    """symbol -> {version, deductions, what_breaks, total}."""
    return {s: {**json.loads(b), "version": v} for s, v, b in conn.execute("SELECT symbol, version, json FROM breaking")}
