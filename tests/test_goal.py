import numpy as np
import pytest

from market_skew import goal

RETURNS = list(np.random.default_rng(1).normal(0.008, 0.04, 120))


def run(**kw):
    args = dict(returns=RETURNS, years=10, start=10000.0, monthly=2000.0, fee=0.0, inflation=0.045, target=1e6, paths=800, seed=7)
    return goal.simulate(**{**args, **kw})


def test_fv_formula_matches_hand_value():
    assert goal.fv_steady(0, 100, 0.12, 1) == pytest.approx(100 * (1.01 ** 12 - 1) / 0.01)
    assert goal.fv_steady(1000, 0, 0.12, 2) == pytest.approx(1000 * 1.01 ** 24)
    assert goal.fv_steady(0, 100, 0.0, 1) == 1200


def test_inflation_makes_today_money_smaller():
    assert goal.deflate(1000.0, 0.045, 12) == pytest.approx(1000 / 1.045)
    assert run(inflation=0.0)["final"]["p50"] > run()["final"]["p50"]


def test_same_seed_same_answer_and_bands_are_ordered():
    a, b = run(), run()
    assert a == b
    f = a["final"]
    assert f["p10"] <= f["p50"] <= f["p90"] and len(a["fan"]["p50"]) == 11 and a["fan"]["p50"][0] == pytest.approx(10000.0)


def test_probability_never_rises_with_a_bigger_target():
    probs = [run(target=t)["prob"] for t in (1e5, 3e5, 6e5, 1e6, 5e6)]
    assert probs == sorted(probs, reverse=True) and probs[0] > probs[-1]


def test_zero_return_history_is_just_contributions_less_fees_and_inflation():
    out = goal.simulate([0.0] * 24, years=1, start=0.0, monthly=100.0, fee=0.02, inflation=0.0, target=1200, paths=50, seed=1)
    assert out["final"]["p50"] == pytest.approx(1176.0) and out["prob"] == 0.0


def test_too_little_history_is_refused():
    assert goal.simulate([0.01] * 11, years=5, start=0, monthly=1, fee=0, inflation=0, target=1, seed=1) is None


def test_clean_accepts_blanks_and_rejects_nonsense():
    assert goal.clean({"target": "2000000", "years": "20", "start": "", "monthly": "8000", "inflation": "5", "actual": True}) == \
        {"target": 2e6, "years": 20, "monthly": 8000.0, "inflation": 0.05, "actual": True}
    assert goal.clean({"target": "1", "years": 41}) is None and goal.clean({"target": "-5", "years": 5}) is None
    assert goal.clean({"target": "abc", "years": 5}) is None and goal.clean({"target": 5, "years": 5, "inflation": 99}) is None


def test_cautious_takes_five_points_a_year_off_every_month_and_keeps_the_shape():
    assert goal.CAUTIOUS_PP == 5.0 and goal.CAUTIOUS_MONTHLY == pytest.approx(0.05 / 12)
    plain, cautious = run(target=2e5), run(target=2e5, haircut=goal.CAUTIOUS_MONTHLY)
    assert cautious["final"]["p50"] < plain["final"]["p50"] and cautious["prob"] < plain["prob"]
    # flat history: the haircut is exactly 0.4167% a month, compounded
    out = goal.simulate([0.01] * 24, years=1, start=1000.0, monthly=0.0, fee=0.0, inflation=0.0, target=1, paths=20, seed=1,
                        haircut=goal.CAUTIOUS_MONTHLY)
    assert out["final"]["p50"] == pytest.approx(1000 * (1 + 0.01 - 0.05 / 12) ** 12)


def test_haircut_uses_the_same_blocks_so_the_spread_is_unchanged():
    plain, cautious = run(), run(haircut=goal.CAUTIOUS_MONTHLY)
    import math
    spread = lambda o: math.log(o["final"]["p90"] / o["final"]["p10"])
    assert spread(cautious) == pytest.approx(spread(plain), rel=0.15)


def test_the_result_carries_a_monthly_median_path_for_milestones():
    out = run(years=2)
    assert len(out["median_path"]) == 25 and out["median_path"][0] == pytest.approx(10000.0)
    assert out["median_path"][12] == pytest.approx(out["fan"]["p50"][1])
