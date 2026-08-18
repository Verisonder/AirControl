"""
AirControl - hand gestures that do things.

One program. Gestures bound to keys fire once when held; gestures bound to the
mouse work continuously while you hold the pose. Both at the same time, so you
can move the cursor with one hand and fire a shortcut with the other.

Record poses first:

    python record.py

Keys
  P       pause everything (button released, nothing fires)
  L       list what is loaded
  R       reload gestures.json without restarting
  Esc/q   quit
"""

import argparse
import sys
import time

import cv2

import actions
import gestures
import hands as H

try:
    import pyautogui
    pyautogui.FAILSAFE = False      # we have our own pause and quit
    pyautogui.PAUSE = 0
    HAVE_MOUSE = True
except ImportError:
    HAVE_MOUSE = False

PALM = 9        # middle knuckle - barely shifts as the hand changes shape


class Trigger:
    """Fires a gesture once it has been held, then waits before firing again."""

    def __init__(self, hold: int = 8, cooldown: float = 1.2):
        self.hold = hold
        self.cooldown = cooldown
        self._current = None
        self._count = 0
        self._last_fire = 0.0

    def update(self, name):
        if name != self._current:
            self._current, self._count = name, 1
            return None

        self._count += 1
        if name is None or self._count != self.hold:
            return None
        if time.time() - self._last_fire < self.cooldown:
            return None

        self._last_fire = time.time()
        return name

    @property
    def progress(self) -> float:
        return 0.0 if self._current is None else min(self._count / self.hold, 1.0)


class Mouse:
    """Cursor and buttons, driven by a held pose."""

    def __init__(self, margin: float, smoothing: float, frames: int, dry: bool):
        self.margin = margin
        self.smoothing = smoothing
        self.frames = frames
        self.dry = dry
        self.w, self.h = pyautogui.size() if HAVE_MOUSE else (1920, 1080)
        self.x, self.y = self.w / 2, self.h / 2
        self.have_fix = False
        self.button = None
        self.down_since = 0.0
        self._want = None
        self._streak = 0
        self.event = ""

    def move_to(self, nx: float, ny: float):
        """Feed a normalised hand position. Returns screen pixels."""
        span = 1.0 - 2 * self.margin
        tx = min(max((nx - self.margin) / span, 0.0), 1.0) * self.w
        ty = min(max((ny - self.margin) / span, 0.0), 1.0) * self.h

        if not self.have_fix:
            self.x, self.y = tx, ty        # jump on first sight, do not slide across
            self.have_fix = True
        else:
            self.x += (tx - self.x) * self.smoothing
            self.y += (ty - self.y) * self.smoothing

        if not self.dry and HAVE_MOUSE:
            pyautogui.moveTo(int(self.x), int(self.y), _pause=False)
        return int(self.x), int(self.y)

    def release(self) -> None:
        if self.button:
            if not self.dry and HAVE_MOUSE:
                pyautogui.mouseUp(button=self.button)
            self.button = None

    def lost(self) -> None:
        self.release()
        self.have_fix = False
        self._want, self._streak = None, 0

    def hold(self, action) -> None:
        """Feed the mouse action seen this frame, or None."""
        if action == self._want:
            self._streak += 1
        else:
            self._want, self._streak = action, 1

        if self._streak < self.frames:
            return

        target = {"mouse:left": "left", "mouse:right": "right"}.get(action)
        if target == self.button:
            return

        was = self.button
        self.release()
        if target:
            self.button = target
            self.down_since = time.time()
            if not self.dry and HAVE_MOUSE:
                pyautogui.mouseDown(button=target)
            self.event = "%s down" % target
        elif was:
            held = time.time() - self.down_since
            self.event = "click" if held < 0.4 else "drag %.1fs" % held


