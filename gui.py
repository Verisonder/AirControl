"""
AirControl - desktop app.

Everything the command line tools do, in one window: watch the camera, record
poses, bind them, and turn the whole thing on and off.

    pip install PySide6
    python gui.py
"""

import sys
import time
import webbrowser
from pathlib import Path

import cv2

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QAction, QIcon, QImage, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout,
    QWidget,
)

import actions
import appsettings
import gestures
import hands as H
import updates
from aircontrol import Mouse, Trigger, PALM, HAVE_MOUSE

try:
    from pynput import keyboard as pynput_keyboard
    HAVE_HOTKEY = True
except Exception:
    HAVE_HOTKEY = False

ICON_PATH = Path(__file__).resolve().with_name("aircontrol.ico")


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
        self.preview = True          # window visible - draw and send frames

        self.captured = None         # normalised pose waiting to be named
        self.captured_hand = "Right"

    def stop(self):
        self.running = False
        self.wait(2000)

    def run(self):
        try:
            cam = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            # A modest feed. The detector shrinks whatever it gets to a small
            # square, so a 1080p frame is copying and colour conversion spent
            # for nothing.
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
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
            last_hand = time.time()

            with H.make_landmarker(2) as landmarker:
                while self.running:
                    # Idling out of sight: an empty room does not need thirty
                    # detections a second. Drop to a slow poll after a few
                    # seconds with no hand, and jump straight back to full speed
                    # the moment one appears.
                    if not self.preview and time.time() - last_hand > 3.0:
                        time.sleep(0.12)

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

                    if result.hand_landmarks:
                        last_hand = time.time()

                    showing = self.preview

                    for i, lm in enumerate(result.hand_landmarks):
                        if showing:
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
                            if showing:
                                px = int(mouse_lm[PALM].x * w)
                                py = int(mouse_lm[PALM].y * h)
                                cv2.circle(frame, (px, py), 12,
                                           (0, 0, 255) if mouse.button else (255, 200, 0), 2)

                        name = trigger.update(key_gesture["name"] if key_gesture else None)
                        if name:
                            action = key_gesture.get("action", "")
                            actions.run(action)
                            self.fired.emit("%s  ->  %s" % (name, actions.describe(action)))

                        if showing and key_gesture and trigger.progress < 1.0:
                            bar = int(trigger.progress * (w - 24))
                            cv2.rectangle(frame, (12, h - 18), (12 + bar, h - 10),
                                          (0, 220, 120), -1)
                    else:
                        mouse.lost()

                    # Hidden window: skip the picture entirely. Converting and
                    # sending frames nobody can see is most of the cost, and the
                    # queued signals pile up while the interface is throttled.
                    if showing:
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
                    else:
                        fps.tick()

            cam.release()
            mouse.release()

        except Exception as exc:                       # keep the window alive
            self.failed.emit("The camera stopped:\n\n%s" % exc)


class Hotkey(QThread):
    """
    Listens for one key combination anywhere in Windows.

    Runs in its own thread because the listener blocks. Restarted rather than
    reconfigured when the combination changes - it is cheap and avoids fighting
    pynput's internal state.
    """

    pressed = Signal()

    def __init__(self, combination: str):
        super().__init__()
        self.combination = combination
        self._listener = None

    def run(self):
        if not HAVE_HOTKEY:
            return
        try:
            self._listener = pynput_keyboard.GlobalHotKeys(
                {self.combination: self.pressed.emit}
            )
            self._listener.run()
        except Exception:
            # A malformed combination should not take the app down
            self._listener = None

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
        self.wait(1500)


