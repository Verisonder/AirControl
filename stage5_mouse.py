"""
Stage 5 - move the mouse with your hand.

  open hand      the cursor follows your palm
  close it       the left button goes down
  open again     the button comes back up

So a quick close-and-open is a click, and closing then moving is a drag.

The pointer follows the middle knuckle rather than a fingertip, because that
point barely moves when you make a fist - a fingertip would drag the cursor
sideways every time you tried to click.

Only the middle of the frame is used, so a small hand movement covers the whole
screen and you never have to reach the edge of the camera's view.

Keys
  P       pause (cursor released, nothing tracked)
  Esc/q   quit
"""

import argparse
import sys
import time

import cv2

import hands as H

try:
    import pyautogui
    pyautogui.FAILSAFE = False      # we have our own pause and quit
    pyautogui.PAUSE = 0             # no built-in delay between calls
except ImportError:
    print("pyautogui is needed for this. Install it with:", file=sys.stderr)
    print("    pip install pyautogui", file=sys.stderr)
    raise SystemExit(1)

PALM = 9        # middle finger knuckle - steady whether the hand is open or shut


class Pointer:
    """Turns a hand position into a smoothed screen position."""

    def __init__(self, margin: float = 0.2, smoothing: float = 0.35):
        self.w, self.h = pyautogui.size()
        self.margin = margin            # fraction of the frame ignored at each edge
        self.smoothing = smoothing      # 0 is frozen, 1 is no smoothing at all
        self.x = self.w / 2
        self.y = self.h / 2
        self.have_fix = False

    def update(self, nx: float, ny: float):
        """Feed a normalised hand position (0-1). Returns screen pixels."""
        span = 1.0 - 2 * self.margin

        # Map the active middle of the frame onto the whole screen
        fx = (nx - self.margin) / span
        fy = (ny - self.margin) / span
        tx = min(max(fx, 0.0), 1.0) * self.w
        ty = min(max(fy, 0.0), 1.0) * self.h

        if not self.have_fix:
            # Jump straight there the first time rather than sliding across
            self.x, self.y = tx, ty
            self.have_fix = True
        else:
            self.x += (tx - self.x) * self.smoothing
            self.y += (ty - self.y) * self.smoothing

        return int(self.x), int(self.y)

    def lost(self) -> None:
        self.have_fix = False


def main() -> int:
    ap = argparse.ArgumentParser(description="Mouse control")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--margin", type=float, default=0.2,
                    help="fraction of the frame ignored at each edge (bigger = less hand movement needed)")
    ap.add_argument("--smoothing", type=float, default=0.35,
                    help="0 to 1, lower is steadier but laggier")
    ap.add_argument("--grip", type=int, default=1,
                    help="fingers still up that still counts as a closed hand")
    ap.add_argument("--frames", type=int, default=3,
                    help="frames the hand must stay closed or open before the button changes")
    ap.add_argument("--dry-run", action="store_true", help="show it working without touching the mouse")
    args = ap.parse_args()

    cam = H.open_camera(args.camera)
    pointer = Pointer(args.margin, args.smoothing)
    fps = H.Fps()
    started = time.time()

    paused = False
    button_down = False
    closed_streak = 0
    open_streak = 0
    down_since = 0.0
    last_event = ""
    event_until = 0.0

    print("Mouse control running.")
    print("Open hand moves the cursor, close it to press, open to release.")
    print("P pauses, Esc quits.")
    if args.dry_run:
        print("Dry run - the mouse will not actually move.")

    def release():
        nonlocal button_down
        if button_down:
            if not args.dry_run:
                pyautogui.mouseUp()
            button_down = False

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

                if paused:
                    release()
                    pointer.lost()
                    lines.append("PAUSED - press P")

                elif not result.hand_landmarks:
                    # Hand gone: let go rather than leaving the button stuck down
                    release()
                    pointer.lost()
                    closed_streak = open_streak = 0
                    lines.append("no hand")

                else:
                    lm = result.hand_landmarks[0]
                    H.draw_hand(frame, lm)

                    side = "Right"
                    if result.handedness and result.handedness[0]:
                        side = result.handedness[0][0].category_name

                    up = H.fingers_up(lm, side)
                    closed = sum(up) <= args.grip

                    # A few frames of agreement before changing the button,
                    # so a half-formed fist does not click by itself
                    if closed:
                        closed_streak += 1
                        open_streak = 0
                    else:
                        open_streak += 1
                        closed_streak = 0

                    if closed_streak >= args.frames and not button_down:
                        button_down = True
                        down_since = time.time()
                        if not args.dry_run:
                            pyautogui.mouseDown()
                        last_event, event_until = "press", time.time() + 0.8

                    elif open_streak >= args.frames and button_down:
                        held = time.time() - down_since
                        button_down = False
                        if not args.dry_run:
                            pyautogui.mouseUp()
                        last_event = "click" if held < 0.4 else "drag %.1fs" % held
                        event_until = time.time() + 0.8

                    sx, sy = pointer.update(lm[PALM].x, lm[PALM].y)
                    if not args.dry_run:
                        pyautogui.moveTo(sx, sy, _pause=False)

                    # Mark the point being followed
                    px, py = int(lm[PALM].x * w), int(lm[PALM].y * h)
                    cv2.circle(frame, (px, py), 12, (0, 0, 255) if button_down else (255, 200, 0), 2)

                    lines.append("%s   %s" % (
                        "CLOSED" if closed else "open",
                        "button down" if button_down else "button up",
                    ))
                    lines.append("cursor %d, %d" % (sx, sy))

                if time.time() < event_until:
                    lines.append(last_event)

                # Show the active area - hand movement outside this does nothing
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
