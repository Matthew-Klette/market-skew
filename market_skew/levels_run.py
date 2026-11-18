"""Glue: candidate buy levels and the one-year chart series for the on-screen names, from closes already downloaded
(the 2-year frame the predictions use). No network here."""
import pandas as pd

from . import levels

YEAR = 252


def build(symbols: list[str], closes: pd.DataFrame | None) -> dict[str, dict]:
    """{symbol: {levels: [...], closes: [last ~year, 2 dp], last, start, end}}. Names with under 120 closes are left out."""
    out = {}
    if closes is None:
        return out
    for symbol in dict.fromkeys(symbols):
        if symbol not in closes:
            continue
        series = closes[symbol].dropna().tail(YEAR)
        if len(series) < levels.MIN_CLOSES:
            continue
        out[symbol] = {"levels": levels.find(series), "closes": [round(float(v), 2) for v in series],
                       "last": round(float(series.iloc[-1]), 2),
                       "start": series.index[0].date().isoformat(), "end": series.index[-1].date().isoformat()}
    return out
