"""
Stage 2 - which fingers are up.

Same preview as stage 1, plus a live readout of each finger and a name for the
pose. Still nothing is controlled.

Use this to check the reading is right before building gestures on it. Hold a
pose and look at the labels - especially the thumb, which is the one most
likely to need adjusting.

Esc or q to quit.
"""

import argparse
import time

import cv2

import hands as H


def main() -> int:
    ap = argparse.ArgumentParser(description="Finger reading")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hands", type=int, default=2, help="how many hands to track")
    ap.add_argument("--no-mirror", action="store_true")
    args = ap.parse_args()

    cam = H.open_camera(args.camera)
    fps = H.Fps()
    started = time.time()

    print("Running. Esc or q to quit.")

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

                lines = ["fps %.0f" % fps.tick()]

                for i, lm in enumerate(result.hand_landmarks):
                    H.draw_hand(frame, lm)

                    # The tracker labels each hand; index matches hand_landmarks
                    side = "Right"
                    if i < len(result.handedness) and result.handedness[i]:
                        side = result.handedness[i][0].category_name

                    up = H.fingers_up(lm, side)
                    shown = [n for n, u in zip(H.FINGER_NAMES, up) if u]
                    pinch = H.pinch_distance(lm)

                    lines.append("%s: %s" % (side, ", ".join(shown) if shown else "none"))
                    lines.append("  pose %s   count %d" % (H.pose_name(up), sum(up)))
                    lines.append("  pinch %.2f%s" % (pinch, "  PINCH" if pinch < 0.35 else ""))

                H.draw_text(frame, lines)
                cv2.imshow("AirControl - stage 2", frame)

                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
        finally:
            cam.release()
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
