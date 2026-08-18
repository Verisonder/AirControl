"""
Stage 3 - record your own gestures.

Hold a pose in front of the camera and press SPACE. The shape is captured and
you name it in the terminal, then pick what it should do.

Saved gestures live in gestures.json next to this file. Matching ignores where
your hand is, how far away it is, and how it is tilted - only the shape counts.

Keys
  SPACE   record the pose being held
  L       list what is saved
  D       delete a gesture
  A       change what a gesture does
  Esc/q   quit
"""

import argparse
import time

import cv2

import actions
import gestures
import hands as H


def ask_action() -> str:
    """Prompt for what the gesture should do."""
    print()
    print("What should it do?")
    names = list(actions.PRESETS)
    for i, label in enumerate(names, 1):
        print("  %2d. %-13s %s" % (i, label, actions.PRESETS[label]))
    print("   0. nothing for now")
    print("  or type an action directly, e.g. hotkey:ctrl+shift+n")

    choice = input("> ").strip()
    if not choice or choice == "0":
        return "none"
    if choice.isdigit() and 1 <= int(choice) <= len(names):
        return actions.PRESETS[names[int(choice) - 1]]
    return choice


def record(lib, lm, side) -> None:
    """Capture the held pose and add it to the library."""
    print()
    print("Captured a %s hand." % side.lower())
    name = input("Name it (blank to cancel): ").strip()
    if not name:
        print("Cancelled.")
        return

    print()
    print("Which hand should trigger it?")
    print("  1. either  2. left only  3. right only")
    pick = input("> ").strip()
    hand = {"2": "Left", "3": "Right"}.get(pick, "any")

    action = ask_action()
    lib.add(name, gestures.normalise(lm), action, hand)

    print()
    print("Saved %r  hand=%s  does=%s" % (name, hand, actions.describe(action)))
    print("%d gesture(s) stored." % len(lib))
    print()


def list_all(lib) -> None:
    print()
    if not len(lib):
        print("Nothing saved yet.")
    else:
        print("Saved gestures:")
        for g in lib.items:
            print("  %-16s hand=%-5s does=%s"
                  % (g["name"], g.get("hand", "any"), actions.describe(g.get("action", ""))))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Record gestures")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hands", type=int, default=2)
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--tolerance", type=float, default=gestures.DEFAULT_TOLERANCE,
                    help="how close a match must be (lower is stricter)")
    args = ap.parse_args()

    lib = gestures.Library()
    print("Loaded %d gesture(s)." % len(lib))
    print("SPACE record   L list   D delete   A change action   Esc quit")

    cam = H.open_camera(args.camera)
    fps = H.Fps()
    started = time.time()
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

                lines = ["fps %.0f    saved %d" % (fps.tick(), len(lib))]
                first_lm, first_side = None, "Right"

                for i, lm in enumerate(result.hand_landmarks):
                    H.draw_hand(frame, lm)

                    side = H.handedness_of(result, i, not args.no_mirror)

                    if first_lm is None:
                        first_lm, first_side = lm, side

                    hit, dist = lib.match(lm, side, args.tolerance)
                    if hit:
                        lines.append("%s: %s  (%.2f)" % (side, hit["name"], dist))
                    else:
                        near = "" if dist == float("inf") else "  nearest %.2f" % dist
                        lines.append("%s: -%s" % (side, near))

                if time.time() < flash_until:
                    lines.append(flash_text)

                H.draw_text(frame, lines)
                cv2.imshow("AirControl - record", frame)

                key = cv2.waitKey(1) & 0xFF

                if key in (27, ord("q")):
                    break

                if key == ord(" "):
                    if first_lm is None:
                        flash_text, flash_until = "no hand in view", time.time() + 1.5
                    else:
                        record(lib, first_lm, first_side)
                        flash_text, flash_until = "saved", time.time() + 1.5

                elif key in (ord("l"), ord("L")):
                    list_all(lib)

                elif key in (ord("d"), ord("D")):
                    list_all(lib)
                    name = input("Delete which? ").strip()
                    print("Deleted." if name and lib.remove(name) else "No such gesture.")
                    print()

                elif key in (ord("a"), ord("A")):
                    list_all(lib)
                    name = input("Change which? ").strip()
                    if any(g["name"].lower() == name.lower() for g in lib.items):
                        lib.set_action(name, ask_action())
                        print("Updated.")
                    else:
                        print("No such gesture.")
                    print()
        finally:
            cam.release()
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
