# AirControl

Control your laptop with hand gestures through the webcam.

Everything runs locally on the CPU. No cloud, no account, no video leaves the machine.

## Status

Stage 1 — hand tracking preview. Nothing is controlled yet.

## Setup

```
pip install -r requirements.txt
```

MediaPipe usually lags a release or two behind the newest Python. If pip refuses to install it,
check `python --version` and install an older Python alongside.

## Run

```
python stage1_preview.py
```

A window opens showing the webcam with the 21 tracked points drawn on any hand it sees.
Esc or `q` to quit.

If the window is black, another application is holding the camera. If it opens the wrong one:

```
python stage1_preview.py --camera 1
```

## Plan

1. **Preview** — see the hand. *(here)*
2. **Fingers** — work out which fingers are up.
3. **Gestures** — turn poses into intentions, with a hold time and a cooldown so it does not
   fire on every flicker.
4. **Actions** — media keys, volume, window switching.
5. **Background** — tray icon, no video window, and an easy off switch.

## Known limits

Poor light kills detection. Holding an arm up gets tiring quickly, so this suits a handful of
quick actions rather than continuous control. A camera running constantly costs battery.

## Licence

MIT