class UpdateCheck(QThread):
    """Asks GitHub whether there is a newer release. Silent on failure."""

    found = Signal(str, str)

    def run(self):
        result = updates.newer_than_installed()
        if result:
            self.found.emit(*result)


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

        self.headline = QLabel("Captured a %s hand." % hand_seen.lower())

        layout = QVBoxLayout(self)
        layout.addWidget(self.headline)
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
    hotkey_changed = Signal(str)

    def __init__(self, engine, settings, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)

        self.hotkey = QLineEdit(settings["hotkey"])
        self.hotkey.setPlaceholderText("<ctrl>+<alt>+a")
        if not HAVE_HOTKEY:
            self.hotkey.setEnabled(False)
            self.hotkey.setText("pynput is not installed")

        self.close_to_tray = QCheckBox("Keep running when the window is closed")
        self.close_to_tray.setChecked(settings["close_to_tray"])

        self.start_minimised = QCheckBox("Start hidden in the tray")
        self.start_minimised.setChecked(settings["start_minimised"])

        self.check_updates = QCheckBox("Check for updates on start")
        self.check_updates.setChecked(settings["check_updates"])

        self.tolerance = self._spin(0.05, 0.6, 0.01, engine.tolerance)
        self.hold = self._spin(1, 30, 1, engine.hold_frames, decimals=0)
        self.cooldown = self._spin(0.1, 5.0, 0.1, engine.cooldown)
        self.margin = self._spin(0.0, 0.45, 0.01, engine.margin)
        self.smoothing = self._spin(0.05, 1.0, 0.05, engine.smoothing)

        form = QFormLayout()
        form.addRow("Shortcut", self._with_hint(
            self.hotkey,
            "Turns gestures on and off from anywhere. Write it as "
            "<ctrl>+<alt>+a, using <shift>, <cmd> and so on."))
        form.addRow("", self.close_to_tray)
        form.addRow("", self.start_minimised)
        form.addRow("", self.check_updates)
        form.addRow(self._divider())
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
        for box in (self.close_to_tray, self.start_minimised, self.check_updates):
            box.toggled.connect(self._apply)
        self.hotkey.editingFinished.connect(self._apply_hotkey)

    def _divider(self):
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#2a2a2a;")
        return line

    def _apply_hotkey(self):
        text = self.hotkey.text().strip()
        if HAVE_HOTKEY and text and text != self.settings["hotkey"]:
            self.settings["hotkey"] = text
            appsettings.save(self.settings)
            self.hotkey_changed.emit(text)

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

        self.settings.update({
            "tolerance": self.engine.tolerance,
            "hold_frames": self.engine.hold_frames,
            "cooldown": self.engine.cooldown,
            "margin": self.engine.margin,
            "smoothing": self.engine.smoothing,
            "close_to_tray": self.close_to_tray.isChecked(),
            "start_minimised": self.start_minimised.isChecked(),
            "check_updates": self.check_updates.isChecked(),
        })
        appsettings.save(self.settings)


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AirControl")
        self.resize(1000, 620)

        self.settings = appsettings.load()
        self.library = gestures.Library()

        self.engine = Engine(self.library)
        self.engine.tolerance = self.settings["tolerance"]
        self.engine.hold_frames = self.settings["hold_frames"]
        self.engine.cooldown = self.settings["cooldown"]
        self.engine.margin = self.settings["margin"]
        self.engine.smoothing = self.settings["smoothing"]
        self.engine.frame_ready.connect(self.show_frame)
        self.engine.status.connect(self.show_status)
        self.engine.fired.connect(self.show_fired)
        self.engine.failed.connect(self.show_failure)

        self.hotkey = None
        self.update_url = ""
        self.quitting = False

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

        self.update_btn = QPushButton("Update available")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self.open_update)
        self.update_btn.hide()
        self.update_btn.setStyleSheet(
            "QPushButton{background:#c62828;border:none;border-radius:6px;"
            "padding:5px 10px;font-size:11px;}"
            "QPushButton:hover{background:#d32f2f;}"
        )

        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.update_btn)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget{background:#181818;border:none;border-radius:10px;padding:6px;}"
            "QListWidget::item{padding:9px;border-radius:6px;}"
            "QListWidget::item:selected{background:#2c2c2c;color:#f0f0f0;}"
            "QListWidget::item:selected:active{background:#2c2c2c;color:#f0f0f0;}"
            "QListWidget::item:selected:!active{background:#2c2c2c;color:#f0f0f0;}"
        )

        self.record_btn = QPushButton("Record a gesture")
        self.record_btn.clicked.connect(self.record)

        self.rebind_btn = QPushButton("Edit")
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
        right.addLayout(title_row)
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

        self.build_tray()
        self.refresh()
        self.engine.start(QThread.HighPriority)
        self.start_hotkey(self.settings["hotkey"])

        if self.settings["check_updates"]:
            self.updater = UpdateCheck()
            self.updater.found.connect(self.update_available)
            self.updater.start()

        if not HAVE_HOTKEY:
            self.statusBar().showMessage(
                "The keyboard shortcut needs pynput. Install it with: pip install pynput", 8000)

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

        current = next((g for g in self.library.items if g["name"] == name), None)
        if current is None:
            return

        dialog = RecordDialog("saved", self)
        dialog.setWindowTitle("Edit gesture")
        dialog.headline.setText("Editing %r. The pose itself is unchanged." % name)
        dialog.name.setText(name)

        index = dialog.hand.findData(current.get("hand", "any"))
        if index >= 0:
            dialog.hand.setCurrentIndex(index)

        action_now = current.get("action", "none")
        index = dialog.action.findData(action_now)
        if index >= 0:
            dialog.action.setCurrentIndex(index)
        else:
            dialog.action.setCurrentIndex(dialog.action.count() - 1)
            dialog.custom.setText(action_now)

        if dialog.exec() != QDialog.Accepted:
            return

        new_name, hand, action = dialog.values()
        if not new_name:
            QMessageBox.information(self, "Needs a name", "Give the gesture a name.")
            return

        clash = new_name.lower() != name.lower() and any(
            g["name"].lower() == new_name.lower() for g in self.library.items)
        if clash:
            QMessageBox.information(
                self, "Name taken",
                "Another gesture is already called %r." % new_name)
            return

        current["name"] = new_name
        current["hand"] = hand
        current["action"] = action
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
        dialog = SettingsDialog(self.engine, self.settings, self)
        dialog.hotkey_changed.connect(self.start_hotkey)
        dialog.exec()

    def toggle_active(self, on=None):
        if on is None:
            on = not self.engine.active
            self.toggle.setChecked(on)
        self.engine.active = on
        self.toggle.setText("Turn off" if on else "Turn on")
        self.tray_toggle.setText("Turn off" if on else "Turn on")
        self.tray.setToolTip("AirControl - %s" % ("on" if on else "off"))
        if self.tray.supportsMessages() and not self.isVisible():
            self.tray.showMessage("AirControl",
                                  "Gestures are %s." % ("on" if on else "off"),
                                  QSystemTrayIcon.Information, 1500)

    # -- tray -------------------------------------------------------------

    def build_tray(self):
        icon = QIcon(str(ICON_PATH)) if ICON_PATH.exists() else self.style().standardIcon(
            self.style().StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("AirControl - off")

        menu = QMenu()
        show = QAction("Open AirControl", self)
        show.triggered.connect(self.show_window)

        self.tray_toggle = QAction("Turn on", self)
        self.tray_toggle.triggered.connect(lambda: self.toggle_active(None))

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.really_quit)

        menu.addAction(show)
        menu.addSeparator()
        menu.addAction(self.tray_toggle)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)
        self.tray.show()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def really_quit(self):
        self.quitting = True
        self.close()
        QApplication.quit()

    # -- global shortcut --------------------------------------------------

    def start_hotkey(self, combination: str):
        if not HAVE_HOTKEY:
            return
        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None
        if not combination:
            return
        self.hotkey = Hotkey(combination)
        self.hotkey.pressed.connect(self.hotkey_fired)
        self.hotkey.start()

    @Slot()
    def hotkey_fired(self):
        self.toggle_active(None)

    # -- updates ----------------------------------------------------------

    @Slot(str, str)
    def update_available(self, tag, url):
        self.update_url = url
        self.update_btn.setText("Update to %s" % tag)
        self.update_btn.show()

    def open_update(self):
        if self.update_url:
            webbrowser.open(self.update_url)

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

    def changeEvent(self, event):
        # Minimised windows get no repaints, so stop producing pictures for one
        if event.type() == event.Type.WindowStateChange:
            self.engine.preview = not self.isMinimized()
        super().changeEvent(event)

    def hideEvent(self, event):
        self.engine.preview = False
        super().hideEvent(event)

    def showEvent(self, event):
        self.engine.preview = True
        super().showEvent(event)

    def closeEvent(self, event):
        # Closing the window normally means "get out of my way", not "stop
        # working" - the whole point is that gestures keep running.
        if self.settings["close_to_tray"] and not self.quitting:
            event.ignore()
            self.hide()
            if self.tray.supportsMessages():
                self.tray.showMessage(
                    "AirControl",
                    "Still running. Use the tray icon to open or quit.",
                    QSystemTrayIcon.Information, 2500)
            return

        self.engine.active = False
        self.engine.stop()
        if self.hotkey is not None:
            self.hotkey.stop()
        self.tray.hide()
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

    # Closing to the tray must not end the program
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    if window.settings["start_minimised"]:
        window.hide()
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
