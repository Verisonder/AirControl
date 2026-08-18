"""
Recording and matching hand poses.

A pose is stored as the 21 landmarks with the position, size and tilt of the
hand taken out, so the same shape matches wherever your hand is on screen,
however far from the camera, and whichever way it is tilted.

Matching is the mean distance between two normalised poses. Small is similar.
"""

import json
import math
from pathlib import Path

STORE = Path(__file__).with_name("gestures.json")

WRIST = 0
MIDDLE_MCP = 9

# Mean landmark distance below which two poses count as the same shape.
# Raise it to match more loosely, lower it to demand a closer copy.
DEFAULT_TOLERANCE = 0.22


def normalise(lm) -> list:
    """
    Turn 21 raw landmarks into a comparable shape.

    Three things are removed: where the hand is, how big it looks, and which way
    it is tilted. What is left is only the shape of the pose itself.
    """
    ox, oy = lm[WRIST].x, lm[WRIST].y
    pts = [(p.x - ox, p.y - oy) for p in lm]

    # Scale so wrist to middle knuckle is always 1
    ax, ay = pts[MIDDLE_MCP]
    size = math.hypot(ax, ay)
    if size < 1e-6:
        return [0.0] * 42
    pts = [(x / size, y / size) for x, y in pts]

    # Rotate so that same axis points straight up, cancelling hand tilt
    ax, ay = pts[MIDDLE_MCP]
    angle = math.atan2(ay, ax) + math.pi / 2   # want it at -90 degrees
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)
    pts = [(x * cos_a - y * sin_a, x * sin_a + y * cos_a) for x, y in pts]

    flat = []
    for x, y in pts:
        flat.append(round(x, 4))
        flat.append(round(y, 4))
    return flat


def distance(a: list, b: list) -> float:
    """Mean landmark distance between two normalised poses."""
    if len(a) != len(b):
        return float("inf")
    total = 0.0
    for i in range(0, len(a), 2):
        total += math.hypot(a[i] - b[i], a[i + 1] - b[i + 1])
    return total / (len(a) / 2)


class Library:
    """The saved gestures, loaded from and written back to gestures.json."""

    def __init__(self, path: Path = STORE):
        self.path = path
        self.items = []
        self.load()

    # ---- storage -------------------------------------------------------

    def load(self) -> None:
        if not self.path.exists():
            self.items = []
            return
        try:
            self.items = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print("Could not read %s: %s" % (self.path.name, exc))
            print("Starting with an empty library. The old file is untouched.")
            self.items = []

    def save(self) -> None:
        self.path.write_text(json.dumps(self.items, indent=2), encoding="utf-8")

    # ---- editing -------------------------------------------------------

    def add(self, name: str, pose: list, action: str = "", hand: str = "any") -> dict:
        """Add a gesture, replacing any existing one with the same name."""
        self.remove(name)
        item = {"name": name, "hand": hand, "action": action, "pose": pose}
        self.items.append(item)
        self.save()
        return item

    def remove(self, name: str) -> bool:
        before = len(self.items)
        self.items = [g for g in self.items if g["name"].lower() != name.lower()]
        if len(self.items) != before:
            self.save()
            return True
        return False

    def set_action(self, name: str, action: str) -> bool:
        for g in self.items:
            if g["name"].lower() == name.lower():
                g["action"] = action
                self.save()
                return True
        return False

    # ---- matching ------------------------------------------------------

    def match(self, lm, hand: str = "any", tolerance: float = DEFAULT_TOLERANCE):
        """
        Closest saved gesture to this hand, or None.

        Returns (gesture, distance).
        """
        pose = normalise(lm)
        best, best_d = None, float("inf")

        for g in self.items:
            if g.get("hand", "any") not in ("any", hand):
                continue
            d = distance(pose, g["pose"])
            if d < best_d:
                best, best_d = g, d

        if best is not None and best_d <= tolerance:
            return best, best_d
        return None, best_d

    def __len__(self) -> int:
        return len(self.items)
