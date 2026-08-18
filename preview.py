"""
Stage 1 - see your hand.

Opens the webcam and draws the 21 tracked points on any hand it finds.
Nothing is controlled yet. This exists to prove the camera and the tracker work
before anything is built on top of them.

The hand model is downloaded once on first run and cached next to this file.

Esc or q to quit.
"""

import argparse
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_PATH = Path(__file__).with_name("hand_landmarker.task")

CONNECTIONS = [(c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]
TIPS = (4, 8, 12, 16, 20)


def ensure_model() -> Path:
    """Download the hand model once, then reuse it."""
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1000:
        return MODEL_PATH

    print("Downloading the hand model (about 8 MB, once only)...")
    tmp = MODEL_PATH.with_suffix(".part")
    try:
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(MODEL_PATH)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print("Could not download the model: %s" % exc, file=sys.stderr)
        print("Download it by hand from %s" % MODEL_URL, file=sys.stderr)
        print("and save it as %s" % MODEL_PATH, file=sys.stderr)
        raise SystemExit(1)

    print("Done.")
    return MODEL_PATH


def draw_hand(frame, landmarks) -> None:
    """Draw bones and joints for one hand onto the frame."""
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]

    for start, end in CONNECTIONS:
        cv2.line(frame, pts[start], pts[end], (255, 255, 255), 2, cv2.LINE_AA)

    for i, p in enumerate(pts):
        tip = i in TIPS
        cv2.circle(frame, p, 6 if tip else 4, (0, 0, 255) if tip else (0, 255, 0), -1, cv2.LINE_AA)


def main() -> int:
    ap = argparse.ArgumentParser(description="Hand tracking preview")
    ap.add_argument("--camera", type=int, default=0, help="camera index (try 1 if 0 is wrong)")
    ap.add_argument("--hands", type=int, default=2, help="how many hands to track")
    ap.add_argument("--no-mirror", action="store_true", help="do not flip the image")
    args = ap.parse_args()

    model = ensure_model()

    cam = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cam.isOpened():
        print("Camera %d did not open." % args.camera, file=sys.stderr)
        print("Another app may be holding it, or try --camera 1", file=sys.stderr)
        return 1

    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=args.hands,
        min_hand_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )

    last = time.time()
    fps = 0.0
    started = time.time()

    print("Running. Esc or q to quit.")

    with vision.HandLandmarker.create_from_options(options) as landmarker:
        try:
            while True:
                ok, frame = cam.read()
                if not ok:
                    print("Dropped a frame.", file=sys.stderr)
                    break

                if not args.no_mirror:
                    frame = cv2.flip(frame, 1)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                stamp = int((time.time() - started) * 1000)

                result = landmarker.detect_for_video(image, stamp)

                found = len(result.hand_landmarks)
                for landmarks in result.hand_landmarks:
                    draw_hand(frame, landmarks)

                now = time.time()
                fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-6))
                last = now

                cv2.putText(
                    frame,
                    "hands %d   fps %.0f" % (found, fps),
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
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
