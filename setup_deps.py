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


def log_path():
    """Where the download log goes, somewhere always writable."""
    from pathlib import Path
    import os
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    folder = base / "AirControl"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "setup.log"


def pip_exe() -> str:
    """
    Always drive pip with python.exe, never pythonw.exe.

    Under pythonw there is no console, so the standard handles are invalid.
    pip writes to them as it works and falls over immediately, which looks like
    a download failure but is nothing of the sort.
    """
    from pathlib import Path
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.exists():
            return str(console)
    return sys.executable


LAST_ERROR = ""


def _run_pip(args, log) -> int:
    """Run pip, sending everything to the log file rather than nowhere."""
    global LAST_ERROR
    try:
        result = subprocess.run(
            args,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
        return result.returncode
    except Exception as exc:
        LAST_ERROR = str(exc)
        log.write("\ncould not start pip: %s\n" % exc)
        return 1


def install(packages) -> bool:
    global LAST_ERROR

    print("Downloading %d package(s). This takes a few minutes the first time." % len(packages))
    print("Around 400 MB in total.")
    print()

    # --no-cache-dir on purpose. The shared pip cache is often left owned by an
    # elevated process from some earlier admin install, and then an ordinary
    # user cannot write to it - which fails with a permission error that has
    # nothing to do with where we are actually installing.
    base = [
        pip_exe(), "-m", "pip", "install",
        "--no-warn-script-location",
        "--no-cache-dir",
        "--disable-pip-version-check",
    ]

    path = log_path()
    with open(path, "w", encoding="utf-8", errors="replace") as log:
        log.write("python: %s\n" % sys.executable)
        log.write("pip via: %s\n" % pip_exe())
        log.write("packages: %s\n\n" % ", ".join(packages))
        log.flush()

        code = _run_pip(base + list(packages), log)

        if code != 0:
            # Second attempt into the user's own site-packages, in case the
            # program folder itself is not writable
            log.write("\n--- retrying with --user ---\n")
            log.flush()
            code = _run_pip(base + ["--user"] + list(packages), log)

    if code != 0 and not LAST_ERROR:
        try:
            tail = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            LAST_ERROR = "\n".join(tail[-6:])
        except OSError:
            LAST_ERROR = "See %s" % path

    return code == 0


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
                "Setup could not finish.\n\n"
                "%s\n\n"
                "Full details: %s"
            ) % (LAST_ERROR or "pip did not report a reason.", log_path())
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
