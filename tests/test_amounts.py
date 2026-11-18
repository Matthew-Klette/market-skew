import json

from market_skew.ui import server


def test_defaults_when_unset_and_per_month_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    assert server.amounts_for("2026-11") == {"tfsa": 0.0, "usd": 0.0}
    server.save_amounts("2026-11", {"usd": 7000.0})
    server.save_amounts("2026-12", {"tfsa": 1000.0})
    assert server.amounts_for("2026-11") == {"tfsa": 0.0, "usd": 7000.0}
    assert server.amounts_for("2026-12") == {"tfsa": 1000.0, "usd": 0.0}
    assert json.loads((tmp_path / "prefs.json").read_text())["amounts"]["2026-11"]["usd"] == 7000.0


def test_saving_amounts_keeps_other_prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    server.save_prefs({"theme": "dark"})
    server.save_amounts("2026-11", {"tfsa": 10.0})
    assert server.prefs()["theme"] == "dark"


def test_amounts_set_is_false_until_something_is_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    assert server.amounts_set("2026-11") is False
    server.save_amounts("2026-11", {"usd": 7000.0})
    assert server.amounts_set("2026-11") is True
    assert server.amounts_set("2026-12") is False


def test_fresh_install_picks_page_asks_for_monthly_amounts(tmp_path, monkeypatch):
    real_connect = server.store.connect
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    monkeypatch.setattr(server.store, "connect", lambda *a, **k: real_connect(tmp_path / "t.db"))
    code, html = server.render("/", {})
    assert code == 200 and "Tell me how much you invest each month" in html and "No report yet" in html
    server.save_amounts(server.month_key(), {"usd": 1000.0})
    assert "Tell me how much you invest each month" not in server.render("/", {})[1]
