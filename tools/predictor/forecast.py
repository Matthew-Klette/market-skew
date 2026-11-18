#!/usr/bin/env python3
"""Forecast a date,value CSV with TimesFM 2.5 (Apache-2.0) and print it next to honest baselines and a backtest.

    forecast.py data.csv --horizon 12 [--season 12] [--backtest-origins 6] [--date-col date --value-col value] [--json]

The model runs in its own Python environment, made by scripts/install-predictor.sh (default folder:
~/Library/Application Support/MarketSkew/predictor). Override with MARKET_SKEW_PREDICTOR_HOME (folder holding env/ and weights/timesfm/)
and MARKET_SKEW_FORECASTER_PYTHON (the Python that runs the model).
Output: point + 10/50/90 quantiles, naive and seasonal-naive baselines, and a backtest on the most recent held-out points.
"""
import argparse
import csv
import datetime as dt
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

WINDOWS = sys.platform == "win32"
if WINDOWS:  # %LOCALAPPDATA%\MarketSkew\predictor, made by scripts\install-predictor.ps1
    _DEFAULT_HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MarketSkew" / "predictor"
else:
    _DEFAULT_HOME = Path.home() / "Library" / "Application Support" / "MarketSkew" / "predictor"
ROOT = Path(os.environ.get("MARKET_SKEW_PREDICTOR_HOME") or _DEFAULT_HOME)
ENV_PYTHON = Path(os.environ.get("MARKET_SKEW_FORECASTER_PYTHON") or (ROOT / "env" / "Scripts" / "python.exe" if WINDOWS else ROOT / "env" / "bin" / "python"))
WEIGHTS = ROOT / "weights" / "timesfm"
WORKER = Path(__file__).resolve().parent / "timesfm_worker.py"
MODEL_LABEL = "TimesFM 2.5 200M (google/timesfm-2.5-200m-pytorch @1d95242, Apache-2.0)"
MAX_CONTEXT = 1024
MAX_HORIZON = 256
RUN_SECONDS = 600


class ForecastError(RuntimeError):
    pass


# ---------- data ----------
def load_csv(path, date_col="date", value_col="value"):
    rows = []
    with open(path, newline="") as handle:
        for record in csv.DictReader(handle):
            raw = (record.get(value_col) or "").strip()
            if raw == "":
                continue
            rows.append((dt.date.fromisoformat(record[date_col].strip()[:10]), float(raw)))
    rows.sort()
    if len(rows) < 8:
        raise ForecastError("Need at least 8 points.")
    return [d for d, _ in rows], [v for _, v in rows]


def infer_step_days(dates):
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    return statistics.median(gaps)


def default_season(step_days):
    if step_days <= 1:
        return 7
    if 6 <= step_days <= 8:
        return 52
    if 27 <= step_days <= 32:
        return 12
    if 88 <= step_days <= 93:
        return 4
    return 1


def future_dates(last, step_days, horizon):
    if 27 <= step_days <= 32:
        out, year, month = [], last.year, last.month
        for _ in range(horizon):
            month += 1
            if month > 12:
                month, year = 1, year + 1
            out.append(dt.date(year, month, min(last.day, 28)))
        return out
    return [last + dt.timedelta(days=int(step_days) * (i + 1)) for i in range(horizon)]


# ---------- baselines ----------
def naive(context, horizon):
    return [context[-1]] * horizon


def seasonal_naive(context, horizon, season):
    if season <= 1 or len(context) < season:
        return naive(context, horizon)
    return [context[len(context) - season + (i % season)] for i in range(horizon)]


# ---------- model ----------
def run_timesfm(contexts, horizon, positive=False):
    """Returns, per context, a list of [q10, q50, q90] per step."""
    if not ENV_PYTHON.exists() or not (WEIGHTS / "model.safetensors").exists():
        raise ForecastError("The predictor is not installed. Run scripts/install-predictor.sh from the project folder (about 1.4 GB).")
    if horizon > MAX_HORIZON:
        raise ForecastError(f"Horizon above {MAX_HORIZON} not supported here.")
    contexts = [c[-MAX_CONTEXT:] for c in contexts]
    payload = json.dumps({"contexts": contexts, "horizon": horizon, "positive": positive}).encode()
    environment = {"HOME": str(ROOT), "PATH": "/usr/bin:/bin", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
                   "OMP_NUM_THREADS": "4", "TOKENIZERS_PARALLELISM": "false"}
    extra = {}
    if WINDOWS:  # Python and PyTorch will not start on Windows without these
        keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS",
                "PROCESSOR_ARCHITECTURE")
        environment.update({key: os.environ[key] for key in keep if key in os.environ})
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        environment["PATH"] = os.pathsep.join([str(Path(system_root) / "System32"), system_root])
        environment["PYTHONUTF8"] = "1"
        extra["creationflags"] = 0x08000000  # no console window
    args = [str(ENV_PYTHON), "-I", str(WORKER), str(WEIGHTS)]
    with tempfile.TemporaryDirectory(prefix="tfm-") as scratch:
        environment["TMPDIR"] = scratch
        if WINDOWS:
            environment["TEMP"] = environment["TMP"] = scratch
        try:
            done = subprocess.run(args, input=payload, capture_output=True, env=environment, timeout=RUN_SECONDS, cwd=ROOT, **extra)
        except subprocess.TimeoutExpired:
            raise ForecastError("TimesFM run timed out.") from None
    if done.returncode != 0:
        raise ForecastError("TimesFM run failed: " + done.stderr.decode(errors="replace")[-400:])
    return json.loads(done.stdout)["paths"]


