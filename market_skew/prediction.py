"""Google's TimesFM 2.5 one-month range for a few names, through the forecaster in tools/predictor.
A projection with a track record, never a promise. Any failure means None and the page hides the block."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from . import system
from .funds import FUNDS

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "tools" / "predictor" / "forecast.py"
PREDICTOR_HOME = system.app_support() / "predictor"
HORIZON, SEASON, ORIGINS = 21, 5, 6
MIN_CLOSES = 120
MAX_CLOSES = 504          # about two years
TIMEOUT_SECONDS = 120
MODEL = "TimesFM 2.5"
PREDICTOR_SCRIPT = r"scripts\install-predictor.ps1" if system.IS_WINDOWS else "scripts/install-predictor.sh"
MISSING_NOTE = f"Google's prediction isn't installed on this {system.DEVICE}. Run {PREDICTOR_SCRIPT} from the project folder to add it (see README)."
BEAT_RATIO = 0.9          # model error under 90% of "no change" error counts as a beat


def wrapper_path() -> Path:
    """MARKET_SKEW_FORECASTER points at a different forecast.py; otherwise the one in tools/predictor."""
    return Path(os.environ.get("MARKET_SKEW_FORECASTER") or WRAPPER)


def env_python() -> Path:
    """The Python that runs the model: MARKET_SKEW_FORECASTER_PYTHON, else the one install-predictor.sh made."""
    return Path(os.environ.get("MARKET_SKEW_FORECASTER_PYTHON") or system.venv_python(PREDICTOR_HOME / "env"))


def available() -> bool:
    """True when the forecaster script and its model environment are both there."""
    return wrapper_path().exists() and env_python().exists()


def run_wrapper(csv_path: str) -> str:
    """The real runner: returns the wrapper's --json stdout. Raises on a non-zero exit."""
    result = subprocess.run(
        [system.console_python(sys.executable or "python3"), *system.python_flags(), str(wrapper_path()), csv_path, "--horizon", str(HORIZON), "--season", str(SEASON),
         "--backtest-origins", str(ORIGINS), "--positive", "--json"],
        capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=True, **system.hidden_window())
    return result.stdout


def verdict(mae_model: float, mae_naive: float, coverage: float) -> str:
    times = max(0, min(5, round(coverage * 5)))
    if mae_naive > 0 and mae_model < mae_naive * BEAT_RATIO:
        lead = "Its middle guess has beaten 'no change' for this stock"
    elif mae_model < mae_naive:
        lead = "Its middle guess has slightly beaten 'no change' for this stock"
    else:
        lead = "Its middle guess hasn't beaten 'no change' for this stock"
    return f"{lead}; the range has been right about {times} times in 5."


def parse(raw: str, last_close: float) -> dict | None:
    data = json.loads(raw)
    step = data["forecast"][HORIZON - 1]
    back = data["backtest"]
    mae = back["mae"]
    coverage = float(back["coverage_10_90"])
    return {"low": float(step["q10"]), "mid": float(step["q50"]), "high": float(step["q90"]),
            "last": float(last_close), "mae_model": float(mae["model"]), "mae_naive": float(mae["naive"]),
            "coverage": coverage, "verdict": verdict(float(mae["model"]), float(mae["naive"]), coverage),
            "model": MODEL, "as_of": str(data.get("last", ""))}


def forecast(symbol: str, closes: pd.Series, runner=run_wrapper) -> dict | None:
    series = closes.dropna().tail(MAX_CLOSES)
    if len(series) < MIN_CLOSES:
        return None
    try:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "series.csv"
            frame = pd.DataFrame({"date": pd.DatetimeIndex(series.index).strftime("%Y-%m-%d"), "value": series.to_numpy()})
            frame.to_csv(path, index=False)
            return parse(runner(str(path)), float(series.iloc[-1]))
    except Exception as error:
        print(f"prediction for {symbol} skipped: {error}"[:300], flush=True)
        return None


def forecast_many(symbols: list[str], closes: pd.DataFrame, runner=run_wrapper, on_done=None) -> dict[str, dict]:
    """One at a time: the model is CPU-heavy. Names with a short history or a failed run are left out."""
    out = {}
    for n, symbol in enumerate(symbols, 1):
        if symbol in closes:
            result = forecast(symbol, closes[symbol], runner)
            if result:
                out[symbol] = result
        if on_done:
            on_done(n, len(symbols))
    return out


def screen_symbols(body: dict) -> list[str]:
    """The names on the Picks page: the index funds, the picks and US holdings, in that order, no repeats."""
    from . import holdings
    names = list(FUNDS) + [t["symbol"] for t in body.get("swing") or []]
    names += [h["symbol"] for h in holdings.load() if h["account"] == "usd"]
    return list(dict.fromkeys(names))
