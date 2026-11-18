"""Reading a close from a daily price series. Pure."""
import datetime as dt

import pandas as pd


def price_at(series: pd.Series | None, day: str) -> float | None:
    """The last close on or before `day`, or None when the series is empty or starts later."""
    if series is None:
        return None
    seen = series.dropna()
    seen = seen[seen.index.date <= dt.date.fromisoformat(day)]
    return float(seen.iloc[-1]) if len(seen) else None