# ---------- backtest ----------
def mae(actual, predicted):
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)


def backtest(values, horizon, season, origins, predict):
    """Rolling-origin: forecast `horizon` steps from `origins` evenly spaced recent cut points, score against what really happened.

    predict(contexts, horizon) -> per context list of [q10, q50, q90].
    Returns dict with MAE of model/naive/seasonal-naive, interval coverage of the 10-90 band (nominal 80%), and which origins were used.
    """
    n = len(values)
    horizon = min(horizon, max(1, n // 4))
    last_cut = n - horizon
    first_cut = max(horizon * 2, last_cut - (origins - 1) * horizon)
    cuts = sorted({last_cut - i * max(1, (last_cut - first_cut) // max(1, origins - 1)) for i in range(origins)} if origins > 1 else {last_cut})
    cuts = [c for c in cuts if c >= max(8, horizon)]
    if not cuts:
        raise ForecastError("Series too short to backtest.")
    paths = predict([values[:c] for c in cuts], horizon)
    errs = {"model": [], "naive": [], "seasonal_naive": []}
    inside = total = 0
    for cut, path in zip(cuts, paths):
        actual = values[cut:cut + horizon]
        errs["model"].append(mae(actual, [p[1] for p in path]))
        errs["naive"].append(mae(actual, naive(values[:cut], horizon)))
        errs["seasonal_naive"].append(mae(actual, seasonal_naive(values[:cut], horizon, season)))
        for a, p in zip(actual, path):
            total += 1
            inside += p[0] <= a <= p[2]
    summary = {k: sum(v) / len(v) for k, v in errs.items()}
    best_base = min(summary["naive"], summary["seasonal_naive"])
    return {"origins": len(cuts), "horizon": horizon, "mae": summary, "coverage_10_90": inside / total,
            "beats_best_baseline": summary["model"] < best_base, "ratio_vs_best_baseline": summary["model"] / best_base if best_base else float("inf")}


def verdict(bt):
    if bt["beats_best_baseline"] and bt["ratio_vs_best_baseline"] < 0.9:
        return "model beat both baselines on held-out points: usable, still not fact"
    if bt["beats_best_baseline"]:
        return "model only marginally beat the best baseline: treat as a baseline-level forecast"
    return "model did NOT beat a baseline on held-out points: use the baseline"


def forecast(dates, values, horizon, season, origins, predict):
    path = predict([values], horizon)[0]
    bt = backtest(values, horizon, season, origins, predict)
    step = infer_step_days(dates)
    return {"model": MODEL_LABEL, "n_points": len(values), "first": str(dates[0]), "last": str(dates[-1]), "season": season, "horizon": horizon,
            "forecast": [{"date": str(d), "q10": p[0], "q50": p[1], "q90": p[2], "naive": b, "seasonal_naive": s}
                         for d, p, b, s in zip(future_dates(dates[-1], step, horizon), path, naive(values, horizon), seasonal_naive(values, horizon, season))],
            "backtest": bt, "verdict": verdict(bt)}


def render(result):
    bt = result["backtest"]
    lines = [f"Model: {result['model']}", f"Data: {result['n_points']} points, {result['first']} to {result['last']}; season={result['season']}; horizon={result['horizon']}",
             "", f"{'date':<12}{'q10':>12}{'q50':>12}{'q90':>12}{'naive':>12}{'seas.naive':>12}"]
    for r in result["forecast"]:
        lines.append(f"{r['date']:<12}{r['q10']:>12.2f}{r['q50']:>12.2f}{r['q90']:>12.2f}{r['naive']:>12.2f}{r['seasonal_naive']:>12.2f}")
    m = bt["mae"]
    lines += ["", f"Backtest ({bt['origins']} origins x {bt['horizon']} held-out steps): MAE model {m['model']:.3f} | naive {m['naive']:.3f} | seasonal-naive {m['seasonal_naive']:.3f}",
              f"10-90 band coverage {bt['coverage_10_90']:.0%} (nominal 80%)", f"Verdict: {result['verdict']}",
              "Not fact: a statistical projection from past values only (no holidays/prices/covariates in this wrapper)."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--horizon", type=int, required=True)
    ap.add_argument("--season", type=int, help="period in steps (default inferred: daily 7, weekly 52, monthly 12, quarterly 4)")
    ap.add_argument("--backtest-origins", type=int, default=4)
    ap.add_argument("--date-col", default="date")
    ap.add_argument("--value-col", default="value")
    ap.add_argument("--positive", action="store_true", help="clamp to non-negative series")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        dates, values = load_csv(a.csv, a.date_col, a.value_col)
        season = a.season or default_season(infer_step_days(dates))
        result = forecast(dates, values, a.horizon, season, a.backtest_origins, lambda c, h: run_timesfm(c, h, a.positive))
    except (ForecastError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1) if a.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
