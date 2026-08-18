"""
Checking GitHub for a newer release.
"""

import json
import re
import urllib.request

import appsettings

API = "https://api.github.com/repos/Verisonder/AirControl/releases/latest"
PAGE = "https://github.com/Verisonder/AirControl/releases/latest"


def _parts(text: str):
    """'v1.2.10' -> (1, 2, 10). Anything unparseable sorts lowest."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def latest():
    """
    Returns (tag, url) for the newest release, or None if the check fails.

    Failures are silent on purpose - not being able to reach GitHub is not
    something to interrupt anyone about.
    """
    try:
        request = urllib.request.Request(API, headers={"User-Agent": "AirControl"})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    tag = data.get("tag_name")
    if not tag:
        return None

    url = PAGE
    for asset in data.get("assets", []):
        if asset.get("name", "").lower().endswith(".exe"):
            url = asset.get("browser_download_url", PAGE)
            break

    return tag, url


def newer_than_installed():
    """The release to offer, or None if we are already current."""
    found = latest()
    if not found:
        return None
    tag, url = found
    if _parts(tag) > _parts(appsettings.version()):
        return tag, url
    return None


def download(url: str, target, progress=None) -> bool:
    """
    Fetch the installer to `target`.

    `progress` is called with (bytes_done, bytes_total). Total is 0 when the
    server does not say, which happens often enough to handle rather than
    assume away.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AirControl"})
        with urllib.request.urlopen(request, timeout=30) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(target, "wb") as out:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        return True
    except Exception:
        try:
            import os
            os.remove(target)
        except OSError:
            pass
        return False
