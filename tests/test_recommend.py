from market_skew import recommend
from market_skew.recommend import recommend as rec

TODAY = "2026-11-18"


def entries(count, start="2026-08-20", ret=0.02, voo=0.01, settled=True):
    import datetime as dt
    first = dt.date.fromisoformat(start)
    return [{"date": (first + dt.timedelta(days=i * 7)).isoformat(), "ret": ret, "voo_ret": voo, "settled": settled}
            for i in range(count)]


CALM = {"spy_1m": 0.01, "vix_1d": -0.02, "risk_off": False}


def test_under_three_months_says_not_enough_evidence_and_picks_mine():
    out = rec(entries(12, start="2026-10-01"), entries(12, start="2026-10-01"), CALM, TODAY)
    assert out["lens"] == "mine"
    assert out["reason"].startswith("Not enough evidence yet: 48 days of record; needs about 3 months.")


def test_too_few_settled_entries_is_not_enough_evidence():
    out = rec(entries(12), entries(4), CALM, TODAY)
    assert out["lens"] == "mine" and out["reason"].startswith("Not enough evidence yet")
    assert out["evidence"]["his_settled"] == 4


def test_unsettled_entries_do_not_count():
    out = rec(entries(12), entries(12, settled=False), CALM, TODAY)
    assert out["reason"].startswith("Not enough evidence yet")


def test_empty_records_are_not_enough_evidence():
    out = rec([], [], CALM, TODAY)
    assert out["lens"] == "mine" and "0 days of record" in out["reason"]


def test_nervous_market_by_numbers_forces_mine():
    mood = {"spy_1m": -0.06, "vix_1d": 0.06, "risk_off": False}
    out = rec(entries(12, ret=0.01), entries(12, ret=0.10), mood, TODAY)
    assert out["lens"] == "mine" and out["reason"].startswith("Nervous market: swing trades are riskier now")


def test_nervous_market_by_tape_read_forces_mine():
    mood = {"spy_1m": 0.0, "vix_1d": 0.0, "risk_off": True}
    assert rec(entries(12), entries(12, ret=0.10), mood, TODAY)["lens"] == "mine"


def test_one_condition_alone_is_not_nervous():
    mood = {"spy_1m": -0.06, "vix_1d": 0.01, "risk_off": False}
    assert rec(entries(12, ret=0.0), entries(12, ret=0.10), mood, TODAY)["lens"] == "his"


def test_his_way_wins_when_clearly_ahead_after_fees():
    out = rec(entries(12, ret=0.02), entries(12, ret=0.06), CALM, TODAY)
    assert out["lens"] == "his"
    assert abs(out["evidence"]["his_avg"] - 0.05) < 1e-9
    assert "His way" in out["reason"] and "VOO" in out["reason"]


def test_his_way_ahead_by_under_one_point_stays_mine():
    out = rec(entries(12, ret=0.020), entries(12, ret=0.025), CALM, TODAY)
    assert out["lens"] == "mine" and "not worth the extra trading" in out["reason"]


def test_mine_ahead_stays_mine():
    out = rec(entries(12, ret=0.05), entries(12, ret=0.01), CALM, TODAY)
    assert out["lens"] == "mine" and "My way" in out["reason"]


def test_only_last_90_days_are_averaged():
    old_bad = entries(10, start="2026-05-01", ret=-0.30)
    mine = old_bad + entries(12, start="2026-09-01", ret=0.02)
    his = entries(12, start="2026-08-20", ret=0.02)
    out = rec(mine, his, CALM, TODAY)
    assert abs(out["evidence"]["mine_avg"] - 0.01) < 1e-9


def test_entries_without_a_voo_figure_are_ignored():
    mine = entries(12) + [{"date": "2026-09-01", "ret": 9.0, "voo_ret": None, "settled": True}]
    assert abs(rec(mine, entries(12), CALM, TODAY)["evidence"]["mine_avg"] - 0.01) < 1e-9


def test_is_nervous_helper():
    assert recommend.is_nervous({"spy_1m": -0.05, "vix_1d": 0.05, "risk_off": False})
    assert not recommend.is_nervous({"spy_1m": None, "vix_1d": None, "risk_off": False})


def test_five_settled_results_per_side_is_enough_but_four_is_not():
    assert rec(entries(5, ret=0.02), entries(5, ret=0.06), CALM, TODAY)["lens"] == "his"
    four = rec(entries(12), entries(4, ret=0.06), CALM, TODAY)
    assert four["lens"] == "mine" and "at least 5 on each side" in four["reason"]
