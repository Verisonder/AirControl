"""
Starting with Windows.

Uses the per-user Run key rather than a shortcut in the Startup folder. Both
work; the registry entry is easier to read back reliably, which matters because
the checkbox has to show the real state rather than what we last wrote.

No administrator rights are needed - HKEY_CURRENT_USER only.
"""

import sys
from pathlib import Path

NAME = "AirControl"
KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

try:
    import winreg
    SUPPORTED = sys.platform == "win32"
except ImportError:
    SUPPORTED = False


def command() -> str:
    """
    The command Windows should run at login.

    Prefers pythonw.exe so no console flashes up, and launch.py so the
    dependency check still happens. Falls back to whatever is running now when
    those are not beside us, which is the case in a source checkout.
    """
    here = Path(__file__).resolve().parent
    exe = Path(sys.executable)

    pythonw = exe.with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = exe

    script = here / "launch.py"
    if not script.exists():
        script = here / "gui.py"

    return '"%s" "%s"' % (pythonw, script)


def enabled() -> bool:
    if not SUPPORTED:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            value, _ = winreg.QueryValueEx(key, NAME)
            return bool(value)
    except OSError:
        return False


def enable() -> bool:
    if not SUPPORTED:
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        return True
    except OSError:
        return False


def disable() -> bool:
    if not SUPPORTED:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, NAME)
        return True
    except FileNotFoundError:
        return True                    # already gone, which is what was wanted
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    return enable() if on else disable()
