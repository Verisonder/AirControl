"""
Launcher.

Checks the libraries are present before starting the window. If anything is
missing it runs setup first, in a console the user can actually see - a missing
import under pythonw fails silently and looks like the app is broken.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def python_console() -> str:
    """python.exe beside us, so setup output is visible even under pythonw."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.exists():
            return str(console)
    return sys.executable


def main() -> int:
    sys.path.insert(0, str(HERE))

    import setup_deps

    if setup_deps.missing():
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_CONSOLE
        result = subprocess.run(
            [python_console(), str(HERE / "setup_deps.py")],
            creationflags=flags,
        )
        if result.returncode != 0:
            return result.returncode

    from gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
