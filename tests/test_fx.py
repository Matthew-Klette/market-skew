import json

import pytest

from market_skew import fx, jse


def test_fetches_once_per_day_then_uses_cache(tmp_path):
    calls = []
    fetch = lambda: calls.append(1) or 17.5
    assert fx.refresh(tmp_path, "2026-11-18", fetch) == 17.5
    assert fx.refresh(tmp_path, "2026-11-18", fetch) == 17.5
    assert len(calls) == 1
    assert json.loads((tmp_path / "fx.json").read_text()) == {"date": "2026-11-18", "rate": 17.5}
    assert fx.cached(tmp_path) == {"rate": 17.5, "date": "2026-11-18"}


def test_new_day_refetches(tmp_path):
    fx.refresh(tmp_path, "2026-11-17", lambda: 17.0)
    assert fx.refresh(tmp_path, "2026-11-18", lambda: 17.5) == 17.5


def test_failed_fetch_falls_back_to_old_rate_or_none(tmp_path):
    def boom():
        raise OSError("offline")
    assert fx.refresh(tmp_path, "2026-11-18", boom, now=0.0) is None
    fx.refresh(tmp_path, "2026-11-17", lambda: 17.0, now=5000.0)
    assert fx.refresh(tmp_path, "2026-11-18", boom, now=5001.0) == 17.0


def test_parse_frankfurter_payload():
    assert fx.parse({"base": "USD", "rates": {"ZAR": 17.123}}) == 17.123
    with pytest.raises(ValueError):
        fx.parse({"rates": {}})


def test_jse_prices_divide_cents_and_cache(tmp_path):
    calls = []
    def fetch(symbol):
        calls.append(symbol)
        return {"SYG500.JO": 8123.0, "STXNDQ.JO": 5000.0}[symbol]
    out = jse.refresh(tmp_path, "2026-11-18", fetch)
    assert out["SYG500"]["price"] == pytest.approx(81.23)
    assert out["STXNDQ"]["price"] == pytest.approx(50.0)
    jse.refresh(tmp_path, "2026-11-18", fetch)
    assert len(calls) == 2


def test_jse_failure_skips_that_symbol(tmp_path):
    def fetch(symbol):
        if symbol == "STXNDQ.JO":
            raise OSError
        return 8000.0
    out = jse.refresh(tmp_path, "2026-11-18", fetch)
    assert "STXNDQ" not in out and out["SYG500"]["price"] == 80.0


def test_cached_reads_only_and_is_none_when_empty(tmp_path):
    assert fx.cached(tmp_path) is None and jse.cached(tmp_path) == {}


def test_failed_fx_fetch_is_not_retried_for_fifteen_minutes(tmp_path):
    calls = []
    def boom():
        calls.append(1)
        raise OSError("offline")
    fx.refresh(tmp_path, "2026-11-18", boom, now=1000.0)
    fx.refresh(tmp_path, "2026-11-18", boom, now=1000.0 + 600)
    assert len(calls) == 1
    fx.refresh(tmp_path, "2026-11-18", boom, now=1000.0 + 901)
    assert len(calls) == 2


def test_jse_partial_failure_retries_only_the_missing_symbol_after_the_wait(tmp_path):
    calls = []
    def fetch(symbol):
        calls.append(symbol)
        if symbol == "STXNDQ.JO" and len(calls) < 3:
            raise OSError
        return 8000.0
    first = jse.refresh(tmp_path, "2026-11-18", fetch, now=0.0)
    assert list(first) == ["SYG500"]
    jse.refresh(tmp_path, "2026-11-18", fetch, now=60.0)       # still backing off: no calls
    assert calls == ["SYG500.JO", "STXNDQ.JO"]
    both = jse.refresh(tmp_path, "2026-11-18", fetch, now=1000.0)
    assert set(both) == {"SYG500", "STXNDQ"} and calls[2:] == ["STXNDQ.JO"]


def test_jse_keeps_last_good_price_with_its_date_when_a_new_day_fails(tmp_path):
    jse.refresh(tmp_path, "2026-11-17", lambda s: 8000.0, now=0.0)
    def boom(symbol):
        raise OSError
    out = jse.refresh(tmp_path, "2026-11-18", boom, now=0.0)
    assert out["SYG500"] == {"price": 80.0, "date": "2026-11-17"}
    assert jse.cached(tmp_path)["SYG500"]["date"] == "2026-11-17"
