"""Build the podcast layouts inside OBS, over obs-websocket.

The deck does this by itself the first time it connects, and again from Settings → Rebuild
layouts. It can also be run by hand. Safe to re-run: it deletes and recreates only the scenes it
owns, and leaves your sources alone.

    py C:\\Users\\<you>\\source\\repos\\podcast-deck\\build_scenes.py
"""
import os
import sys
import time

import obsws_python as obs
from obsws_python.error import OBSSDKRequestError

import configfile
import link
import obsconfig
import positions

cfg = configfile.load()
if cfg is None:
    sys.exit("No config.py yet. Open the deck once (Podcast Deck on your desktop) and it sets one up.")

W, H = cfg.CANVAS_W, cfg.CANVAS_H
LIB = "_Sources (don't delete)"   # holds every input once; layouts just reference them
HERE = os.path.dirname(os.path.abspath(__file__))

# Video + Cams box. Older config.py files without these get the defaults.
VIDEO_BOX = (getattr(cfg, "VIDEO_X", 48), getattr(cfg, "VIDEO_Y", 162),
             getattr(cfg, "VIDEO_W", 1344), getattr(cfg, "VIDEO_H", 756))

# ----------------------------------------------------------------------------
# Sources. Input kinds are Windows names; the script picks the installed
# version of each kind (e.g. text_gdiplus_v2 vs _v3) at runtime.
# ----------------------------------------------------------------------------
BASE_SOURCES = {
    "Game":          ("game_capture",    {"capture_mode": "any_fullscreen"}),
    "Desktop":       ("monitor_capture", {}),
    "Browser Window":("window_capture",  {}),
    "Backdrop":      ("color_source",    {"color": 0xFF1B1F2A, "width": W, "height": H}),
    # Picked from the deck's Background menu. Empty until then, so Backdrop shows through.
    "Background":    ("image_source",    {"file": ""}),
    # player.html plays whatever YouTube link the deck's "Play link…" box was given.
    # reroute_audio = "Control audio via OBS", so the video's sound is recorded.
    "Video Panel":   ("browser_source",  {"is_local_file": True, "local_file": os.path.join(HERE, "player.html"),
                                          "width": VIDEO_BOX[2], "height": VIDEO_BOX[3],
                                          "reroute_audio": True, "shutdown": False}),
    "BRB Text":      ("text_gdiplus",    {"text": "Be right back", "font": {"face": "Segoe UI", "size": 120, "style": "Bold"}}),
}
if cfg.DISCORD_STREAMKIT_URL:
    BASE_SOURCES["Discord Voice"] = ("browser_source", {"url": cfg.DISCORD_STREAMKIT_URL, "width": W, "height": H})


def remote_cams():
    """Cams for people joining online: their VDO.Ninja view link, by cam name. Guests' decks send these
    by themselves (Start my camera); REMOTE_CAMS in config.py can add more by hand."""
    found = {name: link.vdo_view(cam_id) for name, cam_id in link.load_remote_cams().items()}
    return {**found, **getattr(cfg, "REMOTE_CAMS", {})}


def sources():
    """Every source, with cams as webcams for people in the room or VDO.Ninja links for people online."""
    found, remote = dict(BASE_SOURCES), remote_cams()
    for name in cfg.CAMS:
        if name in remote:
            found[f"Cam - {name}"] = ("browser_source", {"url": remote[name], "width": 1280, "height": 720,
                                                         "reroute_audio": True})
        else:
            found[f"Cam - {name}"] = ("dshow_input", {})
    return found

# ----------------------------------------------------------------------------
# Layouts. Each entry: (source name, x, y, box width, box height).
# Items are listed bottom → top. Sources are fit inside their box keeping aspect,
# except FILL ones, which cover the whole box and lose their edges instead.
# ----------------------------------------------------------------------------
FILL = {"Background"}

def full(src):
    return (src, 0, 0, W, H)

def cams_bottom_right():
    """Small cams in a row hugging the bottom-right corner."""
    n = len(cfg.CAMS)
    cw, ch, m = cfg.SMALL_CAM_W, cfg.SMALL_CAM_H, cfg.MARGIN
    y = H - ch - m
    x0 = W - m - n * cw - (n - 1) * m
    return [(f"Cam - {name}", x0 + i * (cw + m), y, cw, ch) for i, name in enumerate(cfg.CAMS)]

def cams_split():
    """Everyone equal size across the screen, vertically centered."""
    n = len(cfg.CAMS)
    m = cfg.MARGIN
    cw = (W - (n + 1) * m) // n
    ch = int(cw * 9 / 16)
    y = (H - ch) // 2
    return [(f"Cam - {name}", m + i * (cw + m), y, cw, ch) for i, name in enumerate(cfg.CAMS)]

