"""The admin deck's door for guests: a small web server that only listens on Tailscale.

Guests' decks send requests here ("move my camera there", "switch layout"). Each request carries
that guest's invite code, and the admin's deck checks what that guest is allowed to do before it
touches OBS. Guests never get OBS itself or its password.

It never listens on anything but this PC's Tailscale address, so it can't be reached from the
open internet or the local network, and guests' decks refuse to connect anywhere else.
"""
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import media

TAILSCALE = ipaddress.ip_network("100.64.0.0/10")    # the only addresses Tailscale hands out
INVITES = os.path.join(media.APP_DIR, "guests.json")  # {cam name: invite code}, git-ignored
PREFIX = "podcast-deck://"
MAX_BODY = 16 * 1024
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_CAMERA_ID = re.compile(r"[A-Za-z0-9_]{12,64}")
REMOTE_CAMS = os.path.join(media.APP_DIR, "remote_cams.json")   # {cam name: VDO.Ninja ID}, git-ignored


# --- Tailscale ---------------------------------------------------------------
def on_tailscale(host):
    """True if host is (or resolves only to) a Tailscale address."""
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, None, socket.AF_INET)}
    except OSError:
        return False
    return bool(addrs) and all(ipaddress.ip_address(a) in TAILSCALE for a in addrs)


def tailscale_ip():
    """This PC's Tailscale address, as reported by Tailscale itself. None if it isn't running.

    Only Tailscale's own answer counts: other networks (some internet providers, virtual machines)
    also use 100.64.x.x addresses, and listening on one of those could expose the deck.
    """
    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        for line in out.split():
            if ipaddress.ip_address(line) in TAILSCALE:
                return line
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


# --- Remote cameras (VDO.Ninja) ----------------------------------------------
def new_camera_id():
    """A long, hard-to-guess VDO.Ninja ID. Anyone who has it can watch that camera, so it stays private."""
    return "pd_" + secrets.token_hex(12)


def vdo_push(cam_id):
    """The link a guest opens to send their camera and mic. &webcam skips VDO.Ninja's screen-share choice."""
    return f"https://vdo.ninja/?push={cam_id}&webcam"


def vdo_view(cam_id):
    return f"https://vdo.ninja/?view={cam_id}"


def load_remote_cams():
    try:
        with open(REMOTE_CAMS, encoding="utf-8") as f:
            found = json.load(f)
        return {k: v for k, v in found.items() if isinstance(v, str) and _CAMERA_ID.fullmatch(v)}
    except (OSError, ValueError, AttributeError):
        return {}


def save_remote_cam(name, cam_id):
    """Remember a guest's camera ID. True if it changed."""
    found = load_remote_cams()
    if found.get(name) == cam_id:
        return False
    found[name] = cam_id
    with open(REMOTE_CAMS, "w", encoding="utf-8") as f:
        json.dump(found, f, indent=2)
    return True


