import datetime as dt

import pytest

from market_skew import milestones

TODAY = dt.date(2026, 11, 18)


def test_defaults_are_the_four_from_the_spec():
    assert [m["label"] for m in milestones.DEFAULTS] == ["Emergency fund", "R100,000 invested", "R500,000 invested", "R1,000,000 invested"]
    assert milestones.DEFAULTS[0] == {"label": "Emergency fund", "kind": "emergency", "value": 3.0}
    assert [m["value"] for m in milestones.DEFAULTS[1:]] == [1e5, 5e5, 1e6]


def test_saved_falls_back_to_defaults_and_cleans_what_it_keeps():
    assert milestones.saved({}) == milestones.DEFAULTS
    assert milestones.saved({"milestones": "nope"}) == milestones.DEFAULTS
    assert milestones.saved({"milestones": [{"label": "Car", "kind": "invested", "value": "250000"}]}) == \
        [{"label": "Car", "kind": "invested", "value": 250000.0}]


@pytest.mark.parametrize("bad", [
    "x", [{"label": "", "kind": "invested", "value": 5}], [{"label": "a", "kind": "other", "value": 5}],
    [{"label": "a", "kind": "invested", "value": -1}], [{"label": "a", "kind": "invested", "value": "abc"}],
    [{"label": "a", "kind": "invested", "value": True}], [{"label": "a" * 41, "kind": "invested", "value": 5}],
    [{"label": "a", "kind": "emergency", "value": 99}], [{"label": "a", "kind": "invested", "value": 5}] * 11, ["x"]])
def test_clean_rejects_nonsense(bad):
    assert milestones.clean(bad) is None


def test_an_empty_list_is_allowed_so_every_row_can_be_removed():
    assert milestones.clean([]) == []


def test_month_label_counts_from_today():
    assert milestones.month_label(TODAY, 0) == "Nov 2026" and milestones.month_label(TODAY, 4) == "Mar 2027"
    assert milestones.month_label(TODAY, 28) == "Mar 2029"


def test_invested_milestone_percent_and_eta_band_from_both_paths():
    cautious = [1000.0 * (1.02 ** m) for m in range(61)]
    past = [1000.0 * (1.04 ** m) for m in range(61)]
    row = milestones.rows([{"label": "R2k", "kind": "invested", "value": 2000.0}], invested=500.0, expenses=None, emergency=None,
                          cautious=cautious, past=past, today=TODAY)[0]
    assert row["pct"] == pytest.approx(0.25) and row["status"] == "open"
    assert row["eta"]["past"] == "May 2028"  # 1.04^18 > 2 first at month 18
    assert row["eta"]["cautious"] == "Nov 2029"  # 1.02^36 > 2 first at month 36
    assert row["band"] == "about Nov 2029 (cautious) to May 2028 (past decade)"


def test_reached_beyond_horizon_and_same_month():
    flat = [100.0] * 25
    row = milestones.rows([{"label": "a", "kind": "invested", "value": 50.0}], 100.0, None, None, flat, flat, TODAY)[0]
    assert row["status"] == "done" and row["pct"] == 1.0 and "reached" in row["band"].lower()
    row = milestones.rows([{"label": "a", "kind": "invested", "value": 1e6}], 100.0, None, None, flat, flat, TODAY)[0]
    assert row["eta"] == {"cautious": None, "past": None} and "not within 2 years" in row["band"]
    both = milestones.rows([{"label": "a", "kind": "invested", "value": 150}], 100.0, None, None, flat, [100.0 + 10 * m for m in range(25)], TODAY)[0]
    assert "not within 2 years (cautious)" in both["band"] and "(past decade)" in both["band"]


def test_emergency_fund_is_months_of_expenses_and_has_no_projection():
    row = milestones.rows([{"label": "Emergency fund", "kind": "emergency", "value": 3.0}], 0.0, expenses=10000.0, emergency=15000.0,
                          cautious=[0.0], past=[0.0], today=TODAY)[0]
    assert row["target"] == 30000.0 and row["pct"] == pytest.approx(0.5) and row["eta"] is None and "cash" in row["band"].lower()
    unknown = milestones.rows([{"label": "Emergency fund", "kind": "emergency", "value": 3.0}], 0.0, None, None, [0.0], [0.0], TODAY)[0]
    assert unknown["pct"] is None and "expenses" in unknown["band"]


def test_no_paths_means_no_eta_but_percent_still_shows():
    row = milestones.rows([{"label": "a", "kind": "invested", "value": 1000.0}], 250.0, None, None, None, None, TODAY)[0]
    assert row["pct"] == 0.25 and row["eta"] is None
