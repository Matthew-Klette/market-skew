"""The few things that differ between a Mac and a Windows PC: where Python and the predictor live, how to check a process
is still alive, how to start the scan at low priority, and what to call the computer in plain words.
On a Mac every answer here is the one the app has always used."""
import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
DEVICE = "PC" if IS_WINDOWS else "Mac"


def venv_python(venv: Path, windowed: bool = False) -> Path:
    """The Python inside a uv/venv folder. `windowed` picks pythonw.exe on Windows (no console window)."""
    if IS_WINDOWS:
        return venv / "Scripts" / ("pythonw.exe" if windowed else "python.exe")
    return venv / "bin" / "python"


def app_support() -> Path:
    """Per-user folder for large optional downloads (the Google predictor)."""
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "MarketSkew"
    return Path.home() / "Library" / "Application Support" / "MarketSkew"


def python_flags() -> list[str]:
    """Interpreter flags for child Pythons. Windows gets UTF-8 mode, so files and pipes are read as UTF-8 as they are on a Mac."""
    return ["-X", "utf8"] if IS_WINDOWS else []


def pid_alive(pid: int) -> bool:
    """True while process `pid` is running. (On Windows, os.kill(pid, 0) would end the process, so it is never used there.)"""
    if IS_WINDOWS:
        return pid > 0 and _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)  # the check the Mac app has always used
        return True
    except OSError:
        return False


def _windows_pid_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    query_limited, still_active, access_denied = 0x1000, 259, 5
    handle = kernel32.OpenProcess(query_limited, False, pid)
    if not handle:
        return ctypes.get_last_error() == access_denied
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def low_priority() -> dict:
    """Popen keyword arguments that start a child at low priority so the computer stays responsive."""
    if IS_WINDOWS:
        below_normal, no_window = 0x00004000, 0x08000000
        return {"creationflags": below_normal | no_window}
    return {"preexec_fn": lambda: os.nice(10)}


def stop_process(child) -> None:
    """End a child the scan started. On Windows the venv's python.exe is a small launcher that starts the real Python as its
    own child, so the whole tree is ended with taskkill; terminate() alone would leave the scan running."""
    if IS_WINDOWS:
        import subprocess
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, **hidden_window())
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
        return
    import subprocess
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()


def console_python(executable: str) -> str:
    """On Windows the app runs under pythonw.exe; children that pipe output get python.exe from the same folder instead."""
    if IS_WINDOWS and executable.lower().endswith("pythonw.exe"):
        candidate = Path(executable).with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return executable


def hidden_window() -> dict:
    """subprocess keyword arguments that stop a console window flashing up on Windows; nothing on a Mac."""
    return {"creationflags": 0x08000000} if IS_WINDOWS else {}


def windows_base_env() -> dict:
    """The variables a Windows program needs to start at all (Python, node and claude fail without SYSTEMROOT and friends)."""
    keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "USERNAME", "APPDATA", "LOCALAPPDATA",
            "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP",
            "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
    return {key: os.environ[key] for key in keep if key in os.environ}

