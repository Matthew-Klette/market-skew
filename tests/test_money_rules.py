import datetime as dt

from market_skew import money_rules as m

INPUTS = {"take_home": 20000, "expenses": 9000, "rent": 6000, "emergency": 18000, "tfsa_year": 12000, "tfsa_life": 40000}


def row(rows, key):
    return next(r for r in rows if r["key"] == key)


def test_tax_year_runs_march_to_february():
    assert m.tax_year_label(dt.date(2026, 11, 18)) == "2026/27"
    assert m.tax_year_label(dt.date(2027, 2, 28)) == "2026/27"
    assert m.tax_year_label(dt.date(2027, 3, 1)) == "2027/28"


def test_invested_share_against_twenty_percent():
    rows = m.rules(INPUTS, invested=4000)
    r = row(rows, "invested")
    assert r["actual"] == 0.2 and r["status"] == "ok"
    assert row(m.rules(INPUTS, invested=1000), "invested")["status"] == "low"


def test_emergency_months_rent_and_living_costs():
    rows = m.rules(INPUTS, invested=0)
    assert row(rows, "emergency")["actual"] == 2.0 and row(rows, "emergency")["status"] == "low"
    assert row(rows, "rent")["actual"] == 0.3 and row(rows, "rent")["status"] == "ok"
    assert row(rows, "living")["actual"] == 0.45 and row(rows, "living")["status"] == "ok"
    assert row(m.rules({**INPUTS, "rent": 8000}, 0), "rent")["status"] == "high"


def test_fun_money_is_five_percent():
    assert row(m.rules(INPUTS, 0), "fun")["amount"] == 1000


def test_missing_take_home_gives_no_ratios_and_no_crash():
    rows = m.rules({}, invested=0)
    assert all(r["actual"] is None for r in rows if r["key"] != "emergency")


def test_tfsa_room_uses_the_smaller_of_year_and_lifetime():
    room = m.tfsa({"tfsa_year": 12000, "tfsa_life": 40000}, monthly=3000)
    assert room["year_left"] == 24000 and room["life_left"] == 460000 and room["room"] == 24000
    assert m.tfsa({"tfsa_year": 0, "tfsa_life": 480000}, 0)["room"] == 20000


def test_tfsa_monthly_line_exact_under_and_over():
    assert "exactly" in m.tfsa({}, monthly=3000)["monthly_line"]
    assert "R36,000" in m.tfsa({}, monthly=3000)["monthly_line"]
    assert "unused" in m.tfsa({}, monthly=2000)["monthly_line"]
    assert "over" in m.tfsa({}, monthly=4000)["monthly_line"]


def test_over_contribution_warns_with_sars_wording():
    assert m.tfsa({"tfsa_year": 36000}, monthly=0, today=dt.date(2026, 11, 18))["warning"] is None
    warn = m.tfsa({"tfsa_year": 37000}, monthly=0)["warning"]
    assert "40%" in warn and "check with sars" in warn.lower()
    day = dt.date(2026, 11, 18)  # 4 months left in the tax year: 30,000 + 4 x 3,000 goes over
    assert m.tfsa({"tfsa_year": 30000}, monthly=3000, today=day)["warning"] is not None
    assert m.tfsa({"tfsa_year": 12000}, monthly=3000, today=day)["warning"] is None
    assert m.tfsa({}, 0, today=day)["months_left"] == 4 and m.tfsa({}, 0, today=dt.date(2027, 2, 3))["months_left"] == 1


def test_clean_inputs_rejects_junk_and_clamps():
    assert m.clean({"take_home": "x"}) is None
    assert m.clean({"take_home": -1}) is None
    assert m.clean({"take_home": 1e12}) is None
    assert m.clean({"take_home": "20000", "bogus": 5}) == {"take_home": 20000.0}
    assert m.clean({}) == {}
