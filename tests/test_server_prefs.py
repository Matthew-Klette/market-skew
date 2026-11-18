import json
import threading

from market_skew.ui import server


def test_prefs_writes_are_atomic_and_do_not_lose_concurrent_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    threads = [threading.Thread(target=server.save_lens, args=(f"2026-{m:02d}", "his")) for m in range(1, 13)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    saved = json.loads((tmp_path / "prefs.json").read_text())
    assert len(saved["lens"]) == 12
    assert not list(tmp_path.glob("*.tmp"))


def test_save_amounts_merges_into_one_month(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PREFS", tmp_path / "prefs.json")
    assert server.save_amounts("2026-11", {"usd": 7000.0})["usd"] == 7000.0
    assert server.amounts_for("2026-11")["usd"] == 7000.0


def test_settings_block_escapes_the_contact():
    from market_skew.ui import views
    html = views.how('"><script>x</script>@e.com')
    assert "<script>x" not in html and "Email for SEC downloads" in html
