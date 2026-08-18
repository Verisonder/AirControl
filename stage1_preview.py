"""
Stage 1 — see your hand.

Opens the webcam and draws the 21 tracked points on any hand it finds.
Nothing is controlled yet. This exists to prove the camera and the tracker work
before anything is built on top of them.

Esc or q to quit.
"""

import argparse
import sys
import time

import cv2
import mediapipe as mp


def main() -> int:
    ap = argparse.ArgumentParser(description="Hand tracking preview")
    ap.add_argument("--camera", type=int, default=0, help="camera index (try 1 if 0 is wrong)")
    ap.add_argument("--hands", type=int, default=1, help="how many hands to track")
    ap.add_argument("--no-mirror", action="store_true", help="do not flip the image")
    args = ap.parse_args()

    cam = cv2.VideoCapture(args.camera)
    if not cam.isOpened():
        print(f"Camera {args.camera} did not open.", file=sys.stderr)
        print("Another app may be holding it, or try --camera 1", file=sys.stderr)
        return 1

    hands = mp.solutions.hands.Hands(
        max_num_hands=args.hands,
        model_complexity=0,          # lighter model, plenty for this
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )
    draw = mp.solutions.drawing_utils
    styles = mp.solutions.drawing_styles

    last = time.time()
    fps = 0.0

    print("Running. Esc or q to quit.")

    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                print("Dropped a frame.", file=sys.stderr)
                break

            if not args.no_mirror:
                frame = cv2.flip(frame, 1)

            # MediaPipe wants RGB; OpenCV gives BGR
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            result = hands.process(rgb)

            found = 0
            if result.multi_hand_landmarks:
                found = len(result.multi_hand_landmarks)
                for hand in result.multi_hand_landmarks:
                    draw.draw_landmarks(
                        frame,
                        hand,
                        mp.solutions.hands.HAND_CONNECTIONS,
                        styles.get_default_hand_landmarks_style(),
                        styles.get_default_hand_connections_style(),
                    )

            now = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-6))
            last = now

            cv2.putText(
                frame,
                f"hands {found}   fps {fps:.0f}",
                (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            cv2.imshow("AirControl - stage 1", frame)
            if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                break
    finally:
        cam.release()
        hands.close()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
