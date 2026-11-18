import json

import numpy as np
import pandas as pd

from market_skew import prediction


def payload(model=1.0, naive=2.0, coverage=0.8):
    rows = [{"date": f"2026-01-{i + 1:02d}", "q10": 90 + i, "q50": 100 + i, "q90": 110 + i} for i in range(21)]
    return json.dumps({"last": "2026-01-01", "forecast": rows,
                       "backtest": {"mae": {"model": model, "naive": naive, "seasonal_naive": 3.0}, "coverage_10_90": coverage}})


def closes(n=200):
    return pd.Series(np.linspace(100, 120, n), index=pd.bdate_range("2025-01-01", periods=n))


def test_parse_takes_step_21_quantiles():
    result = prediction.parse(payload(), 105.0)
    assert (result["low"], result["mid"], result["high"]) == (110.0, 120.0, 130.0)
    assert result["last"] == 105.0 and result["mae_naive"] == 2.0


def test_verdict_not_beaten():
    text = prediction.verdict(2.5, 2.0, 0.8)
    assert "hasn't beaten 'no change'" in text and "about 4 times in 5" in text


def test_verdict_slightly_beat():
    assert "slightly beaten 'no change'" in prediction.verdict(1.9, 2.0, 0.83)


def test_verdict_clear_beat_never_claims_certainty():
    text = prediction.verdict(1.0, 2.0, 1.0)
    assert "has beaten" in text and "5 times in 5" in text and "will" not in text


def test_forecast_uses_injected_runner_and_csv():
    seen = {}

    def runner(path):
        seen["rows"] = open(path).read().splitlines()
        return payload()
    result = prediction.forecast("VOO", closes(), runner)
    assert result["mid"] == 120.0 and seen["rows"][0] == "date,value" and len(seen["rows"]) == 201


def test_forecast_none_on_runner_failure():
    def runner(path):
        raise FileNotFoundError("no env")
    assert prediction.forecast("VOO", closes(), runner) is None


def test_forecast_none_on_garbage_output():
    assert prediction.forecast("VOO", closes(), lambda p: "not json") is None


def test_forecast_many_skips_short_history_and_missing():
    frame = pd.DataFrame({"AAA": closes(), "BBB": closes(60).reindex(closes().index)})
    out = prediction.forecast_many(["AAA", "BBB", "CCC"], frame, lambda p: payload())
    assert list(out) == ["AAA"]


def test_verdict_says_right_about_n_times_in_5():
    assert "the range has been right about 4 times in 5" in prediction.verdict(2.5, 2.0, 0.8)


def test_forecaster_path_follows_env_var(monkeypatch, tmp_path):
    fake, python = tmp_path / "forecast.py", tmp_path / "python"
    fake.write_text("")
    python.write_text("")
    monkeypatch.setenv("MARKET_SKEW_FORECASTER", str(fake))
    monkeypatch.setenv("MARKET_SKEW_FORECASTER_PYTHON", str(python))
    assert prediction.wrapper_path() == fake and prediction.env_python() == python and prediction.available()
    monkeypatch.setenv("MARKET_SKEW_FORECASTER", str(tmp_path / "missing.py"))
    assert not prediction.available()


def test_defaults_point_at_the_repo_script_and_the_installer_folder(monkeypatch):
    monkeypatch.delenv("MARKET_SKEW_FORECASTER", raising=False)
    monkeypatch.delenv("MARKET_SKEW_FORECASTER_PYTHON", raising=False)
    assert prediction.wrapper_path().as_posix().endswith("tools/predictor/forecast.py") and prediction.wrapper_path().exists()
    assert prediction.env_python().as_posix().endswith("Library/Application Support/MarketSkew/predictor/env/bin/python")


def test_csv_file_name_is_fixed():
    seen = {}
    prediction.forecast("ZZZ", closes(), lambda path: seen.setdefault("name", path.rsplit("/", 1)[-1]) and payload())
    assert seen["name"] == "series.csv"
