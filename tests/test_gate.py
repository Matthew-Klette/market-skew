import pandas as pd

from market_skew import breaking, gate, picks, swing

CALM = {"SPY": {"ret_1m": 0.01}, "VIX": {"ret_1d": 0.0}}


def row(symbol, score, raw=None, checked=True, thin=False, growth=0.18, fcf=0.25):
    return {"symbol": symbol, "score": score, "raw_score": raw if raw is not None else score, "thin": thin, "depth": "Thin" if thin else "Full",
            "growth": growth, "accelerating": True, "metrics": {"fcf_margin": fcf}, "breaking": {"total": 1} if checked else None}


def test_line_cites_both_scores_and_the_reasons():
    text = gate.line(row("A", 74, raw=82))
    assert text.startswith("Quality score 82 → 74: growing 18% and speeding up; keeps 25c of every $1 as free cash")
    assert "not yet checked" not in text


def test_unchecked_rows_use_the_raw_score_and_say_so():
    text = gate.line(row("A", 82, checked=False))
    assert text.startswith("Quality score 82 (not yet checked by Claude)")
    assert gate.table([row("A", 82, checked=False)])["A"]["checked"] is False


def _scored():
    base = dict(bucket="Contrarian Bid", close=50.0, dvol_21=2e8, source="mid", atm=0.20, ret_1m=-0.04, ret_1d=0.01, asym=30,
                market_cap=100e9, name="Co")
    return pd.DataFrame([dict(base, symbol=s, sector=s) for s in ("HI", "EDGE", "LOW", "THIN", "NONE")] +
                        [dict(base, symbol="VOO", sector="Fund")])


def test_swing_needs_his_way_min_after_deductions_and_depth_not_thin():
    bar = gate.HIS_WAY_MIN
    g = gate.table([row("HI", bar + 4, raw=bar + 12), row("EDGE", bar), row("LOW", bar - 1, raw=bar + 20), row("THIN", 95, thin=True)])
    trades = swing.choose(_scored(), {}, CALM, "2026-11-18", set(), gate=g)
    assert {t.symbol for t in trades} == {"HI", "EDGE"}  # LOW fell under the bar after deductions; THIN has too little history; NONE has no score
    assert trades[0].reasons[0].startswith(f"Quality score {bar + 12} → {bar + 4}") or trades[0].reasons[0].startswith(f"Quality score {bar}")
    assert any("options traders lean" in x for x in trades[0].reasons)  # the timing reason follows


def test_swing_without_a_gate_keeps_the_old_rules():
    assert len(swing.choose(_scored(), {}, CALM, "2026-11-18", set())) == 5


def test_no_candidate_passing_gives_an_empty_list():
    assert swing.choose(_scored(), {}, CALM, "2026-11-18", set(), gate={}) == []


def test_steady_needs_steady_min_companies_only_and_funds_are_exempt():
    scored = _scored().assign(atm=0.15)
    bar = gate.STEADY_MIN
    g = gate.table([row("HI", bar), row("EDGE", bar - 1), row("THIN", bar + 1, thin=True)])
    got = picks.choose(scored, {}, set(), gate=g)
    symbols = {p.symbol for p in got}
    assert symbols == {"HI", "THIN", "VOO"}  # depth is not a Steady rule; VOO has no Quality score but is a fund
    assert next(p for p in got if p.symbol == "HI").reasons[0].startswith(f"Quality score {bar}")


def test_breaking_prompt_does_not_deduct_for_missing_numbers_and_version_was_bumped():
    low = breaking.SYSTEM_PROMPT.lower()
    assert "do not deduct" in low and "missing" in low and "visible in the numbers" in low
    assert breaking.version({"as_of": "2026Q3", "score": 80}).startswith(f"{breaking.PROMPT_VERSION}|")


def test_gate_table_carries_the_biggest_deduction_reason():
    r = row("A", 56, raw=76)
    r["breaking"] = {"total": 20, "deductions": [{"points": 3, "reason": "small"}, {"points": 8, "reason": "heavy debt vs free cash."}]}
    assert gate.table([r])["A"]["why"] == "heavy debt vs free cash"
    assert gate.table([row("B", 70, checked=False)])["B"]["why"] is None
