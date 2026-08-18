"""
What a gesture does when it fires.

Actions are written as plain strings so they can live in gestures.json:

    key:space              press one key
    hotkey:win+d           press a combination
    text:hello             type something
    run:notepad.exe        start a program
    none                   do nothing (useful while testing)

Some ready-made ones are listed in PRESETS.
"""

import shlex
import subprocess
import sys

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    HAVE_PYAUTOGUI = True
except Exception:                                   # not installed, or no display
    HAVE_PYAUTOGUI = False


# Handy things to bind, shown in the recorder
PRESETS = {
    "desktop":      "hotkey:win+d",
    "task view":    "hotkey:win+tab",
    "switch app":   "hotkey:alt+tab",
    "play/pause":   "key:playpause",
    "next track":   "key:nexttrack",
    "prev track":   "key:prevtrack",
    "volume up":    "key:volumeup",
    "volume down":  "key:volumedown",
    "mute":         "key:volumemute",
    "close window": "hotkey:alt+f4",
    "screenshot":   "hotkey:win+shift+s",
    "lock":         "run:rundll32.exe user32.dll,LockWorkStation",
}


def describe(action: str) -> str:
    """A readable name for an action string."""
    if not action or action == "none":
        return "nothing"
    for label, value in PRESETS.items():
        if value == action:
            return label
    return action


def run(action: str) -> bool:
    """
    Perform an action. Returns True if something happened.

    Failures are reported rather than raised - one bad binding should not stop
    the whole program.
    """
    if not action or action == "none":
        return False

    kind, _, arg = action.partition(":")
    kind = kind.strip().lower()
    arg = arg.strip()

    if kind == "run":
        try:
            subprocess.Popen(shlex.split(arg))
            return True
        except Exception as exc:
            print("Could not run %r: %s" % (arg, exc), file=sys.stderr)
            return False

    if not HAVE_PYAUTOGUI:
        print("pyautogui is not installed, so %r did nothing." % action, file=sys.stderr)
        print("Install it with: pip install pyautogui", file=sys.stderr)
        return False

    try:
        if kind == "key":
            pyautogui.press(arg)
        elif kind == "hotkey":
            pyautogui.hotkey(*[k.strip() for k in arg.split("+") if k.strip()])
        elif kind == "text":
            pyautogui.write(arg)
        else:
            print("Unknown action kind: %r" % kind, file=sys.stderr)
            return False
        return True
    except Exception as exc:
        print("Action %r failed: %s" % (action, exc), file=sys.stderr)
        return False
