import datetime as dt

import pandas as pd

from market_skew import earnings

TODAY = dt.date(2026, 11, 18)


def dates_frame(rows):
    """rows: (ISO timestamp, estimate, reported or None, surprise % or None), like Ticker.get_earnings_dates."""
    index = pd.DatetimeIndex([pd.Timestamp(r[0], tz="America/New_York") for r in rows], name="Earnings Date")
    return pd.DataFrame({"EPS Estimate": [r[1] for r in rows], "Reported EPS": [r[2] for r in rows],
                         "Surprise(%)": [r[3] for r in rows]}, index=index)


def history_frame(rows):
    """rows: (estimate, actual), oldest first, like Ticker.earnings_history."""
    return pd.DataFrame({"epsEstimate": [r[0] for r in rows], "epsActual": [r[1] for r in rows],
                         "surprisePercent": [(r[1] - r[0]) / abs(r[0]) for r in rows]},
                        index=pd.to_datetime(["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"][-len(rows):]))


FOUR_BEATS = history_frame([(1.0, 1.03), (1.0, 1.04), (1.0, 1.02), (1.0, 1.034)])
NEXT = dates_frame([("2026-12-12 16:30", 1.1, None, None), ("2026-09-10 16:30", 1.0, 1.034, 3.4)])


def test_line_for_four_beats_and_next_date():
    result = earnings.parse(NEXT, FOUR_BEATS, None, TODAY)
    assert result["kind"] == "stock" and result["next_date"] == "2026-12-12"
    assert result["beats"] == 4 and result["of"] == 4
    assert abs(result["avg_surprise"] - 3.1) < 0.01
    assert earnings.line(result) == "Reports 12 Dec · beat 4 of the last 4, average surprise +3.1%"


def test_counts_only_real_beats():
    hist = history_frame([(1.0, 1.05), (1.0, 0.95), (1.0, 1.0), (1.0, 1.1)])
    result = earnings.parse(NEXT, hist, None, TODAY)
    assert (result["beats"], result["of"]) == (2, 4)
    assert "beat 2 of the last 4" in earnings.line(result)


def test_only_the_last_four_count():
    old = history_frame([(1.0, 0.5)]).rename(index={pd.Timestamp("2026-09-30"): pd.Timestamp("2025-06-30")})
    result = earnings.parse(NEXT, pd.concat([old, FOUR_BEATS]), None, TODAY)
    assert (result["beats"], result["of"]) == (4, 4)


def test_falls_back_to_dates_table_when_history_missing():
    dates = dates_frame([("2026-12-12 16:30", 1.1, None, None), ("2026-09-10 16:30", 1.0, 1.05, 5.0),
                         ("2026-06-10 16:30", 1.0, 0.9, -10.0), ("2026-03-10 16:30", 1.0, 1.1, 10.0)])
    result = earnings.parse(dates, None, None, TODAY)
    assert (result["beats"], result["of"]) == (2, 3)
    assert abs(result["avg_surprise"] - 1.67) < 0.01


def test_no_history_still_gives_the_date():
    result = earnings.parse(NEXT.iloc[:1], None, None, TODAY)
    assert earnings.line(result) == "Reports 12 Dec · no track record yet"


def test_nothing_at_all_is_none():
    assert earnings.parse(None, None, None, TODAY) is None
    assert earnings.parse(pd.DataFrame(), pd.DataFrame(), None, TODAY) is None


def test_past_dates_are_not_next():
    past = dates_frame([("2026-09-10 16:30", 1.0, 1.034, 3.4)])
    result = earnings.parse(past, FOUR_BEATS, None, TODAY)
    assert result["next_date"] is None
    assert earnings.line(result).startswith("Next date not announced")


