import os
import subprocess
import threading
from http.server import ThreadingHTTPServer

import pytest

from market_skew import atomic, holdings, scan
from market_skew.ui import routes, server


def test_atomic_write_is_a_temp_file_renamed_into_place(tmp_path, monkeypatch):
    target = tmp_path / "w.txt"
    target.write_text("old\n")
    calls = []
    real = os.replace
    monkeypatch.setattr(atomic.os, "replace", lambda a, b: (calls.append((os.path.basename(a), os.path.basename(b))), real(a, b)))
    atomic.write_text(target, "new\n")
    assert target.read_text() == "new\n" and calls and calls[0][1] == "w.txt" and calls[0][0] != "w.txt"
    assert [p.name for p in tmp_path.iterdir()] == ["w.txt"]


def test_a_failed_write_leaves_the_old_file_and_no_temp(tmp_path, monkeypatch):
    target = tmp_path / "w.txt"
    target.write_text("old\n")
    monkeypatch.setattr(atomic.os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        atomic.write_text(target, "new\n")
    assert target.read_text() == "old\n" and [p.name for p in tmp_path.iterdir()] == ["w.txt"]


def test_excluding_a_ticker_is_atomic_and_keeps_the_others(tmp_path, monkeypatch):
    path = tmp_path / "excluded.txt"
    path.write_text("AAA\n")
    replaced = []
    real = os.replace
    monkeypatch.setattr(atomic.os, "replace", lambda a, b: (replaced.append(b), real(a, b)))
    assert holdings.exclude("bbb", path) == {"AAA", "BBB"}
    assert replaced and path.read_text().split() == ["AAA", "BBB"]
    assert holdings.exclude("BBB", path) == {"AAA", "BBB"} and path.read_text().split() == ["AAA", "BBB"]
    with pytest.raises(ValueError):
        holdings.exclude("no way", path)


def test_toggling_a_star_is_atomic_and_keeps_comments(tmp_path, monkeypatch):
    path = tmp_path / "watchlist.txt"
    path.write_text("# my list\nAAA\n")
    monkeypatch.setattr(scan, "WATCHLIST", path)
    replaced = []
    real = os.replace
    monkeypatch.setattr(atomic.os, "replace", lambda a, b: (replaced.append(b), real(a, b)))
    assert server.toggle_watch("BBB") is True and path.read_text().split("\n")[:3] == ["# my list", "AAA", "BBB"]
    assert server.toggle_watch("AAA") is False and "AAA" not in path.read_text().split() and len(replaced) == 2


@pytest.mark.parametrize("host,ok", [
    ("127.0.0.1:8765", True), ("localhost:8765", True), ("127.0.0.1:9999", False), ("127.0.0.1", False),
    ("127.0.0.1:8765.evil.com", False), ("localhost:8765@evil.com", False), ("127.0.0.1.evil.com:8765", False),
    ("evil.com:8765", False), ("", False), ("127.0.0.1:08765x", False), ("127.0.0.1:8765:8765", False),
    ("LOCALHOST:8765", True), ("[::1]:8765", False)])
def test_host_check_is_an_exact_host_and_port_match(host, ok):
    assert routes.host_ok(host, 8765) is ok


class FakeChild:
    def __init__(self, alive):
        self.alive = alive

    def poll(self):
        return None if self.alive else 0


@pytest.fixture
def scanning(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.setattr(scan, "read_status", lambda: {"state": "idle"})
    monkeypatch.setattr(scan, "write_status", lambda **kw: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a) or FakeChild(True))
    monkeypatch.setattr(server, "_scan_child", [])
    return started


def test_run_does_not_start_a_second_scan_while_the_tracked_child_lives(scanning):
    server._scan_child.append(FakeChild(True))
    assert server.start_scan() is False and scanning == []


def test_run_prunes_finished_children_then_starts(scanning):
    server._scan_child.extend([FakeChild(False), FakeChild(False)])
    assert server.start_scan() is True and len(scanning) == 1
    assert len(server._scan_child) == 1 and server._scan_child[0].alive


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setattr(server, "PREFS", tmp_path_factory.mktemp("prefs") / "prefs.json")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    patch.undo()


def post(port, path, body=b"{}", token=True, host=None, length=None):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    conn.putheader("Content-Length", str(len(body) if length is None else length))
    if token:
        conn.putheader("X-Skew-Token", server.TOKEN)
    conn.endheaders(body)
    reply = conn.getresponse()
    out = (reply.status, reply.read())
    conn.close()
    return out


ALL_POSTS = sorted(set(routes.ROUTES) | set(routes.money_ctx.POSTS))


def test_every_post_endpoint_is_routed():
    assert ALL_POSTS == ["/accept", "/amounts", "/ask", "/exclude", "/goal", "/holdings", "/include", "/milestones", "/money", "/plan", "/run",
                         "/settings", "/targets", "/theme", "/watch"]


@pytest.mark.parametrize("path", ALL_POSTS)
def test_every_endpoint_needs_the_token(live, path):
    assert post(live, path, token=False)[0] == 403


@pytest.mark.parametrize("path", ALL_POSTS)
def test_every_endpoint_needs_the_exact_host_and_port(live, path):
    assert post(live, path, host="evil.com:%d" % live)[0] == 403
    assert post(live, path, host="127.0.0.1:1")[0] == 403
    assert post(live, path, host=f"127.0.0.1:{live}.evil.com")[0] == 403


@pytest.mark.parametrize("path", ALL_POSTS)
def test_every_endpoint_has_a_body_size_limit_and_rejects_bad_json(live, path):
    big = b'{"x":"' + b"a" * server.MAX_BODY + b'"}'
    assert post(live, path, body=big)[0] == 413
    assert post(live, path, body=b"{}", length=-5)[0] == 413
    assert post(live, path, body=b"not json")[0] == 400
    assert post(live, path, body=b"[1]")[0] == 400


def test_unknown_paths_are_404_and_a_good_post_still_works(live):
    assert post(live, "/nope")[0] == 404
    code, body = post(live, "/theme", body=b'{"theme":"dark"}')
    assert code == 200 and b"dark" in body and "dark" in server.PREFS.read_text()
    assert post(live, "/watch", body=b'{"symbol":"no way"}')[0] == 400
    assert post(live, "/milestones", body=b'{"milestones":"x"}')[0] == 400


def test_get_pages_also_check_the_host(live):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", live, timeout=5)
    conn.putrequest("GET", "/status", skip_host=True)
    conn.putheader("Host", f"localhost:{live + 1}")
    conn.endheaders()
    assert conn.getresponse().status == 421