def cams_column(box):
    """Cams stacked in a column on whichever side of `box` has more room, never overlapping it."""
    x, y, bw, bh = box
    n, m = len(cfg.CAMS), cfg.MARGIN
    left, right = x - 2 * m, W - (x + bw) - 2 * m
    col_w = max(left, right)
    if col_w < 160:
        sys.exit(f"The video box ({bw}x{bh} at {x},{y}) leaves no room for the cams beside it. "
                 f"Make VIDEO_W smaller or move VIDEO_X in config.py.")
    ch = min(col_w * 9 // 16, (H - (n + 1) * m) // n)
    cw = ch * 16 // 9
    col_x = (m if left > right else x + bw + m) + (col_w - cw) // 2
    y0 = (H - (n * ch + (n - 1) * m)) // 2
    return [(f"Cam - {name}", col_x, y0 + i * (ch + m), cw, ch) for i, name in enumerate(cfg.CAMS)]

def backdrop():
    """The plain color with the chosen background picture over it."""
    return [full("Backdrop"), full("Background")]

def with_discord(items):
    return items + ([full("Discord Voice")] if cfg.DISCORD_STREAMKIT_URL else [])

LAYOUTS = {
    "Gameplay + Cams":  with_discord([full("Game")] + cams_bottom_right()),
    "Browser + Cams":   with_discord([full("Browser Window")] + cams_bottom_right()),
    "Just Us":          with_discord(backdrop() + cams_split()),
    "Gameplay Only":    [full("Game")],
    "Desktop + Cams":   with_discord([full("Desktop")] + cams_bottom_right()),
    "Be Right Back":    backdrop() + [("BRB Text", 0, 0, W, H)],
    "Video + Cams":     with_discord(backdrop() + [("Video Panel", *VIDEO_BOX)] + cams_column(VIDEO_BOX)),
}


def main():
    try:
        cl = obs.ReqClient(host=cfg.OBS_HOST, port=obsconfig.port(cfg), password=obsconfig.password(cfg), timeout=5)
    except Exception as e:  # noqa: BLE001
        sys.exit(obsconfig.problem() or f"Couldn't connect to OBS. Is it open? ({e})")
    build(cl)
    print("\nDone. Pick webcams and the browser window from the deck: Settings.")


def build(cl, log=print, keep_scene=None):
    """Create the sources and layouts in OBS. keep_scene: stay on this layout afterwards if it still exists."""
    SOURCES = sources()
    installed_kinds = cl.get_input_kind_list(False).input_kinds
    def resolve(kind):
        if kind in installed_kinds:
            return kind
        hits = sorted(k for k in installed_kinds if k.startswith(kind))
        if not hits:
            sys.exit(f"OBS has no input kind like '{kind}'. Installed: {installed_kinds}")
        return hits[-1]

    scenes = {s["sceneName"] for s in cl.get_scene_list().scenes}
    inputs = {i["inputName"]: i["inputKind"] for i in cl.get_input_list().inputs}

    # 1. Library scene with every source created exactly once.
    if LIB not in scenes:
        cl.create_scene(LIB)
    for name, (kind, settings) in SOURCES.items():
        if name in inputs and name.startswith("Cam - ") and not inputs[name].startswith(kind):
            cl.remove_input(name)             # switched between a webcam and a remote link
            log(f"  replaced source {name}")
            del inputs[name]
        if name in inputs:
            continue
        for _ in range(20):                   # a just-removed source can hold its name for a moment
            try:
                cl.create_input(LIB, name, resolve(kind), settings, False)
                break
            except OBSSDKRequestError as e:
                if e.code != 601:             # 601: a source with that name still exists
                    raise
                time.sleep(0.1)
        log(f"  created source  {name}")
    for name, url in remote_cams().items():   # keep remote links current if they change
        if f"Cam - {name}" in SOURCES:
            cl.set_input_settings(f"Cam - {name}", {"url": url}, True)
    assign_webcams(cl, [n for n, (kind, _) in SOURCES.items() if n.startswith("Cam - ") and kind == "dshow_input"], log)
    # Keep the video page sized to the box and pointed at this folder's player.html.
    cl.set_input_settings("Video Panel", {k: SOURCES["Video Panel"][1][k]
                                          for k in ("local_file", "width", "height")}, True)

    # 2. Layout scenes, rebuilt from scratch.
    item_ids = {}
    for scene, items in LAYOUTS.items():
        if scene in scenes:
            cl.remove_scene(scene)
        cl.create_scene(scene)
        for src, x, y, bw, bh in items:
            item_id = cl.create_scene_item(scene, src, True).scene_item_id
            cl.set_scene_item_transform(scene, item_id, positions.box_transform(x, y, bw, bh, fill=src in FILL))
            item_ids[scene, src] = item_id
        log(f"  built layout    {scene}")

    # 3. Remember each layout's usual cam spots (the deck's Reset button goes back to them), then
    #    put back any cams people have dragged somewhere else from their decks.
    positions.write(cl, positions.DEFAULTS, {
        scene: {src: [x, y, bw, bh] for src, x, y, bw, bh in items if src.startswith("Cam - ")}
        for scene, items in LAYOUTS.items()})
    for name in cfg.CAMS:
        cam = f"Cam - {name}"
        for scene, box in positions.read(cl, positions.cam_slot(cam), {}).items():
            if (scene, cam) in item_ids:
                cl.set_scene_item_transform(scene, item_ids[scene, cam], positions.box_transform(*box))
                log(f"  kept moved cam  {cam} in {scene}")

    cl.set_current_program_scene(keep_scene if keep_scene in LAYOUTS else "Gameplay + Cams")


def webcams(cl, cam):
    """(name, id) of every camera device OBS can see, from a webcam source's own device list."""
    items = cl.get_input_properties_list_property_items(cam, "video_device_id").property_items
    return [(i["itemName"], i["itemValue"]) for i in items if i["itemValue"] and i.get("itemEnabled", True)]


def assign_webcams(cl, cams, log=print):
    """Give each webcam source with no device picked yet the next unused camera, so it just works."""
    if not cams:
        return
    picked = {c: cl.get_input_settings(c).input_settings.get("video_device_id", "") for c in cams}
    free = [(n, v) for n, v in webcams(cl, cams[0])
            if v not in picked.values() and "virtual" not in n.lower()]   # skip OBS's own virtual camera
    for cam in cams:
        if not picked[cam] and free:
            name, value = free.pop(0)
            cl.set_input_settings(cam, {"video_device_id": value}, True)
            log(f"  picked webcam   {name} for {cam}")


if __name__ == "__main__":
    main()
