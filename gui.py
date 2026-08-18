"""
AirControl - desktop app.

Everything the command line tools do, in one window: watch the camera, record
poses, bind them, and turn the whole thing on and off.

    pip install PySide6
    python gui.py
"""

import sys
import time

import cv2

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget,
)

import actions
import gestures
import hands as H
from aircontrol import Mouse, Trigger, PALM, HAVE_MOUSE


# --------------------------------------------------------------------------
# Camera and detection, off the interface thread
# --------------------------------------------------------------------------

class Engine(QThread):
    """Runs the camera and detection. Emits frames and what it sees."""

    frame_ready = Signal(QImage)
    status = Signal(str)
    fired = Signal(str)
    failed = Signal(str)

    def __init__(self, library):
        super().__init__()
        self.library = library
        self.running = True

        # Live settings, safe to change while running
        self.camera_index = 0
        self.tolerance = gestures.DEFAULT_TOLERANCE
        self.hold_frames = 8
        self.cooldown = 1.2
        self.margin = 0.33
        self.smoothing = 0.35
        self.active = False          # gestures actually do things
        self.capture_next = False    # grab the next pose seen

        self.captured = None         # normalised pose waiting to be named
        self.captured_hand = "Right"

    def stop(self):
        self.running = False
        self.wait(2000)

    def run(self):
        try:
            cam = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cam.isOpened():
                self.failed.emit(
                    "Camera %d did not open.\n\n"
                    "Another application may be using it, or try a different "
                    "camera in Settings." % self.camera_index
                )
                return

            fps = H.Fps()
            trigger = Trigger(self.hold_frames, self.cooldown)
            mouse = Mouse(self.margin, self.smoothing, 3, dry=False)
            started = time.time()

            with H.make_landmarker(2) as landmarker:
                while self.running:
                    ok, frame = cam.read()
                    if not ok:
                        continue

                    frame = cv2.flip(frame, 1)
                    h, w = frame.shape[:2]

                    trigger.hold = self.hold_frames
                    trigger.cooldown = self.cooldown
                    mouse.margin = self.margin
                    mouse.smoothing = self.smoothing

                    stamp = int((time.time() - started) * 1000)
                    result = landmarker.detect_for_video(H.to_image(frame), stamp)

                    key_gesture = None
                    mouse_action, mouse_lm = None, None
                    first_lm, first_side = None, "Right"
                    seen = []

                    for i, lm in enumerate(result.hand_landmarks):
                        H.draw_hand(frame, lm)
                        side = H.handedness_of(result, i, True)

                        if first_lm is None:
                            first_lm, first_side = lm, side

                        hit, dist = self.library.match(lm, side, self.tolerance)
                        if not hit:
                            seen.append("%s: -" % side)
                            continue

                        seen.append("%s: %s" % (side, hit["name"]))
                        action = hit.get("action", "")
                        if action in actions.MOUSE_ACTIONS:
                            if mouse_action is None:
                                mouse_action, mouse_lm = action, lm
                        elif key_gesture is None:
                            key_gesture = hit

                    # Capture for the record dialog
                    if self.capture_next and first_lm is not None:
                        self.captured = gestures.normalise(first_lm)
                        self.captured_hand = first_side
                        self.capture_next = False

                    if self.active:
                        if mouse_lm is None:
                            mouse.lost()
                        else:
                            mouse.hold(mouse_action)
                            mouse.move_to(mouse_lm[PALM].x, mouse_lm[PALM].y)
                            px = int(mouse_lm[PALM].x * w)
                            py = int(mouse_lm[PALM].y * h)
                            cv2.circle(frame, (px, py), 12,
                                       (0, 0, 255) if mouse.button else (255, 200, 0), 2)

                        name = trigger.update(key_gesture["name"] if key_gesture else None)
                        if name:
                            action = key_gesture.get("action", "")
                            actions.run(action)
                            self.fired.emit("%s  ->  %s" % (name, actions.describe(action)))

                        if key_gesture and trigger.progress < 1.0:
                            bar = int(trigger.progress * (w - 24))
                            cv2.rectangle(frame, (12, h - 18), (12 + bar, h - 10),
                                          (0, 220, 120), -1)
                    else:
                        mouse.lost()

                    if any(g.get("action") in actions.MOUSE_ACTIONS
                           for g in self.library.items):
                        m = self.margin
                        cv2.rectangle(frame, (int(m * w), int(m * h)),
                                      (int((1 - m) * w), int((1 - m) * h)), (90, 90, 90), 1)

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
                    self.frame_ready.emit(image)

                    self.status.emit("%.0f fps    %s" % (
                        fps.tick(), "   ".join(seen) if seen else "no hand"))

            cam.release()
            mouse.release()

        except Exception as exc:                       # keep the window alive
            self.failed.emit("The camera stopped:\n\n%s" % exc)