# --- Invites -----------------------------------------------------------------
def load_invites():
    try:
        with open(INVITES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_invites(invites):
    with open(INVITES, "w", encoding="utf-8") as f:
        json.dump(invites, f, indent=2)


def new_invite(name):
    """Give a guest a fresh code. Any older code for them stops working."""
    invites = load_invites()
    invites[name] = secrets.token_urlsafe(24)
    _save_invites(invites)
    return invites[name]


def remove_invite(name):
    invites = load_invites()
    if invites.pop(name, None) is not None:
        _save_invites(invites)


def invite_text(ip, port, code):
    return f"{PREFIX}{ip}:{port}/{code}"


def parse_invite(text):
    """(host, port, code) from an invite. Refuses anything that isn't a Tailscale address."""
    from control import DeckError
    m = re.fullmatch(r"podcast-deck://([^:/\s]+):(\d+)/([A-Za-z0-9_-]{16,})", (text or "").strip())
    if not m:
        raise DeckError("That invite doesn't look right. Paste the whole invite from the admin into INVITE "
                        "in config.py.")
    host, port, code = m.group(1), int(m.group(2)), m.group(3)
    if not on_tailscale(host):
        raise DeckError("That invite isn't a Tailscale address. The deck only connects over Tailscale.")
    if tailscale_ip() is None:
        raise DeckError("Tailscale isn't running on this PC. Start Tailscale, then reopen the deck.")
    return host, port, code


def who(code):
    """The guest an invite code belongs to, or None."""
    for name, known in load_invites().items():
        if code and hmac.compare_digest(code, known):
            return name
    return None


# --- The door ----------------------------------------------------------------
class LinkServer:
    """Runs on the admin's deck. Started only if this PC has a Tailscale address."""

    def __init__(self, local, port):
        self.local, self.port = local, port
        self.ip = tailscale_ip()
        self.httpd = None
        if self.ip is None:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 10                       # drop connections that stall

            def log_message(self, *args):      # no console under pythonw
                pass

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def guest(self):
                if ipaddress.ip_address(self.client_address[0]) not in TAILSCALE:
                    return None
                auth = self.headers.get("Authorization", "")
                return who(auth.removeprefix("Bearer ").strip())

            def do_GET(self):
                name = self.guest()
                if name is None:
                    return self.reply(403, {"message": "The admin hasn't invited you, or your invite was "
                                                       "replaced. Ask them for a new one."})
                if self.path != "/state":
                    return self.reply(404, {"message": "Unknown request."})
                server.answer(self, lambda: dict(server.local.state(), you=name))

            def do_POST(self):
                name = self.guest()
                if name is None:
                    return self.reply(403, {"message": "The admin hasn't invited you, or your invite was "
                                                       "replaced. Ask them for a new one."})
                length = self.headers.get("Content-Length") or ""
                length = int(length) if length.isdigit() else 0
                if self.path != "/action" or not 0 < length <= MAX_BODY:
                    return self.reply(400, {"message": "Unknown request."})
                try:
                    body = json.loads(self.rfile.read(length))
                    action, args = body["do"], body.get("args") or {}
                    if not isinstance(action, str) or not isinstance(args, dict):
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    return self.reply(400, {"message": "Unknown request."})
                server.answer(self, lambda: server.act(name, action, args))

        try:
            self.httpd = ThreadingHTTPServer((self.ip, port), Handler)
        except OSError:                        # port taken, e.g. a second deck already open
            self.ip = None
            return
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def answer(self, handler, fn):
        from control import DeckError
        try:
            handler.reply(200, fn())
        except PermissionError as e:
            handler.reply(403, {"message": str(e)})
        except DeckError as e:
            handler.reply(400, {"message": str(e)})
        except ConnectionError:
            handler.reply(503, {"message": "The admin's OBS isn't reachable right now."})
        except Exception:  # noqa: BLE001 - never let one bad request take the door down
            handler.reply(500, {"message": "Something went wrong on the admin's deck."})

    def act(self, name, action, args):
        """Carry out one guest request, after checking they're allowed to."""
        from control import DeckError, valid_box
        local = self.local
        own_cam = f"Cam - {name}"

        if action in ("move", "reset"):
            cam, scene = args.get("cam"), args.get("scene")
            if not isinstance(cam, str) or not isinstance(scene, str):
                raise DeckError("Unknown request.")
            if cam != own_cam and not local.full():
                raise PermissionError("You can only move your own camera.")
            if action == "reset":
                return local.reset(scene, cam)
            return local.move(scene, cam, valid_box(args.get("box"), local.canvas))

        if action == "display_name":           # the name on their own camera only
            return local.set_display_name(name, args.get("name"))
        if action == "camera":                 # Start my camera: always their own camera only
            cam_id = args.get("id")
            if not (isinstance(cam_id, str) and _CAMERA_ID.fullmatch(cam_id)):
                raise DeckError("That camera ID doesn't look right.")
            return local.set_remote_cam(name, cam_id)

        if not local.full():
            raise PermissionError("The admin hasn't given you full control.")
        if action == "switch" and isinstance(args.get("scene"), str):
            if args["scene"] not in local.state()["scenes"]:   # layouts only, never the hidden source library
                raise DeckError("That layout doesn't exist.")
            return local.switch(args["scene"])
        if action == "toggle_record":
            return local.toggle_record()
        if action == "backgrounds":
            return local.backgrounds()
        if action == "set_background":
            path = args.get("path")
            if path != "" and path not in media.list_backgrounds():   # only the admin's saved pictures
                raise DeckError("That picture isn't one of the admin's saved backgrounds.")
            return local.set_background(path)
        if action == "next_background":
            return local.next_background()
        if action == "video_settings":
            return local.video_settings()
        if action == "set_restart":
            return local.set_restart(bool(args.get("on")))
        if action == "play_video":
            vid, start, title = args.get("vid"), args.get("start", 0), args.get("title")
            if vid is not None and not (isinstance(vid, str) and _YOUTUBE_ID.fullmatch(vid)):
                raise DeckError("That isn't a YouTube video.")
            if not isinstance(start, int) or start < 0:
                start = 0
            return local.play_video(vid, start, title[:200] if isinstance(title, str) else None)
        if action == "bg_video":
            import bgcontrol
            try:
                state = bgcontrol.valid_state(args.get("state"))
            except ValueError:
                raise DeckError("That background video doesn't look right.") from None
            return local.set_bg_video(state)
        if action == "background_url":
            url = args.get("url")
            if not isinstance(url, str) or (media.parse_background(url) or {}).get("kind") != "picture_url":
                raise DeckError("That isn't a picture link.")
            return local.add_background_url(url)
        raise DeckError("Unknown request.")
