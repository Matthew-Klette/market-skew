"""Market Skew on Windows: the dashboard in its own window, opened from the Start menu or desktop shortcut.

The same rules as the Mac app: it scans on open when the last report is stale, nothing runs in the background, and
closing the window stops the scan. The window is Microsoft Edge (built into Windows 10 and 11) in app mode with its own
profile, so it is a plain window with no tabs or address bar and shares nothing with your normal browser.
Without Edge it tries Chrome, and without either it opens your default browser plus a small "close to stop" window."""
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import system

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "data" / "app.lock"
LOG = ROOT / "data" / "logs" / "app.log"
TITLE = "Market Skew"


def window_profile() -> Path:
    return system.app_support() / "window"


def browser_candidates(env: dict | None = None) -> list[Path]:
    """Edge first (every Windows 10/11 PC has it), then Chrome, in their usual install folders."""
    env = os.environ if env is None else env
    roots = [env.get(key) for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    roots = [Path(root) for root in roots if root]
    edge = [root / "Microsoft" / "Edge" / "Application" / "msedge.exe" for root in roots]
    chrome = [root / "Google" / "Chrome" / "Application" / "chrome.exe" for root in roots]
    return edge + chrome


def find_browser(env: dict | None = None) -> str | None:
    for candidate in browser_candidates(env):
        if candidate.is_file():
            return str(candidate)
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def window_command(browser: str, url: str, profile: Path) -> list[str]:
    """App mode with a private profile: one window, no tabs, and the process ends when the window closes."""
    return [browser, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1440,900", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--disable-sync", "--disable-background-mode"]


def window_open(profile: Path) -> bool:
    """Edge holds `lockfile` in its profile folder while any of its windows is open; it can't be removed until Edge exits."""
    lock = profile / "lockfile"
    if not lock.exists():
        return False
    try:
        lock.unlink()
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def wait_for_window(browser: str, url: str, profile: Path, sleep=None) -> None:
    """Open the window and return once it is closed. If Edge hands the window to a copy of itself that is already running
    on this profile, the launched process exits at once, so the profile lock is what says the window is still open."""
    import time
    sleep = sleep or time.sleep
    subprocess.run(window_command(browser, url, profile))
    while window_open(profile):
        sleep(2)


def take_lock() -> bool:
    """One copy at a time. False when another Market Skew window is already open."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            alive = system.pid_alive(int(LOCK.read_text().strip() or "0"))
        except (OSError, ValueError):
            alive = False
        if alive:
            return False
        LOCK.unlink(missing_ok=True)  # left over from a window that crashed
        return take_lock()
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def _notice(message: str) -> None:
    """A Windows message box (the launcher has no console to print to)."""
    if system.IS_WINDOWS:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x40)


def _fallback_window(url: str) -> None:
    """No Edge or Chrome: open the default browser and keep a small window whose closing stops the app."""
    webbrowser.open(url)
    try:
        import tkinter as tk
    except ImportError:
        threading.Event().wait()  # no way to show a window; runs until signed out
        return
    root = tk.Tk()
    root.title(TITLE)
    root.geometry("420x140")
    tk.Label(root, text="Market Skew is open in your browser.\nClose this window to stop it.", pady=20).pack()
    tk.Button(root, text="Open it again", command=lambda: webbrowser.open(url)).pack()
    root.mainloop()


def _send_output_to_log() -> None:
    """pythonw has no console, so stdout/stderr are None; the server writes there, so point them at a log file."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stream = open(LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


def run() -> int:
    if not system.IS_WINDOWS:
        print("`skew app` is the Windows window. On a Mac, open Market Skew.app (./install.sh builds it).")
        return 2
    _send_output_to_log()
    if not take_lock():
        _notice("Market Skew is already open. Look for its window on the taskbar.")
        return 0
    try:
        from .ui import server
    except Exception:
        LOCK.unlink(missing_ok=True)
        raise
    httpd = None
    try:
        httpd, url = server.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            server._scan_if_stale()
        except Exception as error:  # the dashboard still opens; the scan can be started from the page
            print(f"Scan on open skipped: {error}", file=sys.stderr)
        browser = find_browser()
        if browser:
            profile = window_profile()
            profile.mkdir(parents=True, exist_ok=True)
            wait_for_window(browser, url, profile)
        else:
            _fallback_window(url)
    finally:
        server.stop_scan()
        if httpd is not None:
            httpd.shutdown()
        LOCK.unlink(missing_ok=True)
    return 0