# --------------------------------------------------------------------------
# Naming a captured pose
# --------------------------------------------------------------------------

class RecordDialog(QDialog):
    def __init__(self, hand_seen: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New gesture")
        self.setMinimumWidth(380)

        self.name = QLineEdit()
        self.name.setPlaceholderText("open palm, fist, point...")

        self.hand = QComboBox()
        self.hand.addItem("Either hand", "any")
        self.hand.addItem("Left hand only", "Left")
        self.hand.addItem("Right hand only", "Right")

        self.action = QComboBox()
        self.action.addItem("Nothing for now", "none")
        for label, value in actions.PRESETS.items():
            self.action.addItem(label.capitalize(), value)
        self.action.addItem("Something else...", "custom")

        self.custom = QLineEdit()
        self.custom.setPlaceholderText("hotkey:ctrl+shift+n")
        self.custom.hide()
        self.action.currentIndexChanged.connect(self._toggle_custom)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Trigger with", self.hand)
        form.addRow("Does", self.action)
        form.addRow("", self.custom)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Captured a %s hand." % hand_seen.lower()))
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _toggle_custom(self):
        self.custom.setVisible(self.action.currentData() == "custom")

    def values(self):
        action = self.action.currentData()
        if action == "custom":
            action = self.custom.text().strip() or "none"
        return self.name.text().strip(), self.hand.currentData(), action


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)

        self.tolerance = self._spin(0.05, 0.6, 0.01, engine.tolerance)
        self.hold = self._spin(1, 30, 1, engine.hold_frames, decimals=0)
        self.cooldown = self._spin(0.1, 5.0, 0.1, engine.cooldown)
        self.margin = self._spin(0.0, 0.45, 0.01, engine.margin)
        self.smoothing = self._spin(0.05, 1.0, 0.05, engine.smoothing)

        form = QFormLayout()
        form.addRow("Match tolerance", self._with_hint(
            self.tolerance, "Lower is stricter. Raise it if a pose is not recognised."))
        form.addRow("Hold frames", self._with_hint(
            self.hold, "How long a shortcut pose must be held before it fires."))
        form.addRow("Cooldown", self._with_hint(
            self.cooldown, "Seconds before the same gesture can fire again."))
        form.addRow("Cursor box", self._with_hint(
            self.margin, "Higher means a smaller box, so less hand movement."))
        form.addRow("Cursor smoothing", self._with_hint(
            self.smoothing, "Lower is steadier but slower to respond."))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        for w in (self.tolerance, self.hold, self.cooldown, self.margin, self.smoothing):
            w.valueChanged.connect(self._apply)

    def _spin(self, lo, hi, step, value, decimals=2):
        box = QDoubleSpinBox()
        box.setRange(lo, hi)
        box.setSingleStep(step)
        box.setDecimals(decimals)
        box.setValue(value)
        return box

    def _with_hint(self, widget, text):
        hint = QLabel(text)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8a8a8a; font-size: 11px;")
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(widget)
        box.addWidget(hint)
        holder = QWidget()
        holder.setLayout(box)
        return holder

    def _apply(self):
        self.engine.tolerance = self.tolerance.value()
        self.engine.hold_frames = int(self.hold.value())
        self.engine.cooldown = self.cooldown.value()
        self.engine.margin = self.margin.value()
        self.engine.smoothing = self.smoothing.value()


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AirControl")
        self.resize(1000, 620)

        self.library = gestures.Library()
        self.engine = Engine(self.library)
        self.engine.frame_ready.connect(self.show_frame)
        self.engine.status.connect(self.show_status)
        self.engine.fired.connect(self.show_fired)
        self.engine.failed.connect(self.show_failure)

        # -- left: camera
        self.video = QLabel("Starting the camera...")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(560, 420)
        self.video.setStyleSheet("background:#111; border-radius:10px; color:#777;")

        self.status = QLabel("")
        self.status.setStyleSheet("color:#8a8a8a; font-family:monospace; font-size:12px;")

        left = QVBoxLayout()
        left.addWidget(self.video, 1)
        left.addWidget(self.status)

        # -- right: gestures
        title = QLabel("Gestures")
        title.setFont(QFont("", 14, QFont.Bold))

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget{background:#181818;border:none;border-radius:10px;padding:6px;}"
            "QListWidget::item{padding:9px;border-radius:6px;}"
            "QListWidget::item:selected{background:#2c2c2c;}"
        )

        self.record_btn = QPushButton("Record a gesture")
        self.record_btn.clicked.connect(self.record)

        self.rebind_btn = QPushButton("Change what it does")
        self.rebind_btn.clicked.connect(self.rebind)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self.open_settings)

        self.toggle = QPushButton("Turn on")
        self.toggle.setCheckable(True)
        self.toggle.setMinimumHeight(44)
        self.toggle.clicked.connect(self.toggle_active)
        self.toggle.setStyleSheet(
            "QPushButton{background:#2a2a2a;border:none;border-radius:10px;font-size:15px;}"
            "QPushButton:checked{background:#c62828;}"
        )

        row = QHBoxLayout()
        row.addWidget(self.rebind_btn)
        row.addWidget(self.delete_btn)

        right = QVBoxLayout()
        right.addWidget(title)
        right.addWidget(self.list, 1)
        right.addWidget(self.record_btn)
        right.addLayout(row)
        right.addWidget(self.settings_btn)
        right.addSpacing(8)
        right.addWidget(self.toggle)

        body = QHBoxLayout()
        body.addLayout(left, 3)
        body.addLayout(right, 2)

        holder = QWidget()
        holder.setLayout(body)
        self.setCentralWidget(holder)

        self.refresh()
        self.engine.start()

        if not HAVE_MOUSE:
            self.statusBar().showMessage(
                "pyautogui is not installed, so nothing will actually be pressed. "
                "Install it with: pip install pyautogui")

    # -- gesture list -----------------------------------------------------

    def refresh(self):
        self.list.clear()
        for g in self.library.items:
            hand = g.get("hand", "any")
            where = "" if hand == "any" else "  (%s hand)" % hand.lower()
            item = QListWidgetItem("%s%s\n%s"
                                   % (g["name"], where,
                                      actions.describe(g.get("action", ""))))
            item.setData(Qt.UserRole, g["name"])
            self.list.addItem(item)

        empty = not len(self.library)
        self.toggle.setEnabled(not empty)
        if empty:
            self.list.addItem("Nothing recorded yet.")

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    # -- actions ----------------------------------------------------------

    def record(self):
        self.record_btn.setEnabled(False)
        self.countdown = 3
        self.record_btn.setText("Hold your pose... 3")

        def tick():
            self.countdown -= 1
            if self.countdown > 0:
                self.record_btn.setText("Hold your pose... %d" % self.countdown)
                QTimer.singleShot(1000, tick)
                return

            self.engine.captured = None
            self.engine.capture_next = True
            QTimer.singleShot(400, self.finish_record)

        QTimer.singleShot(1000, tick)

    def finish_record(self):
        self.record_btn.setEnabled(True)
        self.record_btn.setText("Record a gesture")

        pose = self.engine.captured
        if pose is None:
            QMessageBox.information(
                self, "No hand",
                "No hand was in view. Hold your pose in front of the camera and try again.")
            return

        dialog = RecordDialog(self.engine.captured_hand, self)
        if dialog.exec() != QDialog.Accepted:
            return

        name, hand, action = dialog.values()
        if not name:
            QMessageBox.information(self, "Needs a name", "Give the gesture a name.")
            return

        self.library.add(name, pose, action, hand)
        self.refresh()

    def rebind(self):
        name = self.selected()
        if not name:
            return

        dialog = RecordDialog("saved", self)
        dialog.setWindowTitle("Change what it does")
        dialog.name.setText(name)
        dialog.name.setEnabled(False)
        if dialog.exec() != QDialog.Accepted:
            return

        _, hand, action = dialog.values()
        for g in self.library.items:
            if g["name"] == name:
                g["action"] = action
                g["hand"] = hand
                break
        self.library.save()
        self.refresh()

    def delete(self):
        name = self.selected()
        if not name:
            return
        if QMessageBox.question(self, "Delete", "Delete %r?" % name) == QMessageBox.Yes:
            self.library.remove(name)
            self.refresh()

    def open_settings(self):
        SettingsDialog(self.engine, self).exec()

    def toggle_active(self, on):
        self.engine.active = on
        self.toggle.setText("Turn off" if on else "Turn on")

    # -- from the engine --------------------------------------------------

    @Slot(QImage)
    def show_frame(self, image):
        self.video.setPixmap(QPixmap.fromImage(image).scaled(
            self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    @Slot(str)
    def show_status(self, text):
        self.status.setText(text)

    @Slot(str)
    def show_fired(self, text):
        self.statusBar().showMessage(text, 2000)

    @Slot(str)
    def show_failure(self, text):
        QMessageBox.critical(self, "Camera", text)

    def closeEvent(self, event):
        self.engine.active = False
        self.engine.stop()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { background:#0e0e0e; color:#f0f0f0; font-size:13px; }
        QPushButton { background:#1e1e1e; border:none; border-radius:8px; padding:9px 14px; }
        QPushButton:hover { background:#282828; }
        QPushButton:disabled { color:#555; }
        QLineEdit, QComboBox, QDoubleSpinBox {
            background:#1a1a1a; border:1px solid #2e2e2e; border-radius:6px; padding:6px;
        }
        QStatusBar { color:#8a8a8a; }
    """)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
