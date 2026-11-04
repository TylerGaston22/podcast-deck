"""Browser-controlled videos: the background video and the Video + Cams video, run from a page in your
browser. Two channels: "bg" (the background) and "video" (the Video + Cams box).

The deck runs a tiny web server on this PC only (127.0.0.1, never the network). It serves:

- /bg: the control page (bg_control.html) opened in your browser after pasting a video link. You
  play, pause, mute, and seek there; nothing changes in OBS until you click "Use as background".
  After that, the same controls change the background video live.
- /bg/state and /video/state: what OBS should show right now in each channel.
- /bg/frame?ch=…: the player OBS shows (bg_frame.html). OBS's "Background Video" and "Video Panel"
  sources are local files (bg_player.html, player.html) that load it from localhost, because YouTube
  won't play for pages opened by IP address.

Every request that changes something needs this run's secret token, which only the deck and the
page it opened know, so no website you visit can change your background.
"""
import json
import math
import mimetypes
import os
import urllib.parse
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import media

ADMIN_PORT = 4461                              # OBS's Background Video page reads the deck here
PAGE = os.path.join(media.APP_DIR, "bg_control.html")
FRAME = os.path.join(media.APP_DIR, "bg_frame.html")
MAX_BODY = 8 * 1024
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def valid_state(d):
    """A background video state, checked field by field. None means "no background video"."""
    if d is None:
        return None
    if not isinstance(d, dict):
        raise ValueError
    kind = d.get("kind")
    out = {"kind": kind, "id": None, "url": None}
    if kind == "youtube":
        if not (isinstance(d.get("id"), str) and _YOUTUBE_ID.fullmatch(d["id"])):
            raise ValueError
        out["id"] = d["id"]
    elif kind == "video_url":
        if media.parse_background(d.get("url") or "") != {"kind": "video_url", "url": d.get("url")}:
            raise ValueError
        out["url"] = d["url"]
    else:
        raise ValueError
    title = d.get("title")
    out["title"] = title[:200] if isinstance(title, str) else ""
    out["playing"] = bool(d.get("playing", True))
    out["muted"] = bool(d.get("muted", False))
    volume, time_, seek = d.get("volume", 100), d.get("time", 0), d.get("seek", 0)
    out["volume"] = int(min(max(volume, 0), 100)) if isinstance(volume, (int, float)) and math.isfinite(volume) else 100
    out["time"] = float(max(time_, 0)) if isinstance(time_, (int, float)) and math.isfinite(time_) else 0.0
    out["seek"] = int(seek) if isinstance(seek, int) else 0
    return out


CHANNELS = ("bg", "video")


class BgControl:
    """The deck's local server. `deck` supplies live_state(channel) and control(channel, state, action)."""

    def __init__(self, deck, admin):
        self.deck = deck
        self.token = secrets.token_urlsafe(18)
        self.pending = {}                      # channel → the video its page controls (with "live": bool)
        self.httpd = None
        server = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 10

            def log_message(self, *args):
                pass

            def reply(self, code, body, kind="application/json", cors=False):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                if cors:                       # OBS's page is a local file, so it's another origin
                    self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path, _, query = self.path.partition("?")
                if path in ("/bg/state", "/video/state"):
                    return self.reply(200, server.deck.live_state(path.split("/")[1]), cors=True)
                if path == "/video/idle":         # what the empty Video + Cams box shows
                    return self.reply(200, server.deck.idle_state(), cors=True)
                if path.startswith("/bg/picture/"):   # a picture from the backgrounds folder, for that box
                    name = os.path.basename(urllib.parse.unquote(path[len("/bg/picture/"):]))
                    file = os.path.join(media.BACKGROUNDS, name)
                    if name.lower().endswith(media.IMAGE_TYPES) and os.path.isfile(file):
                        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
                        with open(file, "rb") as f:
                            return self.reply(200, f.read(), kind, cors=True)
                    return self.reply(404, {"message": "Not found."})
                if path == "/bg/frame":
                    with open(FRAME, encoding="utf-8") as f:
                        return self.reply(200, f.read().encode(), "text/html; charset=utf-8")
                ch = query.partition("&ch=")[2] or "bg"
                if path == "/bg" and query.partition("&")[0] == f"t={server.token}" and server.pending.get(ch):
                    with open(PAGE, encoding="utf-8") as f:
                        page = f.read()
                    setup = json.dumps({"token": server.token, "channel": ch, "source": server.pending[ch],
                                        "colors": server.deck.page_colors()})
                    page = page.replace("/*SETUP*/null", setup.replace("</", "<\\/"))
                    return self.reply(200, page.encode(), "text/html; charset=utf-8")
                self.reply(404, {"message": "Not found."})

            def do_POST(self):
                length = self.headers.get("Content-Length") or ""
                length = int(length) if length.isdigit() else 0
                if self.path != "/bg/control" or not 0 < length <= MAX_BODY:
                    return self.reply(400, {"message": "Unknown request."})
                try:
                    body = json.loads(self.rfile.read(length))
                    if not secrets.compare_digest(str(body.get("token", "")), server.token):
                        return self.reply(403, {"message": "This page is out of date. Paste the link again."})
                    action, ch = body.get("action"), body.get("channel", "bg")
                    if action not in ("preview", "go_live", "update", "stop") or ch not in CHANNELS:
                        raise ValueError
                    state = valid_state(body.get("state")) if action != "stop" else None
                except (ValueError, TypeError, AttributeError):
                    return self.reply(400, {"message": "Unknown request."})
                try:
                    self.reply(200, {"message": server.deck.control(ch, state, action)})
                except Exception as e:  # noqa: BLE001 - the page shows whatever went wrong
                    self.reply(400, {"message": str(e)})

        for port in ([ADMIN_PORT] if admin else []) + [0]:   # a second deck takes any free port
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                break
            except OSError:
                continue
        if self.httpd:
            self.httpd.daemon_threads = True
            threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def page_url(self, channel="bg"):
        # localhost, not 127.0.0.1: YouTube refuses to play for pages opened by IP address.
        return f"http://localhost:{self.httpd.server_address[1]}/bg?t={self.token}&ch={channel}"
