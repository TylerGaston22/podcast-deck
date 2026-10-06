"""OBS's remote-control (WebSocket) settings, read straight from OBS's own settings file.

So nobody has to copy the OBS password anywhere: on the PC that runs OBS, the deck and
build_scenes.py read it themselves. If remote control is switched off, it's switched on here,
but only while OBS is closed, because OBS rewrites the file when it exits.
"""
import json
import os
import secrets
import subprocess

PATH = os.path.join(os.environ.get("APPDATA", ""), "obs-studio", "plugin_config", "obs-websocket", "config.json")
PLACEHOLDERS = ("", "CHANGE_ME")


def read():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def password(cfg):
    """The password in config.py if one was typed in, otherwise OBS's own."""
    typed = getattr(cfg, "OBS_PASSWORD", "")
    if typed not in PLACEHOLDERS:
        return typed
    settings = read() or {}
    return settings.get("server_password") if settings.get("auth_required", True) else None


def port(cfg):
    return (read() or {}).get("server_port") or getattr(cfg, "OBS_PORT", 4455)


def obs_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True, text=True,
                             timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "obs64.exe" in out.lower()


def problem():
    """Why the deck can't reach OBS, in plain words, fixing it first when it safely can. None if unknown."""
    settings = read()
    if settings and settings.get("server_enabled"):
        return None                            # remote control is on; OBS is probably just closed
    if not os.path.isdir(os.path.join(os.environ.get("APPDATA", ""), "obs-studio")):
        return "OBS isn't set up on this PC yet. Install OBS from obsproject.com and open it once."
    if obs_running():
        return "OBS's remote control is off. Close OBS once and the deck will turn it on, then open OBS again."
    settings = settings or {"server_port": 4455, "alerts_enabled": False, "first_load": False}
    settings["server_enabled"] = True
    if not settings.get("server_password"):
        settings["server_password"], settings["auth_required"] = secrets.token_urlsafe(12), True
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
    except OSError:
        return "Couldn't turn on OBS's remote control. In OBS: Tools → WebSocket Server Settings → Enable."
    return "Turned on OBS's remote control. Open OBS and the deck connects by itself."
