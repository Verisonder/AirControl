# AirControl

Control your laptop with hand gestures through the webcam.

Everything runs locally on the CPU. No cloud, no account, no video leaves the machine.

## Install

Download **AirControl-Setup.exe** from [Releases](../../releases) and run it. Python is
bundled, so nothing else is needed. It installs for the current user only, no administrator
prompt.

Your gestures are kept in `%APPDATA%\AirControl\gestures.json` and survive an upgrade.

## Running from source

```
pip install -r requirements.txt
python gui.py
```

MediaPipe usually lags a release or two behind the newest Python. If pip refuses it, check
`python --version` and install an older Python alongside.

## The command line tools

The window is the easy way in, but everything works from a terminal too.

**Record your gestures**

```
python record.py
```

Hold a pose, press SPACE, name it, and pick what it does. Shortcuts like "show desktop" fire
once. "Move cursor" and "left click" drive the mouse instead.

**Then run it**

```
python aircontrol.py
```

| Key | |
|---|---|
| P | pause everything |
| L | list loaded gestures |
| R | reload after recording more |
| Esc | quit |

Add `--dry-run` to watch it work without pressing anything. Worth doing before you bind
anything destructive.

## How poses are matched

A pose is stored with the hand's position, size and tilt removed, so the same shape matches
wherever your hand is, however far from the camera, and however tilted. The preview shows the
match distance — keep different gestures well apart from each other.

Shortcut gestures must be held for a few frames before firing, and there is a cooldown after,
so a flicker while your hand moves does not set something off. Mouse poses act continuously
instead: hold the click pose briefly for a click, hold it while moving to drag.

One hand can drive the cursor while the other fires a shortcut.

## Tuning

| Flag | |
|---|---|
| `--tolerance` | how close a match must be. Lower is stricter. |
| `--hold` | frames a shortcut gesture must be held |
| `--cooldown` | seconds before the same gesture can fire again |
| `--margin` | bigger means a smaller active box, so less hand movement covers the screen |
| `--smoothing` | cursor smoothing. Lower is steadier but laggier. |
| `--camera` | try `1` if the wrong camera opens |

## Checking things

```
python preview.py     # just the tracking
python fingers.py     # which fingers are up, and pose names
```

Useful when something is not being recognised.

## Known limits

Poor light kills detection. Holding an arm up gets tiring, so this suits a handful of quick
actions rather than continuous use. A camera running constantly costs battery.

Windows blocks some synthetic key combinations. `win+l` is one — the lock preset uses a direct
Windows call instead.

## Licence

MIT
