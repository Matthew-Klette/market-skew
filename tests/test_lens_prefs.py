from market_skew.ui import server


def test_lens_defaults_to_auto_and_follows_recommendation(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    assert server.lens_choice("2026-11") == "auto"
    assert server.lens_for("2026-11", recommended="his") == "his"


def test_lens_choice_is_per_month_and_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    server.save_prefs({"theme": "dark"})
    server.save_lens("2026-11", "his")
    assert server.lens_choice("2026-11") == "his" and server.lens_choice("2026-12") == "auto"
    assert server.lens_for("2026-11", recommended="mine") == "his"
    server.save_lens("2026-12", "mine")
    assert server.lens_choice("2026-11") == "his" and server.prefs()["theme"] == "dark"


def test_garbage_in_prefs_falls_back_to_auto(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    (tmp_path / "prefs.json").write_text('{"lens": {"2026-11": "bogus"}}')
    assert server.lens_choice("2026-11") == "auto"