def summarise(lib) -> None:
    print()
    if not len(lib):
        print("Nothing recorded yet. Run: python record.py")
        return
    print("Loaded %d gesture(s):" % len(lib))
    for g in lib.items:
        print("  %-16s hand=%-5s does=%s"
              % (g["name"], g.get("hand", "any"), actions.describe(g.get("action", ""))))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="AirControl")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hands", type=int, default=2)
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--tolerance", type=float, default=gestures.DEFAULT_TOLERANCE,
                    help="how close a pose must match (lower is stricter)")
    ap.add_argument("--hold", type=int, default=8,
                    help="frames a key gesture must be held before firing")
    ap.add_argument("--cooldown", type=float, default=1.2,
                    help="seconds before the same gesture can fire again")
    ap.add_argument("--margin", type=float, default=0.33,
                    help="fraction of the frame ignored at each edge (bigger = smaller box)")
    ap.add_argument("--smoothing", type=float, default=0.35,
                    help="cursor smoothing, 0 to 1, lower is steadier but laggier")
    ap.add_argument("--frames", type=int, default=3,
                    help="frames a mouse pose must hold before the button changes")
    ap.add_argument("--dry-run", action="store_true", help="report only, press nothing")
    args = ap.parse_args()

    lib = gestures.Library()
    if not len(lib):
        print("No gestures recorded yet.")
        print("    python record.py")
        return 1

    summarise(lib)

    has_mouse = any(g.get("action") in actions.MOUSE_ACTIONS for g in lib.items)
    if has_mouse and not HAVE_MOUSE:
        print("Mouse gestures are recorded but pyautogui is missing.", file=sys.stderr)
        print("    pip install pyautogui", file=sys.stderr)
        return 1

    print("P pause   L list   R reload   Esc quit")
    if args.dry_run:
        print("Dry run - nothing will actually be pressed.")

    cam = H.open_camera(args.camera)
    fps = H.Fps()
    trigger = Trigger(args.hold, args.cooldown)
    mouse = Mouse(args.margin, args.smoothing, args.frames, args.dry_run)
    started = time.time()

    paused = False
    flash, flash_until = "", 0.0
    mirrored = not args.no_mirror

    with H.make_landmarker(args.hands) as landmarker:
        try:
            while True:
                ok, frame = cam.read()
                if not ok:
                    break

                if mirrored:
                    frame = cv2.flip(frame, 1)

                h, w = frame.shape[:2]
                stamp = int((time.time() - started) * 1000)
                result = landmarker.detect_for_video(H.to_image(frame), stamp)

                lines = ["fps %.0f" % fps.tick()]
                key_gesture = None           # a gesture bound to a key or program
                mouse_action, mouse_lm = None, None

                for i, lm in enumerate(result.hand_landmarks):
                    H.draw_hand(frame, lm)
                    side = H.handedness_of(result, i, mirrored)

                    hit, dist = lib.match(lm, side, args.tolerance)
                    if not hit:
                        lines.append("%s: -" % side)
                        continue

                    action = hit.get("action", "")
                    lines.append("%s: %s (%.2f)" % (side, hit["name"], dist))

                    # One hand can drive the mouse while the other fires shortcuts
                    if action in actions.MOUSE_ACTIONS:
                        if mouse_action is None:
                            mouse_action, mouse_lm = action, lm
                    elif key_gesture is None:
                        key_gesture = hit

                if paused:
                    mouse.lost()
                    lines.append("PAUSED - press P")

                else:
                    # --- mouse ---
                    if mouse_lm is None:
                        # Pose gone: let go rather than leaving a button stuck down
                        mouse.lost()
                    else:
                        mouse.hold(mouse_action)
                        sx, sy = mouse.move_to(mouse_lm[PALM].x, mouse_lm[PALM].y)
                        lines.append("cursor %d, %d%s"
                                     % (sx, sy, "   %s down" % mouse.button if mouse.button else ""))
                        px, py = int(mouse_lm[PALM].x * w), int(mouse_lm[PALM].y * h)
                        cv2.circle(frame, (px, py), 12,
                                   (0, 0, 255) if mouse.button else (255, 200, 0), 2)
                        if mouse.event:
                            flash, flash_until = mouse.event, time.time() + 0.8
                            mouse.event = ""

                    # --- everything else ---
                    fired = trigger.update(key_gesture["name"] if key_gesture else None)
                    if fired:
                        action = key_gesture.get("action", "")
                        label = actions.describe(action)
                        if args.dry_run:
                            print("would fire: %s -> %s" % (fired, label))
                        else:
                            actions.run(action)
                            print("fired: %s -> %s" % (fired, label))
                        flash, flash_until = "%s  ->  %s" % (fired, label), time.time() + 1.2

                    if key_gesture and trigger.progress < 1.0:
                        bar = int(trigger.progress * 20)
                        lines.append("[" + "#" * bar + "." * (20 - bar) + "]")

                if time.time() < flash_until:
                    lines.append(flash)

                if has_mouse:
                    m = args.margin
                    cv2.rectangle(frame, (int(m * w), int(m * h)),
                                  (int((1 - m) * w), int((1 - m) * h)), (90, 90, 90), 1)

                H.draw_text(frame, lines, colour=(0, 200, 255) if paused else (0, 255, 0))
                cv2.imshow("AirControl", frame)

                k = cv2.waitKey(1) & 0xFF
                if k in (27, ord("q")):
                    break
                if k in (ord("p"), ord("P")):
                    paused = not paused
                    if paused:
                        mouse.lost()
                    print("Paused." if paused else "Resumed.")
                if k in (ord("l"), ord("L")):
                    summarise(lib)
                if k in (ord("r"), ord("R")):
                    lib.load()
                    print("Reloaded.")
                    summarise(lib)
        finally:
            mouse.release()
            cam.release()
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
