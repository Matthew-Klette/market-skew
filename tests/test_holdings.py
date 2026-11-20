import json

import pandas as pd
import pytest

from market_skew import holdings


def test_load_keeps_valid_entries_and_defaults(tmp_path):
    f = tmp_path / "h.json"
    f.write_text(json.dumps([{"symbol": "qqq", "account": "usd"}, {"symbol": "STXNDQ", "account": "tfsa", "new_money": False},
                             {"symbol": "bad symbol!"}, "junk"]))
    got = holdings.load(f)
    assert got == [{"symbol": "QQQ", "account": "usd", "new_money": True},
                   {"symbol": "STXNDQ", "account": "tfsa", "new_money": False}]


def test_load_missing_or_broken_file_is_empty(tmp_path):
    assert holdings.load(tmp_path / "none.json") == []
    (tmp_path / "x.json").write_text("{")
    assert holdings.load(tmp_path / "x.json") == []


def test_shipped_example_holdings_file_is_empty_and_loads():
    example = holdings.ROOT / "config" / "holdings.example.json"
    assert holdings.load(example) == []


def test_exclude_validates_and_dedupes(tmp_path):
    f = tmp_path / "e.txt"
    assert holdings.exclude("abc", f) == {"ABC"}
    assert holdings.exclude("ABC", f) == {"ABC"}
    assert f.read_text().count("ABC") == 1
    with pytest.raises(ValueError):
        holdings.exclude("a;rm", f)
    assert holdings.excluded(f) == {"ABC"}


def test_include_undoes_an_exclude_and_keeps_the_rest(tmp_path):
    f = tmp_path / "e.txt"
    f.write_text("# can't buy these\nABC\nXYZ\n")
    assert holdings.include("abc", f) == {"XYZ"}
    assert f.read_text() == "# can't buy these\nXYZ\n"
    assert holdings.include("ABC", f) == {"XYZ"} and holdings.include("NOPE", tmp_path / "missing.txt") == set()
    with pytest.raises(ValueError):
        holdings.include("a;rm", f)


def test_rows_cover_us_light_missing_etf_and_jse_price():
    lights = [{"symbol": "SCHD", "name": "Schwab", "light": "add", "label": "Good time to add", "why": "w", "price": 28.0, "ret_1m": -0.02},
              {"symbol": "QQQ", "name": "QQQ", "light": "none", "label": "No reading", "why": "x", "price": None, "ret_1m": None}]
    hs = [{"symbol": s, "account": a, "new_money": True} for s, a in [("SCHD", "usd"), ("QQQ", "usd"), ("STXNDQ", "tfsa")]]
    out = {r["symbol"]: r for r in holdings.rows(hs, lights, {"STXNDQ": {"price": 61.5}})}
    assert out["SCHD"]["light"] == "add" and out["SCHD"]["currency"] == "USD"
    assert out["QQQ"]["why"] == holdings.NO_READING and out["QQQ"]["price"] is None
    assert out["STXNDQ"]["why"] == "JSE fund: price only" and out["STXNDQ"]["price"] == 61.5 and out["STXNDQ"]["currency"] == "ZAR"


def test_server_filter_drops_excluded_picks_live():
    from market_skew.picks import without
    picks = [{"symbol": "AAA"}, {"symbol": "BBB"}]
    assert without(picks, {"AAA"}) == [{"symbol": "BBB"}]
    assert without(picks, set()) == picks and len(picks) == 2


def test_views_holdings_table_shows_prices_and_button_escapes():
    from market_skew.ui import views
    r = {"swing": [{"symbol": "A<B", "name": "n", "sector": "s", "entry": 10.0, "stop": 9.0, "target": 12.0, "until": "2026-12-16",
                    "stop_pct": -0.1, "target_pct": 0.2, "atm": 0.3, "ret_1m": 0.0, "reasons": ["r"]}],
         "holdings": holdings.rows([{"symbol": "STXNDQ", "account": "tfsa", "new_money": False}], [], {"STXNDQ": {"price": 61.5}})}
    html = views.picks_page(r, {"tfsa": 1.0, "usd": 1.0}, None)
    assert "R61.50" in html and "JSE fund: price only" in html
    assert 'data-exclude="A&lt;B"' in html and "Not on EasyEquities" in html


def test_last_buy_is_read_when_valid_and_ignored_otherwise(tmp_path):
    path = tmp_path / "h.json"
    path.write_text('[{"symbol": "AAA", "last_buy": 12.5}, {"symbol": "BBB", "last_buy": "x"}, {"symbol": "CCC", "last_buy": -1}, {"symbol": "DDD"}]')
    got = {h["symbol"]: h for h in holdings.load(path)}
    assert got["AAA"]["last_buy"] == 12.5
    assert all("last_buy" not in got[s] for s in ("BBB", "CCC", "DDD"))


def test_load_keeps_units_prices_and_ignores_bad_ones(tmp_path):
    f = tmp_path / "h.json"
    f.write_text(json.dumps([{"symbol": "VOO", "units": 2.5, "avg_price": 410.5, "last_buy": 480},
                             {"symbol": "QQQ", "units": -1, "avg_price": "x"}]))
    got = holdings.load(f)
    assert got[0]["units"] == 2.5 and got[0]["avg_price"] == 410.5 and got[0]["last_buy"] == 480.0
    assert "units" not in got[1] and "avg_price" not in got[1]
    assert holdings.buy_price(got[0]) == 480.0
    assert holdings.buy_price({"avg_price": 3.0}) == 3.0 and holdings.buy_price({}) is None


GOOD = {"symbol": "voo", "account": "usd", "units": "1.5", "avg_price": "400", "new_money": True}


def test_validate_normalises_a_good_row():
    out = holdings.validate([GOOD, {"symbol": "STXNDQ", "account": "tfsa", "units": 10, "new_money": False}])
    assert out[0] == {"symbol": "VOO", "account": "usd", "new_money": True, "units": 1.5, "avg_price": 400.0}
    assert out[1] == {"symbol": "STXNDQ", "account": "tfsa", "new_money": False, "units": 10.0}


@pytest.mark.parametrize("bad", [
    {**GOOD, "symbol": "bad symbol"}, {**GOOD, "account": "cash"}, {**GOOD, "units": -1}, {**GOOD, "units": 1e9},
    {**GOOD, "units": "abc"}, {**GOOD, "avg_price": -1}, {**GOOD, "avg_price": 1e7}, {**GOOD, "last_buy": 1e7}, {**GOOD, "units": float("nan")},
    "junk"])
def test_validate_rejects_bad_rows(bad):
    with pytest.raises(ValueError):
        holdings.validate([bad])


def test_validate_caps_rows_and_blank_units_are_allowed():
    with pytest.raises(ValueError):
        holdings.validate([{"symbol": "VOO", "account": "usd"}] * 51)
    assert "units" not in holdings.validate([{"symbol": "VOO", "account": "usd", "units": ""}])[0]
    with pytest.raises(ValueError):
        holdings.validate("nope")


def test_save_is_atomic_and_round_trips(tmp_path):
    f = tmp_path / "h.json"
    saved = holdings.save([GOOD], f)
    assert holdings.load(f) == saved and not list(tmp_path.glob("*.tmp"))
    with pytest.raises(ValueError):
        holdings.save([{"symbol": "!!"}], f)
    assert holdings.load(f) == saved
