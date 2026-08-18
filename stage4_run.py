"""
Stage 4 - gestures actually do things.

Watches for the gestures you recorded and runs what they are bound to.

Two rules keep it usable rather than maddening:

  hold     the same gesture must be seen for several frames before it fires,
           so a flicker while your hand moves does not trigger anything
  cooldown after firing, nothing fires again for a moment, so one gesture does
           not repeat twenty times while you hold it

Press P to pause everything without quitting.

Keys
  P       pause / resume
  Esc/q   quit
"""

import argparse
import time

import cv2

import actions
import gestures
import hands as H


class Trigger:
    """Fires once a gesture has been held, then waits before firing again."""

    def __init__(self, hold: int = 8, cooldown: float = 1.2):
        self.hold = hold
        self.cooldown = cooldown
        self._current = None
        self._count = 0
        self._last_fire = 0.0

    def update(self, name):
        """Feed the gesture seen this frame (or None). Returns a name to fire."""
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
        if self._current is None:
            return 0.0
        return min(self._count / self.hold, 1.0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run gestures")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hands", type=int, default=2)
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--tolerance", type=float, default=gestures.DEFAULT_TOLERANCE)
    ap.add_argument("--hold", type=int, default=8, help="frames a gesture must be held")
    ap.add_argument("--cooldown", type=float, default=1.2, help="seconds between firings")
    ap.add_argument("--dry-run", action="store_true", help="show what would fire, do nothing")
    args = ap.parse_args()

    lib = gestures.Library()
    if not len(lib):
        print("No gestures saved yet. Record some first:")
        print("    python stage3_record.py")
        return 1

    print("Watching for %d gesture(s). P pauses, Esc quits." % len(lib))
    if args.dry_run:
        print("Dry run - nothing will actually be pressed.")

    cam = H.open_camera(args.camera)
    fps = H.Fps()
    trigger = Trigger(args.hold, args.cooldown)
    started = time.time()
    paused = False
    flash_until, flash_text = 0.0, ""

    with H.make_landmarker(args.hands) as landmarker:
        try:
            while True:
                ok, frame = cam.read()
                if not ok:
                    break

                if not args.no_mirror:
                    frame = cv2.flip(frame, 1)

                stamp = int((time.time() - started) * 1000)
                result = landmarker.detect_for_video(H.to_image(frame), stamp)

                seen = None
                for i, lm in enumerate(result.hand_landmarks):
                    H.draw_hand(frame, lm)

                    side = H.handedness_of(result, i, not args.no_mirror)

                    hit, _ = lib.match(lm, side, args.tolerance)
                    if hit and seen is None:
                        seen = hit["name"]

                if not paused:
                    fired = trigger.update(seen)
                    if fired:
                        item = next(g for g in lib.items if g["name"] == fired)
                        action = item.get("action", "")
                        label = actions.describe(action)
                        if args.dry_run:
                            print("would fire: %s -> %s" % (fired, label))
                        else:
                            actions.run(action)
                            print("fired: %s -> %s" % (fired, label))
                        flash_text = "%s  ->  %s" % (fired, label)
                        flash_until = time.time() + 1.2

                status = "PAUSED" if paused else ("holding %s" % seen if seen else "watching")
                lines = ["fps %.0f    %s" % (fps.tick(), status)]

                if seen and not paused:
                    bar = int(trigger.progress * 20)
                    lines.append("[" + "#" * bar + "." * (20 - bar) + "]")

                if time.time() < flash_until:
                    lines.append(flash_text)

                H.draw_text(frame, lines, colour=(0, 200, 255) if paused else (0, 255, 0))
                cv2.imshow("AirControl", frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key in (ord("p"), ord("P")):
                    paused = not paused
                    print("Paused." if paused else "Resumed.")
        finally:
            cam.release()
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