def test_wide_spread_when_range_over_20_percent_of_consensus():
    wide = earnings.parse(NEXT, FOUR_BEATS, {"high": 1.3, "low": 0.9, "avg": 1.1}, TODAY)
    narrow = earnings.parse(NEXT, FOUR_BEATS, {"high": 1.15, "low": 1.05, "avg": 1.1}, TODAY)
    assert wide["spread"] == "wide" and narrow["spread"] == "narrow"
    assert "analysts disagree" in earnings.line(wide) and "analysts disagree" not in earnings.line(narrow)
    assert earnings.parse(NEXT, FOUR_BEATS, None, TODAY)["spread"] is None


def test_soon_within_two_weeks():
    assert earnings.soon("2026-12-01", TODAY) is True
    assert earnings.soon("2026-12-02", TODAY) is True
    assert earnings.soon("2026-12-03", TODAY) is False
    assert earnings.soon(None, TODAY) is False
    assert earnings.soon("2026-11-10", TODAY) is False


def test_fund_line():
    assert earnings.line({"kind": "fund"}) == "Fund: no earnings"


class FakeTicker:
    def __init__(self, dates=None, history=None, estimate=None, quote="EQUITY", fail=()):
        self._d, self._h, self._e, self._q, self._fail = dates, history, estimate, quote, fail

    def get_earnings_dates(self, limit=8):
        if "dates" in self._fail:
            raise RuntimeError("boom")
        return self._d

    @property
    def earnings_history(self):
        if "history" in self._fail:
            raise RuntimeError("boom")
        return self._h

    @property
    def earnings_estimate(self):
        if "estimate" in self._fail:
            raise RuntimeError("boom")
        return self._e

    @property
    def info(self):
        return {"quoteType": self._q}


def test_fetch_survives_a_failing_history_call():
    result = earnings.fetch("AAA", TODAY, lambda s: FakeTicker(NEXT, None, None, fail=("history", "estimate")))
    assert result["next_date"] == "2026-12-12" and result["of"] == 1


def test_fetch_marks_etf_as_fund():
    result = earnings.fetch("QQQ", TODAY, lambda s: FakeTicker(pd.DataFrame(), pd.DataFrame(), None, quote="ETF", fail=("dates",)))
    assert result == {"kind": "fund"}


def test_fetch_known_fund_skips_the_network():
    def boom(_s):
        raise AssertionError("no network for a known fund")
    assert earnings.fetch("QQQ", TODAY, boom) == {"kind": "fund"}


def test_fetch_total_failure_is_none():
    assert earnings.fetch("ZZZ", TODAY, lambda s: FakeTicker(None, None, None, fail=("dates", "history", "estimate"))) is None


def test_refresh_is_sequential_paced_cached_and_skips_fresh(tmp_path):
    path, naps, seen = tmp_path / "earnings.json", [], []

    def factory(symbol):
        seen.append(symbol)
        return FakeTicker(NEXT, FOUR_BEATS, None)

    out = earnings.refresh(["AAA", "BBB"], TODAY, factory, path=path, sleep=naps.append, now=1000.0)
    assert set(out) == {"AAA", "BBB"} and seen == ["AAA", "BBB"] and len(naps) >= 1
    again = earnings.refresh(["AAA", "BBB"], TODAY, factory, path=path, sleep=naps.append, now=1000.0 + 3600)
    assert seen == ["AAA", "BBB"] and set(again) == {"AAA", "BBB"}  # fresh within a day: nothing fetched
    earnings.refresh(["AAA"], TODAY, factory, path=path, sleep=naps.append, now=1000.0 + 90000)
    assert seen == ["AAA", "BBB", "AAA"]


def test_refresh_keeps_last_good_value_on_failure(tmp_path):
    path = tmp_path / "e.json"
    earnings.refresh(["AAA"], TODAY, lambda s: FakeTicker(NEXT, FOUR_BEATS, None), path=path, sleep=lambda n: None, now=1000.0)
    out = earnings.refresh(["AAA"], TODAY, lambda s: FakeTicker(None, None, None, fail=("dates", "history", "estimate")),
                           path=path, sleep=lambda n: None, now=1000.0 + 90000)
    assert out["AAA"]["beats"] == 4
