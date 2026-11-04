"""The group: everyone on the show, and how their cameras reach each other.

There's no admin. Each person's deck only ever controls the OBS on their own PC. People who record
put everyone's camera in their own OBS; people who don't just send their camera. Cameras travel
through VDO.Ninja, so decks never connect to each other and nothing can reach anyone's OBS.

A group is a random code plus everyone's names. Each person's camera ID comes from the code and
their name, so anyone with the group link can show anyone's camera, and nobody without it can.
"""
import hashlib
import re
import secrets
from urllib.parse import parse_qs, quote

PREFIX = "podcast-deck://"
JOIN_PAGE = "https://tylergaston22.github.io/podcast-deck/join.html"   # docs/join.html, on GitHub Pages
_GROUP = re.compile(r"pd[0-9a-f]{16}")


# --- The group ---------------------------------------------------------------
def new_group():
    """A fresh, hard-to-guess group code. Anyone who has it can see the group's cameras."""
    return "pd" + secrets.token_hex(8)


def clean_names(names):
    """Names as typed: trimmed, no blanks or repeats (ignoring case), at most 24 characters each."""
    found, seen = [], set()
    for name in names:
        name = " ".join(str(name).split())[:24].strip(",")
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            found.append(name)
    return found


def group_link(group, names):
    """The link to send everyone: a page that walks them through the download, then opens the group in
    their deck. The group rides after the #, which browsers never send to any server."""
    return f"{JOIN_PAGE}#g={group}&n={quote(','.join(names), safe=',')}"


def app_link(group, names):
    """The same group as a podcast-deck:// link, which opens the deck (the join page's Join button)."""
    return f"{PREFIX}join?g={group}&n={quote(','.join(names), safe=',')}"


def find_group(text):
    """(group code, names) from a group link (the web page or podcast-deck://), or None if there isn't one."""
    text = (text or "").strip()
    if text.startswith(PREFIX):
        query = text.split("?", 1)[1] if "?" in text else ""
    elif "#" in text:
        query = text.split("#", 1)[1]
    else:
        return None
    found = parse_qs(query.rstrip("/"))      # Windows can add a / to the end of a podcast-deck:// link
    group = found.get("g", [""])[0].strip()
    if not _GROUP.fullmatch(group):
        return None
    names = clean_names(n for part in found.get("n", []) for n in part.split(","))
    return group, names


# --- Cameras (VDO.Ninja) -----------------------------------------------------
def camera_id(group, name):
    """A person's camera ID in a group. The same on every deck, so no one has to send it anywhere."""
    digest = hashlib.sha256(f"{group}|{name.casefold()}".encode()).hexdigest()
    return "pd_" + digest[:24]


def vdo_push(cam_id, label=""):
    """The page someone opens to send their camera and mic. &webcam skips VDO.Ninja's screen-share choice."""
    return f"https://vdo.ninja/?push={cam_id}&webcam" + (f"&label={quote(label)}" if label else "")


def vdo_view(cam_id):
    return f"https://vdo.ninja/?view={cam_id}"
