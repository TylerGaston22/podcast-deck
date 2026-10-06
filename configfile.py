"""Reading and writing config.py, so the deck's first-launch window and Settings can fill it in."""
import importlib
import os
import re
import sys

import media

PATH = os.path.join(media.APP_DIR, "config.py")


def _example():
    for folder in (media.APP_DIR, getattr(sys, "_MEIPASS", "")):   # _MEIPASS: inside the packaged .exe
        path = os.path.join(folder, "config.example.py")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError("config.example.py is missing")


def load():
    """The config module, or None if there's no config.py yet."""
    if media.APP_DIR not in sys.path:
        sys.path.insert(0, media.APP_DIR)
    if not os.path.exists(PATH):
        return None
    if "config" in sys.modules:
        return importlib.reload(sys.modules["config"])
    return importlib.import_module("config")


def _with(text, values):
    for key, value in values.items():
        line = f"{key} = {value!r}"
        text, n = re.subn(rf"^{key} = .*$", lambda _m: line, text, count=1, flags=re.M)
        if not n:
            text += f"\n{line}\n"
    return text


def create(**values):
    """Write config.py from config.example.py, with these settings filled in."""
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(_with(_example(), values))


def update(**values):
    """Change settings in an existing config.py, keeping everything else as it is."""
    with open(PATH, encoding="utf-8") as f:
        text = f.read()
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(_with(text, values))
