"""
Launcher.

Checks the libraries are present before starting the window. A missing import
under pythonw fails silently and just looks like the app is broken, so anything
wrong is reported in a dialog instead.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    sys.path.insert(0, str(HERE))

    import setup_deps

    if setup_deps.missing():
        # The installer normally does this. Getting here means it was skipped
        # or it failed, so try once more quietly before giving up.
        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        setup_deps.alert(
            "AirControl needs to finish setting up.\n\n"
            "The libraries will download now - around 400 MB. "
            "This window will close and AirControl opens when it is done."
        )

        result = subprocess.run(
            [sys.executable, str(HERE / "setup_deps.py"), "--quiet"],
            creationflags=flags,
        )
        if result.returncode != 0 or setup_deps.missing():
            return 1

    from gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
