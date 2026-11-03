"""Keeps the installed app up to date from GitHub Releases.

Only the installed app (PodcastDeck.exe) updates this way. A source folder cloned with git updates
through Podcast Deck.bat instead. The newest installer is downloaded and run silently; it closes the
deck, installs over it (config.py, backgrounds, and guests stay), and opens the deck again.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from version import VERSION

REPO = "TylerGaston22/podcast-deck"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "PodcastDeck-Setup.exe"
DOWNLOAD = f"https://github.com/{REPO}/releases/latest/download/{ASSET}"   # always the newest installer


def installed():
    return bool(getattr(sys, "frozen", False)) and VERSION != "dev"


def _number(tag):
    """"v1.0.12" → (1, 0, 12). Anything unreadable counts as oldest."""
    try:
        return tuple(int(p) for p in tag.lstrip("v").split("."))
    except ValueError:
        return ()


def newer():
    """The newest release's installer link, if it's newer than this app. None otherwise, or when offline."""
    if not installed():
        return None
    try:
        req = urllib.request.Request(LATEST, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "podcast-deck"})
        with urllib.request.urlopen(req, timeout=5) as r:
            release = json.load(r)
    except (OSError, ValueError):
        return None
    if _number(release.get("tag_name", "")) <= _number(VERSION):
        return None
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET:
            return asset.get("browser_download_url")
    return None


def install(url):
    """Download the installer and start it silently. The caller closes the deck right after."""
    path = os.path.join(tempfile.gettempdir(), ASSET)
    req = urllib.request.Request(url, headers={"User-Agent": "podcast-deck"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
    subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True)
