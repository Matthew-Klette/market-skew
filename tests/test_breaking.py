import json
import subprocess

import pytest

from market_skew import breaking, breaking_run, sentinel, store
from tests.test_sentinel import metrics, peers, px


def rows(**over):
    f, p = peers()
    f["ACME"], p["ACME"] = metrics(**over), px(name="Acme")
    return sentinel.score_all(f, p)


def acme(**over):
    return next(r for r in rows(**over) if r["symbol"] == "ACME")


GOOD = '{"deductions":[{"points":6,"reason":"Debt is high."},{"points":4,"reason":"Growth is slowing."}],"what_breaks":"A sales slowdown would hurt."}'


def test_parse_reads_clean_json_and_json_inside_chatter():
    out = breaking.parse(GOOD)
    assert out == {"deductions": [{"points": 6, "reason": "Debt is high."}, {"points": 4, "reason": "Growth is slowing."}],
                   "what_breaks": "A sales slowdown would hurt.", "total": 10}
    assert breaking.parse("Sure! Here you go:\n```json\n" + GOOD + "\n```\nHope that helps {not json}")["total"] == 10


def test_parse_skips_a_leading_object_that_is_not_json_and_takes_the_first_valid_dict():
    assert breaking.parse("{oops} " + GOOD)["total"] == 10


@pytest.mark.parametrize("text", ["", "no json here", "[1,2]", '{"deductions": "many"}', '{"what_breaks": "x"}', "{broken",
                                  '{"deductions": [{"points": 3}], "what_breaks": ""}'])
def test_parse_rejects_unusable_replies(text):
    assert breaking.parse(text) is None


def test_parse_clamps_points_and_drops_bad_items():
    text = json.dumps({"deductions": [{"points": 99, "reason": "big"}, {"points": 0, "reason": "zero"}, {"points": -4, "reason": "neg"},
                                      {"points": "7", "reason": "string"}, {"points": True, "reason": "bool"}, {"points": 3.6, "reason": "float"},
                                      {"points": 5, "reason": ""}, "junk", {"points": 5}], "what_breaks": "x"})
    out = breaking.parse(text)
    cap = breaking.MAX_POINTS
    first = [cap, 1, 1, min(7, cap)]  # over-cap clamps down, under 1 clamps up
    last = min(4, cap, breaking.MAX_TOTAL - sum(first))  # 3.6 rounds to 4, then the running total cap may trim it
    assert [d["points"] for d in out["deductions"]] == first + [last]


def test_parse_caps_each_item_and_the_total_and_the_reason_at_20_words():
    items = [{"points": 10, "reason": " ".join(["word"] * 30)} for _ in range(5)]
    out = breaking.parse(json.dumps({"deductions": items, "what_breaks": "w" * 500}))
    full, rest = divmod(breaking.MAX_TOTAL, breaking.MAX_POINTS)
    assert out["total"] == breaking.MAX_TOTAL
    assert [d["points"] for d in out["deductions"]] == [breaking.MAX_POINTS] * full + ([rest] if rest else [])
    assert out["deductions"][0]["reason"].endswith("...") and len(out["deductions"][0]["reason"].split()) == 20
    assert len(out["what_breaks"]) == breaking.MAX_BREAKS


def test_parse_accepts_a_healthy_company_with_no_deductions():
    out = breaking.parse('{"deductions": [], "what_breaks": "Nothing in the numbers stands out."}')
    assert out["deductions"] == [] and out["total"] == 0


def test_brief_has_numbers_only_and_no_missing_value_crashes():
    text = breaking.brief(acme())
    for needle in ("ACME", "Quality score", "Pillars", "sales last 12 months", "free cash yield", "options market bucket Chase", "to 2025Q4"):
        assert needle in text
    sparse = breaking.brief(acme(revenue_growth=None, fcf=None, fcf_margin=None, net_cash=None))
    assert "n/a" in sparse


class Done:
    def __init__(self, out="", code=0, err=""):
        self.stdout, self.returncode, self.stderr = out, code, err


def test_ask_runs_claude_with_tools_off_a_clean_env_and_the_brief_on_stdin(monkeypatch):
    monkeypatch.setattr(breaking, "_claude", lambda: "/bin/claude")
    seen = {}

    def run(command, **kw):
        seen.update(command=command, **kw)
        return Done(GOOD)
    out = breaking.ask(acme(), run)
    c = seen["command"]
    assert out["total"] == 10
    assert c[:2] == ["/bin/claude", "-p"] and "--safe-mode" in c and "--no-session-persistence" in c and "--strict-mcp-config" in c
    assert c[c.index("--tools") + 1] == "" and c[c.index("--model") + 1] == "haiku" and c[c.index("--output-format") + 1] == "text"
    assert c[c.index("--system-prompt") + 1] == breaking.SYSTEM_PROMPT
    assert seen["input"] == breaking.brief(acme()) and seen["timeout"] == 60
    assert not any("KEY" in k or "TOKEN" in k for k in seen["env"])


