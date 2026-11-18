import datetime as dt
import threading
import time

import pandas as pd
import pytest

from market_skew import market

TODAY = dt.date(2026, 11, 18)


def test_price_download_passes_a_timeout(monkeypatch):
    seen = {}
    index = pd.date_range("2026-11-10", periods=2)
    frame = pd.concat({"Close": pd.DataFrame({"SPY": [1.0, 2.0]}, index=index), "Volume": pd.DataFrame({"SPY": [5, 6]}, index=index)}, axis=1)

    def download(batch, **kw):
        seen.update(kw)
        return frame
    monkeypatch.setattr(market.yf, "download", download)
    market.prices(["SPY"])
    assert seen["timeout"] == market.PRICE_TIMEOUT_SECONDS and 0 < seen["timeout"] <= 120


def test_within_returns_raises_and_times_out():
    assert market._within(1, lambda x: x + 1, 1) == 2
    with pytest.raises(ValueError):
        market._within(1, lambda: (_ for _ in ()).throw(ValueError("boom")))
    release = threading.Event()
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="timed out"):
        market._within(0.05, release.wait, 5)
    release.set()
    assert time.monotonic() - started < 2


def test_chain_fetch_is_wrapped_in_a_thread_timeout_of_30_seconds(monkeypatch):
    assert market.CHAIN_TIMEOUT_SECONDS == 30
    monkeypatch.setattr(market, "_pace", lambda: None)
    monkeypatch.setattr(market, "CHAIN_TIMEOUT_SECONDS", 0.05)
    release = threading.Event()

    class Hung:
        def __init__(self, symbol):
            pass

        @property
        def options(self):
            release.wait(5)
            return ()
    monkeypatch.setattr(market.yf, "Ticker", Hung)
    with pytest.raises(RuntimeError, match="timed out"):
        market.chain_skew("AAA", 100.0, TODAY, retries=1)
    release.set()


def test_a_normal_chain_still_reads(monkeypatch):
    monkeypatch.setattr(market, "_pace", lambda: None)
    seen = {}

    class Chain:
        calls = pd.DataFrame([{"strike": 100.0}])
        puts = pd.DataFrame([{"strike": 100.0}])

    class Fine:
        def __init__(self, symbol):
            pass
        options = ("2026-12-18",)

        def option_chain(self, expiry):
            seen["expiry"] = expiry
            return Chain
    monkeypatch.setattr(market.yf, "Ticker", Fine)
    monkeypatch.setattr(market, "read_chain", lambda calls, puts, spot, years: ("reading", len(calls), len(puts)))
    assert market.chain_skew("AAA", 100.0, TODAY, retries=1) == (("reading", 1, 1), "2026-12-18") and seen["expiry"] == "2026-12-18"
