import pytest

from market_skew.ui import routes, server, views


@pytest.mark.gate
def test_gate_shows_until_accepted(monkeypatch):
    monkeypatch.setattr(server, "prefs", lambda: {})
    code, html = server.render("/", {})
    assert code == 200 and "not financial advice" in html and "data-accept" in html


def test_gate_gone_after_accepting(monkeypatch):
    monkeypatch.setattr(server, "prefs", lambda: {"accepted_terms": "2026-11-18T20:00:00"})
    code, html = server.render("/how", {})
    assert code == 200 and "data-accept" not in html


def test_accept_route_saves_a_timestamp():
    saved = {}

    class App:
        def save_prefs(self, values):
            saved.update(values)

    code, body = routes.dispatch("/accept", {}, App())
    assert code == 200 and saved["accepted_terms"] == body["accepted"]


def test_gate_text_points_to_an_adviser():
    assert "licensed financial adviser" in views.accept_gate()
