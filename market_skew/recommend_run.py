"""Glue for the Recommended lens: builds both paper records for the latest report and asks recommend() which way to lean.
VOO's closes are kept in data/voo.json. The page only reads that file; `refresh_voo` (scan and CLI) is the one place that fetches."""
import time
from pathlib import Path

import pandas as pd

from . import cache, market, recommend, steady_record, store
from .closes import price_at

VOO_FILE = cache.DATA / "voo.json"


def voo_closes(path: Path | None = None) -> pd.Series | None:
    """The saved VOO closes, however old. Never touches the network."""
    saved = cache.read(path or VOO_FILE).get("closes")
    if not saved:
        return None
    series = pd.Series({pd.Timestamp(day): float(v) for day, v in saved.items()}).sort_index()
    return series if len(series) else None


def refresh_voo(day: str, path: Path | None = None, fetch=market.prices, now: float | None = None) -> pd.Series | None:
    """Fetches a year of VOO closes unless the saved ones already reach `day` or a recent try failed."""
    path = path or VOO_FILE
    saved = cache.read(path)
    have = voo_closes(path)
    if have is not None and have.index[-1].date().isoformat() >= day:
        return have
    if cache.backing_off(saved.get("failed_at"), now):
        return have
    try:
        got, _ = fetch(["VOO"], period="1y")
        series = got["VOO"].dropna()
        cache.write(path, {"closes": {d.date().isoformat(): float(v) for d, v in series.items()}})
        return series
    except Exception as error:
        print(f"warning: no VOO closes ({error})"[:200], flush=True)
        cache.write(path, {**saved, "failed_at": now if now is not None else time.time()})
        return have


def fill_voo_entries(conn, rows: list[dict], voo: pd.Series | None) -> list[dict]:
    """Saves VOO's close on each pick's day where the column is still empty (rows from before it existed)."""
    out = []
    for r in rows:
        if not r.get("voo_entry"):
            price = price_at(voo, r["date"])
            if price:
                store.set_paper_voo(conn, r["symbol"], price)
                r = {**r, "voo_entry": price}
        out.append(r)
    return out


def mood(report: dict) -> dict:
    idx = report.get("indexes") or {}
    tape = (report.get("read") or [""])[0]
    return {"spy_1m": (idx.get("SPY") or {}).get("ret_1m"), "vix_1d": (idx.get("VIX") or {}).get("ret_1d"),
            "risk_off": "risk-off" in tape}


def his_record(swing_record: list[dict]) -> list[dict]:
    return [{"date": x["date"], "ret": x.get("ret"), "voo_ret": x.get("voo_ret"), "settled": x.get("status") not in (None, "open")}
            for x in swing_record]


def enrich(conn, report: dict, voo: pd.Series | None = None) -> dict:
    """The report with a fresh Steady paper record (after fees, vs VOO) and the recommendation. Reads saved data only."""
    day = report["date"]
    rows = store.paper_rows(conn)
    voo = voo if voo is not None else voo_closes()
    rows = fill_voo_entries(conn, rows, voo)
    now = {**(report.get("paper_closes") or {}), **dict(conn.execute("SELECT symbol, close FROM stocks WHERE date = ?", (day,)).fetchall())}
    paper = steady_record.record(rows, now, voo, day)
    rec = recommend.recommend(paper, his_record(report.get("swing_record") or []), mood(report), day)
    return {**report, "paper": paper, "recommendation": rec}
