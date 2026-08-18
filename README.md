<p align="center">
  <img src="aircontrol.ico" width="96" alt="AirControl" />
</p>

<h1 align="center">AirControl</h1>

<p align="center">
  Control your laptop with your hands. Nothing but a webcam.
</p>

<p align="center">
  <a href="../../releases/latest"><img src="https://img.shields.io/github/v/release/Verisonder/AirControl?style=flat-square&color=c62828&label=download" alt="Latest release" /></a>
  <img src="https://img.shields.io/badge/Windows-0D1117?style=flat-square&logo=windows11&logoColor=00A4EF" alt="Windows" />
  <img src="https://img.shields.io/badge/Python-0D1117?style=flat-square&logo=python&logoColor=FFD343" alt="Python" />
  <img src="https://img.shields.io/badge/licence-MIT-0D1117?style=flat-square" alt="MIT" />
</p>

---

Record a pose. Bind it to something. Hold it in front of the camera and it happens.

Everything runs on your own machine. No account, no cloud, no video leaves the laptop. The
camera is released the moment you turn gestures off, so the indicator light beside your webcam
is a real answer to whether anything is watching.

## Install

Download **AirControl-Setup.exe** from [Releases](../../releases/latest) and run it.

Installs for the current user, no administrator prompt. Python comes with it. The libraries are
fetched during installation — around 400 MB, once.

## What it does

**Shortcuts.** Hold a pose for a moment and it fires: show the desktop, switch app, lock the
screen, play, pause, mute. Or anything else — bind a key combination or a program directly.

**The mouse.** One pose moves the cursor, another holds the left button. A quick close is a
click. Close and move is a drag. Your other hand is still free for shortcuts.

**Out of the way.** Closing the window keeps it running in the tray. One keyboard shortcut turns
gestures on and off from anywhere, `Ctrl+Alt+A` by default.

## Recording a gesture

Press **Record a gesture**, hold the pose through a short countdown, then name it and pick what
it does.

A pose is stored with the hand's position, size and tilt taken out, so the same shape is
recognised wherever your hand is, however far from the camera, and however tilted. Keep
different gestures visibly different from each other — the preview shows how close a match is.

Nothing fires the instant a pose is seen. A shortcut has to be held for a few frames and then
waits before it can fire again, so a flicker while your hand moves does not set something off.

## Settings

| | |
|---|---|
| **Shortcut** | The combination that turns gestures on and off from anywhere |
| **Match tolerance** | Lower is stricter. Raise it if a pose is not being recognised. |
| **Hold frames** | How long a shortcut pose must be held before it fires |
| **Cooldown** | Seconds before the same gesture can fire again |
| **Cursor box** | Higher means a smaller active area, so less hand movement covers the screen |
| **Cursor smoothing** | Lower is steadier but slower to respond |

## Running from source

```
git clone https://github.com/Verisonder/AirControl.git
cd AirControl
pip install -r requirements.txt
python gui.py
```

MediaPipe lags a release or two behind the newest Python. If pip refuses it, check
`python --version` and install an older Python alongside.

There are command line tools too, if you prefer them:

```
python record.py        # record gestures
python aircontrol.py    # run them
python preview.py       # just the tracking, for checking the camera
python fingers.py       # which fingers are up, and pose names
```

## Honest limits

Poor light kills detection. It will work at a desk and struggle on a sofa at night.

Holding an arm up is tiring faster than you expect. This suits a handful of quick actions
rather than continuous use.

A camera running costs battery. Turn gestures off when you are not using them — that genuinely
releases the camera rather than just ignoring it.

Windows blocks some synthetic key combinations. `Win+L` is one, so the lock preset calls the
Windows API directly instead.

## Built with

[MediaPipe](https://ai.google.dev/edge/mediapipe) for hand tracking, [OpenCV](https://opencv.org)
for the camera, [PySide6](https://doc.qt.io/qtforpython-6/) for the window,
[pynput](https://github.com/moses-palmer/pynput) for the global shortcut, and
[PyAutoGUI](https://pyautogui.readthedocs.io) for pressing things.

## Licence

MIT
