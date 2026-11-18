import datetime as dt
import json

from market_skew import cache, edgar, fundamentals_run, store

TODAY = dt.date(2026, 11, 18)


def test_periods_run_newest_first():
    assert edgar.quarter_periods(TODAY, 3) == ["2026Q3", "2026Q2", "2026Q1"]
    assert edgar.quarter_periods(dt.date(2026, 2, 1), 2) == ["2025Q4", "2025Q3"]
    assert edgar.year_periods(TODAY, 2) == ["2025", "2024"]
    assert edgar.frame_period("2026Q3", "instant", True) == "CY2026Q3I"
    assert edgar.frame_period("2025", "flow") == "CY2025"


def test_parse_frame_keeps_the_latest_end_date_per_company():
    payload = {"data": [{"cik": 1, "val": 5, "end": "2025-06-30"}, {"cik": 1, "val": 7, "end": "2025-09-30"}, {"cik": 2, "val": None}]}
    assert edgar.parse_frame(payload) == {"1": 7.0}


def use_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar, "DIR", tmp_path)


def test_fetch_all_skips_fresh_cache_and_refetches_old(monkeypatch, tmp_path):
    use_tmp(monkeypatch, tmp_path)
    calls = []

    def get(url):
        calls.append(url)
        return {"data": [{"cik": 9, "val": 1, "end": "2026-09-30"}]}
    first = edgar.fetch_all(TODAY, now=1_000_000, get=get, sleep=lambda s: None, log=lambda *a: None)
    assert first["requests"] == len(edgar.jobs(TODAY)) == len(calls) and first["failed"] == 0
    assert all(u.startswith("https://data.sec.gov/api/xbrl/frames/") for u in calls)
    again = edgar.fetch_all(TODAY, now=1_000_000 + 3600, get=get, sleep=lambda s: None)
    assert again["requests"] == 0
    stale = edgar.fetch_all(TODAY, now=1_000_000 + 8 * 86400, get=get, sleep=lambda s: None)
    assert stale["requests"] == first["requests"]


def test_a_failed_request_is_counted_and_keeps_going(monkeypatch, tmp_path):
    use_tmp(monkeypatch, tmp_path)

    def get(url):
        raise OSError("blocked")
    out = edgar.fetch_all(TODAY, now=5, get=get, sleep=lambda s: None, log=lambda *a: None)
    assert out["failed"] == out["requests"] == edgar.GIVE_UP_AFTER


def test_debt_falls_back_to_noncurrent_plus_current():
    assert edgar._pick("debt", [None, 100.0, 20.0]) == 120.0
    assert edgar._pick("debt", [90.0, 100.0, 20.0]) == 90.0
    assert edgar._pick("debt", [None, None, 20.0]) is None
    assert edgar._pick("revenue", [None, 5.0, 6.0]) == 5.0


def test_refresh_saves_rows_and_skips_foreign_filers(monkeypatch, tmp_path):
    use_tmp(monkeypatch, tmp_path)
    for label in edgar.quarter_periods(TODAY, 8):
        cache.write(edgar._path("Revenues", label, False), {"fetched": 1, "values": {"111": 100.0}})
    with store.connect(tmp_path / "t.db") as conn:
        out = fundamentals_run.refresh(conn, ["AAA", "BRK.B", "FOREIGN", "NOCIK"], TODAY, fetch=lambda today, log=print: {"requests": 0, "failed": 0},
                                       mapping={"AAA": "111", "BRK-B": "111", "FOREIGN": "222"})
        saved = store.fundamentals(conn)
    assert out["rows"] == 2 and out["universe"] == 4
    assert set(saved) == {"AAA", "BRK.B"} and saved["AAA"]["cik"] == "111" and saved["AAA"]["ttm_revenue"] == 400.0
    json.dumps(saved)


def test_user_agent_carries_the_contact(monkeypatch):
    monkeypatch.setattr(edgar.settings, "sec_contact", lambda path=None: "someone@example.org")
    assert edgar.user_agent() == f"{edgar.APP_AGENT} someone@example.org"


