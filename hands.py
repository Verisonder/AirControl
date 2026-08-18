"""
Shared hand tracking. Everything else builds on this.
"""

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
MODEL_PATH = Path(__file__).resolve().with_name("hand_landmarker.task")

CONNECTIONS = [(c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]

# Landmark indices worth naming
WRIST = 0
THUMB_TIP, THUMB_IP, THUMB_MCP = 4, 3, 2
INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP = 8, 12, 16, 20
FINGER_TIPS = (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
ALL_TIPS = (THUMB_TIP,) + FINGER_TIPS

FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")


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
        print("Get it from %s and save it as %s" % (MODEL_URL, MODEL_PATH), file=sys.stderr)
        raise SystemExit(1)

    print("Done.")
    return MODEL_PATH


def make_landmarker(num_hands: int = 1):
    """A HandLandmarker in video mode. Use as a context manager."""
    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(ensure_model())),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )
    return vision.HandLandmarker.create_from_options(options)


def open_camera(index: int = 0, width: int = 640, height: int = 480):
    """
    Open a webcam, or exit with a useful message.

    Asks for a modest resolution on purpose. The detector shrinks whatever it
    is given down to a small square anyway, so a 1080p feed costs a great deal
    of copying and colour conversion for no extra accuracy.
    """
    cam = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cam.isOpened():
        print("Camera %d did not open." % index, file=sys.stderr)
        print("Another app may be holding it, or try --camera 1", file=sys.stderr)
        raise SystemExit(1)

    cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)      # take the newest frame, not a backlog
    return cam


def to_image(frame_bgr):
    """OpenCV BGR frame to a MediaPipe image."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


# --------------------------------------------------------------------------
# Reading the hand
# --------------------------------------------------------------------------

def hand_size(lm) -> float:
    """
    Rough scale of the hand: wrist to middle knuckle.

    Used to turn distances into something independent of how close you are to
    the camera. Without this, a pinch at arm's length and a pinch up close
    measure completely differently.
    """
    dx = lm[9].x - lm[WRIST].x
    dy = lm[9].y - lm[WRIST].y
    return max((dx * dx + dy * dy) ** 0.5, 1e-6)


def handedness_of(result, i: int, mirrored: bool = True) -> str:
    """
    Which real hand this is: "Left" or "Right".

    The tracker names hands as though it were looking at an unmirrored picture.
    We flip the frame first so the preview behaves like a mirror, which means
    its answer arrives back to front. This puts it right again, so "Left"
    always means the hand on the left side of your body.
    """
    side = "Right"
    if i < len(result.handedness) and result.handedness[i]:
        side = result.handedness[i][0].category_name
    if mirrored:
        side = "Left" if side == "Right" else "Right"
    return side


def fingers_up(lm, handedness: str = "Right", mirrored: bool = True) -> list:
    """
    Which fingers are extended: [thumb, index, middle, ring, pinky].

    The four fingers are simple - a tip sits above its middle joint when the
    finger is straight, and y grows downward on screen.

    The thumb folds sideways rather than down, so it is judged left to right
    instead. Which direction counts as extended depends both on the hand and
    on whether the picture is mirrored, so both are taken into account.

    `handedness` is the real hand, as returned by handedness_of.
    """
    four = [lm[t].y < lm[t - 2].y for t in FINGER_TIPS]

    points_right = (handedness == "Right") != bool(mirrored)
    if points_right:
        thumb = lm[THUMB_TIP].x > lm[THUMB_IP].x
    else:
        thumb = lm[THUMB_TIP].x < lm[THUMB_IP].x

    return [thumb] + four


def pinch_distance(lm) -> float:
    """Thumb tip to index tip, scaled by hand size. Under ~0.35 is a pinch."""
    dx = lm[THUMB_TIP].x - lm[INDEX_TIP].x
    dy = lm[THUMB_TIP].y - lm[INDEX_TIP].y
    return ((dx * dx + dy * dy) ** 0.5) / hand_size(lm)


def pose_name(up: list) -> str:
    """A short name for a finger pattern, or 'unknown'."""
    count = sum(up)
    thumb, index, middle, ring, pinky = up

    if count == 5:
        return "open palm"
    if count == 0:
        return "fist"
    if count == 1 and index:
        return "point"
    if count == 1 and thumb:
        return "thumb"
    if count == 2 and index and middle:
        return "two"
    if count == 3 and index and middle and ring:
        return "three"
    if count == 2 and thumb and pinky:
        return "call"
    if count == 2 and index and pinky:
        return "rock"
    return "unknown"


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def draw_hand(frame, lm) -> None:
    """Draw bones and joints for one hand."""
    h, w = frame.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in lm]

    for start, end in CONNECTIONS:
        cv2.line(frame, pts[start], pts[end], (255, 255, 255), 2, cv2.LINE_AA)

    for i, p in enumerate(pts):
        tip = i in ALL_TIPS
        cv2.circle(frame, p, 6 if tip else 4, (0, 0, 255) if tip else (0, 255, 0), -1, cv2.LINE_AA)


def draw_text(frame, lines, x=12, y=30, colour=(0, 255, 0)) -> None:
    """A few lines of text in the corner."""
    for i, line in enumerate(lines):
        cv2.putText(
            frame, line, (x, y + i * 26),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2, cv2.LINE_AA,
        )


class Fps:
    """Smoothed frames per second."""

    def __init__(self):
        self._last = time.time()
        self.value = 0.0

    def tick(self) -> float:
        now = time.time()
        self.value = 0.9 * self.value + 0.1 * (1.0 / max(now - self._last, 1e-6))
        self._last = now
        return self.value
