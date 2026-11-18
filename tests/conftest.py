"""Keep the tests away from the real data folder, so running them never leaves a fake "scan running" status
or earnings file behind (a fresh install runs the tests before its first open)."""
import pytest

from market_skew import earnings, scan


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(scan, "LOCK", tmp_path / "run.lock")
    monkeypatch.setattr(earnings, "PATH", tmp_path / "earnings.json")


@pytest.fixture(autouse=True)
def _accepted(request, monkeypatch):
    """Page tests see the app after the one-time "not financial advice" screen was accepted, unless a test opts out."""
    if request.node.get_closest_marker("gate"):
        return
    from market_skew.ui import server
    real = server.prefs
    monkeypatch.setattr(server, "prefs", lambda: {"accepted_terms": "2026-01-01T00:00:00", **real()})