def test_no_contact_stops_before_any_request(monkeypatch, tmp_path):
    import urllib.request

    import pytest
    monkeypatch.setattr(edgar.settings, "PREFS", tmp_path / "none.json")
    use_tmp(monkeypatch, tmp_path)

    def boom(*a, **k):
        raise AssertionError("a request was made")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(edgar.NoContact, match="Add your email under Settings"):
        edgar.fetch_all(TODAY, now=1, sleep=lambda s: None)


def test_contact_validation_and_read(tmp_path):
    from market_skew import settings
    assert settings.valid_email("a.b@example.com") and not settings.valid_email("a b@x.com")
    assert not settings.valid_email("x@y") and not settings.valid_email("a" * 250 + "@x.com") and not settings.valid_email(None)
    path = tmp_path / "prefs.json"
    path.write_text('{"theme": "dark", "sec_contact": "a@example.com"}')
    assert settings.sec_contact(path) == "a@example.com"
    path.write_text('{"sec_contact": "<script>"}')
    assert settings.sec_contact(path) is None


def test_debt_falls_back_to_a_combined_figure_and_cash_prefers_the_broad_tag():
    assert edgar._pick("debt", [None, None, 5.0, 40.0, None]) == 40.0
    assert edgar._pick("debt", [None, 30.0, 5.0, 40.0, None]) == 35.0
    assert edgar._pick("debt", [90.0, 30.0, 5.0, 40.0, None]) == 90.0
    assert edgar.SPECS["cash"][1][0][1] == "CashCashEquivalentsAndShortTermInvestments"
    assert "ElectricUtilityRevenue" in [c for _, c, _ in edgar.SPECS["revenue"][1]]


def test_cash_adds_short_term_investments_without_double_counting():
    assert edgar._pick("cash", [500.0, 100.0, 300.0, 200.0, None]) == 500.0      # combined tag already includes them
    assert edgar._pick("cash", [None, 100.0, 300.0, 200.0, 50.0]) == 400.0       # cash + first investments tag only
    assert edgar._pick("cash", [None, 100.0, None, None, 50.0]) == 150.0
    assert edgar._pick("cash", [None, 100.0, None, None, None]) == 100.0
    assert edgar._pick("cash", [None, None, 300.0, None, None]) is None          # investments alone are not cash
    tags = [c for _, c, _ in edgar.SPECS["cash"][1]]
    assert tags[2:] == ["MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
                      "MarketableSecuritiesNoncurrent"]


def test_company_series_sums_cash_and_investments_from_frames():
    frames = {("CashAndCashEquivalentsAtCarryingValue", "2026Q3", True): {"7": 100.0},
              ("ShortTermInvestments", "2026Q3", True): {"7": 40.0}}
    assert edgar.company_series("7", TODAY, frames)["i"]["cash"]["2026Q3"] == 140.0


def test_gross_profit_falls_back_to_revenue_minus_cost_of_revenue():
    frames = {("Revenues", "2026Q3", False): {"7": 1000.0, "8": 500.0},
              ("CostOfGoodsAndServicesSold", "2026Q3", False): {"7": 600.0},
              ("CostOfRevenue", "2026Q3", False): {"8": 100.0},
              ("GrossProfit", "2026Q3", False): {"8": 350.0}}
    series = edgar.company_series("7", TODAY, frames)
    assert series["q"]["gross"]["2026Q3"] == 400.0 and "cost" not in series["q"]
    assert edgar.company_series("8", TODAY, frames)["q"]["gross"]["2026Q3"] == 350.0  # a tagged GrossProfit wins
    assert edgar.company_series("9", TODAY, frames)["q"].get("gross") is None


def test_operating_cash_flow_has_a_continuing_operations_alternative():
    frames = {("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "2025", False): {"7": 90.0}}
    assert edgar.company_series("7", TODAY, frames)["a"]["ocf"]["2025"] == 90.0


def test_long_term_marketable_securities_are_added_once_to_cash():
    assert edgar._pick("cash", [None, 100.0, None, 50.0, None, 30.0]) == 180.0
    assert edgar._pick("cash", [500.0, None, None, None, None, 30.0]) == 530.0
    assert edgar._pick("cash", [None, 100.0, None, None, None, None]) == 100.0
