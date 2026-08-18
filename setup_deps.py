"""
Fetching the libraries.

The installer ships a small Python runtime and the app, but not the libraries -
they are several hundred megabytes and would make the download painful.

Normally this runs inside the installer, hidden, with the wizard showing
progress. Run it directly to repair a broken install; pass --quiet to keep it
silent and report through a dialog instead of the console.
"""

import subprocess
import sys

PACKAGES = ["PySide6", "mediapipe", "opencv-python", "pyautogui"]

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


def missing() -> list:
    """Which packages are not importable."""
    checks = {
        "PySide6": "PySide6",
        "mediapipe": "mediapipe",
        "opencv-python": "cv2",
        "pyautogui": "pyautogui",
    }
    out = []
    for package, module in checks.items():
        try:
            __import__(module)
        except ImportError:
            out.append(package)
    return out


def install(packages) -> bool:
    print("Downloading %d package(s). This takes a few minutes the first time." % len(packages))
    print("Around 400 MB in total.")
    print()

    # --no-cache-dir on purpose. The shared pip cache is often left owned by an
    # elevated process from some earlier admin install, and then an ordinary
    # user cannot write to it - which fails with a permission error that has
    # nothing to do with where we are actually installing.
    base = [
        sys.executable, "-m", "pip", "install",
        "--no-warn-script-location",
        "--no-cache-dir",
        "--disable-pip-version-check",
    ]

    try:
        result = subprocess.run(base + list(packages))
    except Exception as exc:
        print("Could not start pip: %s" % exc)
        return False

    if result.returncode == 0:
        return True

    # Second attempt into the user's own site-packages, in case the program
    # folder itself is not writable
    print()
    print("That did not work. Trying again into your user folder...")
    try:
        result = subprocess.run(base + ["--user"] + list(packages))
    except Exception as exc:
        print("Could not start pip: %s" % exc)
        return False

    if result.returncode != 0:
        print()
        print("Something went wrong during the download.")
        print("Check your internet connection, then run Repair AirControl again.")
        return False
    return True


def fetch_model() -> bool:
    from pathlib import Path
    import urllib.request

    target = Path(__file__).resolve().with_name("hand_landmarker.task")
    if target.exists() and target.stat().st_size > 1000:
        return True

    print("Fetching the hand model...")
    try:
        urllib.request.urlretrieve(MODEL_URL, target)
        return True
    except Exception as exc:
        print("Could not fetch the hand model: %s" % exc)
        return False


def alert(text: str, title: str = "AirControl", icon: int = 0x40) -> None:
    """A native dialog. Works before any library is installed."""
    if sys.platform != "win32":
        print(text)
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, icon)
    except Exception:
        print(text)


def main() -> int:
    quiet = "--quiet" in sys.argv

    if not quiet:
        print("AirControl setup")
        print("=" * 40)
        print()

    need = missing()
    if need:
        if not install(need) or missing():
            message = (
                "The libraries could not be downloaded.\n\n"
                "Check your internet connection, then run "
                "Repair AirControl from the Start Menu."
            )
            if quiet:
                alert(message, icon=0x10)      # error icon
            else:
                print()
                print(message)
                input("Press Enter to close.")
            return 1
    elif not quiet:
        print("Libraries are already in place.")

    fetch_model()

    if quiet:
        return 0

    print()
    print("Ready.")
    alert("AirControl is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
