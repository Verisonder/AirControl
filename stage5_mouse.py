"""
Stage 5 - move the mouse with your hand, using poses you recorded yourself.

Record two gestures first, in stage3_record.py:

  one bound to "move cursor"   the cursor follows this hand while you hold it
  one bound to "left click"    the left button is down while you hold it

Optionally a third bound to "right click".

Holding the click pose briefly is a click. Holding it while you move is a drag.

The cursor follows the middle knuckle rather than a fingertip, because that
point barely shifts as the hand changes shape - a fingertip would drag the
cursor sideways every time you clicked.

Only the middle of the frame is used, so a small hand movement covers the whole
screen. The box is drawn on the preview.

Keys
  P       pause (button released, nothing tracked)
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
except ImportError:
    print("pyautogui is needed for this. Install it with:", file=sys.stderr)
    print("    pip install pyautogui", file=sys.stderr)
    raise SystemExit(1)

PALM = 9        # middle finger knuckle - steady whether the hand is open or shut


class Pointer:
    """Turns a hand position into a smoothed screen position."""

    def __init__(self, margin: float = 0.33, smoothing: float = 0.35):
        self.w, self.h = pyautogui.size()
        self.margin = margin
        self.smoothing = smoothing
        self.x = self.w / 2
        self.y = self.h / 2
        self.have_fix = False

    def update(self, nx: float, ny: float):
        span = 1.0 - 2 * self.margin
        fx = (nx - self.margin) / span
        fy = (ny - self.margin) / span
        tx = min(max(fx, 0.0), 1.0) * self.w
        ty = min(max(fy, 0.0), 1.0) * self.h

        if not self.have_fix:
            self.x, self.y = tx, ty          # jump on first sight, do not slide
            self.have_fix = True
        else:
            self.x += (tx - self.x) * self.smoothing
            self.y += (ty - self.y) * self.smoothing

        return int(self.x), int(self.y)

    def lost(self) -> None:
        self.have_fix = False


def main() -> int:
    ap = argparse.ArgumentParser(description="Mouse control from recorded poses")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--margin", type=float, default=0.33,
                    help="fraction of the frame ignored at each edge (bigger = smaller box)")
    ap.add_argument("--smoothing", type=float, default=0.35,
                    help="0 to 1, lower is steadier but laggier")
    ap.add_argument("--tolerance", type=float, default=gestures.DEFAULT_TOLERANCE)
    ap.add_argument("--frames", type=int, default=3,
                    help="frames a pose must hold before the button changes")
    ap.add_argument("--dry-run", action="store_true", help="show it working without touching the mouse")
    args = ap.parse_args()

    lib = gestures.Library()
    bound = {g.get("action") for g in lib.items}

    if "mouse:move" not in bound:
        print("No gesture is bound to 'move cursor' yet.")
        print()
        print("Record one first:")
        print("    python stage3_record.py")
        print("Hold the pose, press SPACE, name it, then choose 'move cursor'.")
        print("Record a second one for 'left click' while you are there.")
        return 1

    if "mouse:left" not in bound:
        print("Note: nothing is bound to 'left click', so you can move but not click.")

    names = {a: next(g["name"] for g in lib.items if g.get("action") == a)
             for a in actions.MOUSE_ACTIONS if a in bound}
    print("Using:")
    for action, name in names.items():
        print("  %-12s %s" % (actions.describe(action), name))
    print("P pauses, Esc quits.")
    if args.dry_run:
        print("Dry run - the mouse will not actually move.")

    cam = H.open_camera(args.camera)
    pointer = Pointer(args.margin, args.smoothing)
    fps = H.Fps()
    started = time.time()

    paused = False
    held_button = None          # "left", "right" or None
    down_since = 0.0
    want = None                 # what this frame is asking for
    streak = 0
    last_event, event_until = "", 0.0

    def release():
        nonlocal held_button
        if held_button:
            if not args.dry_run:
                pyautogui.mouseUp(button=held_button)
            held_button = None

    with H.make_landmarker(1) as landmarker:
        try:
            while True:
                ok, frame = cam.read()
                if not ok:
                    break

                if not args.no_mirror:
                    frame = cv2.flip(frame, 1)

                h, w = frame.shape[:2]
                stamp = int((time.time() - started) * 1000)
                result = landmarker.detect_for_video(H.to_image(frame), stamp)

                lines = ["fps %.0f" % fps.tick()]
                seen_action, lm = None, None

                if result.hand_landmarks:
                    lm = result.hand_landmarks[0]
                    H.draw_hand(frame, lm)

                    side = "Right"
                    if result.handedness and result.handedness[0]:
                        side = result.handedness[0][0].category_name

                    hit, dist = lib.match(lm, side, args.tolerance)
                    if hit and hit.get("action") in actions.MOUSE_ACTIONS:
                        seen_action = hit["action"]
                        lines.append("%s  (%.2f)" % (hit["name"], dist))
                    elif hit:
                        lines.append("%s - not a mouse pose" % hit["name"])
                    else:
                        lines.append("no match  (nearest %.2f)" % dist)

                if paused:
                    release()
                    pointer.lost()
                    lines.append("PAUSED - press P")

                elif lm is None:
                    # Hand gone: let go rather than leaving the button stuck down
                    release()
                    pointer.lost()
                    want, streak = None, 0
                    lines.append("no hand")

                else:
                    # A few frames of agreement before changing the button,
                    # so a half-formed pose does not click by itself
                    if seen_action == want:
                        streak += 1
                    else:
                        want, streak = seen_action, 1

                    if streak >= args.frames:
                        target = {"mouse:left": "left", "mouse:right": "right"}.get(want)

                        if target != held_button:
                            release()
                            if target:
                                held_button = target
                                down_since = time.time()
                                if not args.dry_run:
                                    pyautogui.mouseDown(button=target)
                                last_event, event_until = "%s down" % target, time.time() + 0.8
                            elif last_event.endswith("down"):
                                held = time.time() - down_since
                                last_event = "click" if held < 0.4 else "drag %.1fs" % held
                                event_until = time.time() + 0.8

                    # Any recognised mouse pose moves the cursor, so a drag
                    # does not freeze the moment the button goes down
                    if seen_action:
                        sx, sy = pointer.update(lm[PALM].x, lm[PALM].y)
                        if not args.dry_run:
                            pyautogui.moveTo(sx, sy, _pause=False)
                        lines.append("cursor %d, %d%s"
                                     % (sx, sy, "   %s down" % held_button if held_button else ""))
                    else:
                        pointer.lost()

                    px, py = int(lm[PALM].x * w), int(lm[PALM].y * h)
                    cv2.circle(frame, (px, py), 12,
                               (0, 0, 255) if held_button else (255, 200, 0), 2)

                if time.time() < event_until:
                    lines.append(last_event)

                m = args.margin
                cv2.rectangle(
                    frame,
                    (int(m * w), int(m * h)),
                    (int((1 - m) * w), int((1 - m) * h)),
                    (90, 90, 90), 1,
                )

                H.draw_text(frame, lines, colour=(0, 200, 255) if paused else (0, 255, 0))
                cv2.imshow("AirControl - mouse", frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key in (ord("p"), ord("P")):
                    paused = not paused
                    if paused:
                        release()
                    print("Paused." if paused else "Resumed.")
        finally:
            release()
            cam.release()
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