def test_ask_turns_timeouts_failures_and_junk_into_breaking_errors(monkeypatch):
    monkeypatch.setattr(breaking, "_claude", lambda: "/bin/claude")

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("claude", 60)
    for run in (timeout, lambda *a, **k: Done("", 1, "boom"), lambda *a, **k: Done("sorry, no")):
        with pytest.raises(breaking.BreakingError):
            breaking.ask(acme(), run)


def test_apply_subtracts_relabels_reranks_and_ignores_stale_answers():
    base = rows()
    top = base[0]
    answer = {"version": breaking.version(top), "deductions": [], "what_breaks": "x", "total": 30}
    stale = {"version": "2020Q1|99", "deductions": [], "what_breaks": "x", "total": 30}
    out = breaking.apply(base, {top["symbol"]: answer})
    moved = next(r for r in out if r["symbol"] == top["symbol"])
    assert moved["raw_score"] == top["score"] and moved["score"] == max(0, top["score"] - 30)
    assert moved["label"] == sentinel.label(moved["score"]) and breaking.headline(moved) == f"{top['score']} → {moved['score']}"
    assert [r["rank"] for r in out] == list(range(1, len(out) + 1)) and out[0]["score"] >= out[-1]["score"]
    ignored = breaking.apply(base, {top["symbol"]: stale})
    assert all(r["breaking"] is None and r["score"] == r["raw_score"] for r in ignored)
    assert breaking.headline(ignored[0]) == str(ignored[0]["score"])
    assert breaking.apply(base, {top["symbol"]: {**answer, "total": 500}})[-1]["score"] >= 0


@pytest.fixture
def conn(tmp_path):
    with store.connect(tmp_path / "t.db") as c:
        yield c


def test_run_caches_per_data_version_and_reruns_when_numbers_change(conn):
    calls = []

    def ask(row):
        calls.append(row["symbol"])
        return {"deductions": [{"points": 5, "reason": "r"}], "what_breaks": "w", "total": 5}
    data = rows()
    assert breaking_run.run(conn, data, ["ACME"], ask, log=lambda *a: None) == {"asked": 1, "cached": 0, "failed": 0}
    assert breaking_run.run(conn, data, ["ACME"], ask) == {"asked": 0, "cached": 1, "failed": 0} and calls == ["ACME"]
    saved = store.breaking(conn)["ACME"]
    assert saved["total"] == 5 and saved["version"] == breaking.version(data[[r["symbol"] for r in data].index("ACME")])
    newer = rows(as_of="2026Q1")  # new filing period: the old answer is stale
    assert breaking_run.run(conn, newer, ["ACME"], ask)["asked"] == 1 and calls == ["ACME", "ACME"]
    changed = rows(revenue_growth=0.0)  # same period, different score
    assert breaking_run.run(conn, changed, ["ACME"], ask)["asked"] == 1


def test_run_skips_failures_unknown_symbols_and_keeps_going(conn):
    logged = []

    def ask(row):
        if row["symbol"] == "P1":
            raise breaking.BreakingError("timed out")
        return {"deductions": [], "what_breaks": "w", "total": 0}
    out = breaking_run.run(conn, rows(), ["P1", "NOPE", "P2"], ask, log=logged.append)
    assert out == {"asked": 1, "cached": 0, "failed": 1} and set(store.breaking(conn)) == {"P2"} and "P1 skipped" in logged[0]


def test_on_screen_lists_picks_swing_us_holdings_and_top_watch_without_repeats_or_excluded():
    data = rows()
    for i, r in enumerate(data):
        r["label"] = "WATCH" if i < 25 else "OK"
        r["rank"] = i + 1
    names = [r["symbol"] for r in data]
    report = {"picks": [{"symbol": names[30 % len(names)]}], "swing": [{"symbol": names[1]}, {"symbol": "ZZZ"}]}
    owned = [{"symbol": names[2], "account": "usd"}, {"symbol": names[3], "account": "tfsa"}, {"symbol": "VOO", "account": "usd"}]
    out = breaking_run.on_screen(report, data, owned, skip={names[4]})
    assert out[0] == names[30 % len(names)] and names[1] in out and names[2] in out
    assert names[3] not in out[:3] and "ZZZ" not in out and "VOO" not in out and names[4] not in out
    assert len(out) == len(set(out))
