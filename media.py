"""Background pictures and YouTube links for the deck. No OBS calls here, so it can be tested alone."""
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
BACKGROUNDS = os.path.join(APP_DIR, "backgrounds")
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
VIDEO_TYPES = (".mp4", ".webm", ".mov", ".m4v")
MAX_PICTURE = 25 * 1024 * 1024


# --- Backgrounds -------------------------------------------------------------
def list_backgrounds():
    """Every picture in the backgrounds folder, sorted by name."""
    if not os.path.isdir(BACKGROUNDS):
        return []
    return sorted((os.path.join(BACKGROUNDS, f) for f in os.listdir(BACKGROUNDS)
                   if f.lower().endswith(IMAGE_TYPES)), key=lambda p: os.path.basename(p).lower())


def add_background(path):
    """Copy a picture into the backgrounds folder and return the copy's path.

    Copying means the background keeps working if the original is moved or deleted.
    A different picture with the same name gets " (2)", " (3)", … added.
    """
    os.makedirs(BACKGROUNDS, exist_ok=True)
    if os.path.dirname(os.path.abspath(path)) == BACKGROUNDS:
        return os.path.abspath(path)
    stem, ext = os.path.splitext(os.path.basename(path))
    dest, n = os.path.join(BACKGROUNDS, stem + ext), 2
    while os.path.exists(dest):
        if _same_file(path, dest):
            return dest
        dest, n = os.path.join(BACKGROUNDS, f"{stem} ({n}){ext}"), n + 1
    shutil.copy2(path, dest)
    return dest


def _same_file(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def next_background(current):
    """The picture after `current` in the folder, wrapping around. None if the folder is empty."""
    pics = list_backgrounds()
    if not pics:
        return None
    norm = [os.path.normcase(os.path.abspath(p)) for p in pics]
    cur = os.path.normcase(os.path.abspath(current)) if current else None
    return pics[(norm.index(cur) + 1) % len(pics)] if cur in norm else pics[0]


# --- YouTube -----------------------------------------------------------------
_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def parse_youtube(link):
    """Return (video id, start seconds) for any normal YouTube link, or None if it isn't one.

    Handles watch?v=, youtu.be/, shorts/, live/, and embed/ links, on www., m., and music.
    """
    link = link.strip()
    if not re.match(r"^[a-z]+://", link, re.I):
        link = "https://" + link
    u = urllib.parse.urlparse(link)
    host = (u.hostname or "").lower()
    for prefix in ("www.", "m.", "music."):
        host = host.removeprefix(prefix)
    query = urllib.parse.parse_qs(u.query)

    vid = ""
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if u.path.rstrip("/") == "/watch":
            vid = query.get("v", [""])[0]
        else:
            m = re.match(r"^/(?:shorts|live|embed|v)/([^/]+)", u.path)
            vid = m.group(1) if m else ""
    if not _ID.fullmatch(vid):
        return None
    return vid, _seconds(query.get("t", query.get("start", ["0"]))[0])


def _seconds(t):
    """'90', '90s', '1m30s', '1h2m3s' → seconds. Anything else → 0."""
    if t.isdigit():
        return int(t)
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", t)
    if not m or not t:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def youtube_check(vid):
    """Ask YouTube whether the video can play outside youtube.com, and get its title.

    Returns (problem, title). problem is a message to show if it can't play, or None if it can (or
    YouTube couldn't be reached, in which case the player page shows its own message if it fails).
    """
    url = ("https://www.youtube.com/oembed?format=json&url="
           + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}", safe=""))
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            title = json.loads(r.read()).get("title")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return ("This video's owner only allows it to play on YouTube, so it can't be played here. "
                    "Open it in a browser and use Browser + Cams instead."), None
        return "YouTube can't find that video. It may be private or deleted.", None
    except (urllib.error.URLError, OSError, ValueError):
        return None, None
    return None, title if isinstance(title, str) else None


# --- Pasted background links ---------------------------------------------------
def parse_background(text):
    """What a pasted background is: a picture file on this PC, a picture link, a YouTube link, or a
    direct video link. Returns a dict with "kind", or None if it's none of those."""
    text = text.strip().strip('"')
    if text.lower().endswith(IMAGE_TYPES) and os.path.isfile(text):
        return {"kind": "picture_file", "path": text}
    found = parse_youtube(text)
    if found:
        return {"kind": "youtube", "id": found[0], "start": found[1]}
    u = urllib.parse.urlparse(text)
    if u.scheme == "https" and u.hostname:
        path = u.path.lower()
        if path.endswith(IMAGE_TYPES):
            return {"kind": "picture_url", "url": text}
        if path.endswith(VIDEO_TYPES):
            return {"kind": "video_url", "url": text}
    return None


def download_picture(url):
    """Save a picture from a link into the backgrounds folder, and return its path.

    https only, pictures only, and at most 25 MB, so a pasted link can't fetch anything else.
    """
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not u.path.lower().endswith(IMAGE_TYPES):
        raise ValueError("That isn't a picture link.")
    req = urllib.request.Request(url, headers={"User-Agent": "podcast-deck"})
    with urllib.request.urlopen(req, timeout=15) as r:
        if not (r.headers.get("Content-Type") or "").startswith("image/"):
            raise ValueError("That link isn't a picture.")
        data = r.read(MAX_PICTURE + 1)
    if len(data) > MAX_PICTURE:
        raise ValueError("That picture is too big (over 25 MB).")
    name = re.sub(r"[^A-Za-z0-9 ._-]", "_", os.path.basename(urllib.parse.unquote(u.path)))[-80:] or "picture.png"
    os.makedirs(BACKGROUNDS, exist_ok=True)
    stem, ext = os.path.splitext(name)
    dest, n = os.path.join(BACKGROUNDS, name), 2
    while os.path.exists(dest):
        dest, n = os.path.join(BACKGROUNDS, f"{stem} ({n}){ext}"), n + 1
    with open(dest, "wb") as f:
        f.write(data)
    return dest
