"""Build the podcast layouts inside OBS, over obs-websocket.

Run once (and again any time you change config.py). Safe to re-run: it deletes
and recreates only the scenes it owns, and leaves your sources alone.

    py C:\\Users\\<you>\\source\\repos\\podcast-deck\\build_scenes.py
"""
import sys

import obsws_python as obs

try:
    import config as cfg
except ModuleNotFoundError:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(f"No config.py yet. Copy {here}\\config.example.py to {here}\\config.py and fill in your OBS password.")

W, H = cfg.CANVAS_W, cfg.CANVAS_H
LIB = "_Sources (don't delete)"   # holds every input once; layouts just reference them

# ----------------------------------------------------------------------------
# Sources. Input kinds are Windows names; the script picks the installed
# version of each kind (e.g. text_gdiplus_v2 vs _v3) at runtime.
# ----------------------------------------------------------------------------
SOURCES = {
    "Game":          ("game_capture",    {"capture_mode": "any_fullscreen"}),
    "Desktop":       ("monitor_capture", {}),
    "Browser Window":("window_capture",  {}),
    "Backdrop":      ("color_source",    {"color": 0xFF1B1F2A, "width": W, "height": H}),
    "BRB Text":      ("text_gdiplus",    {"text": "Be right back", "font": {"face": "Segoe UI", "size": 120, "style": "Bold"}}),
}
for name in cfg.CAMS:
    SOURCES[f"Cam - {name}"] = ("dshow_input", {})
if cfg.DISCORD_STREAMKIT_URL:
    SOURCES["Discord Voice"] = ("browser_source", {"url": cfg.DISCORD_STREAMKIT_URL, "width": W, "height": H})

# ----------------------------------------------------------------------------
# Layouts. Each entry: (source name, x, y, box width, box height).
# Items are listed bottom → top. Sources are fit inside their box keeping aspect.
# ----------------------------------------------------------------------------
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

def with_discord(items):
    return items + ([full("Discord Voice")] if cfg.DISCORD_STREAMKIT_URL else [])

LAYOUTS = {
    "Gameplay + Cams":  with_discord([full("Game")] + cams_bottom_right()),
    "Browser + Cams":   with_discord([full("Browser Window")] + cams_bottom_right()),
    "Just Us":          with_discord([full("Backdrop")] + cams_split()),
    "Gameplay Only":    [full("Game")],
    "Desktop + Cams":   with_discord([full("Desktop")] + cams_bottom_right()),
    "Be Right Back":    [full("Backdrop"), ("BRB Text", 0, 0, W, H)],
}


def main():
    try:
        cl = obs.ReqClient(host=cfg.OBS_HOST, port=cfg.OBS_PORT, password=cfg.OBS_PASSWORD, timeout=5)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Couldn't connect to OBS at {cfg.OBS_HOST}:{cfg.OBS_PORT}. "
                 f"Is OBS open and the WebSocket server enabled? ({e})")

    installed_kinds = cl.get_input_kind_list(False).input_kinds
    def resolve(kind):
        if kind in installed_kinds:
            return kind
        hits = sorted(k for k in installed_kinds if k.startswith(kind))
        if not hits:
            sys.exit(f"OBS has no input kind like '{kind}'. Installed: {installed_kinds}")
        return hits[-1]

    scenes = {s["sceneName"] for s in cl.get_scene_list().scenes}
    inputs = {i["inputName"] for i in cl.get_input_list().inputs}

    # 1. Library scene with every source created exactly once.
    if LIB not in scenes:
        cl.create_scene(LIB)
    for name, (kind, settings) in SOURCES.items():
        if name in inputs:
            continue
        cl.create_input(LIB, name, resolve(kind), settings, False)
        print(f"  created source  {name}")

    # 2. Layout scenes, rebuilt from scratch.
    for scene, items in LAYOUTS.items():
        if scene in scenes:
            cl.remove_scene(scene)
        cl.create_scene(scene)
        for src, x, y, bw, bh in items:
            item_id = cl.create_scene_item(scene, src, True).scene_item_id
            cl.set_scene_item_transform(scene, item_id, {
                "positionX": x, "positionY": y,
                "alignment": 5,                       # top-left anchor
                "boundsType": "OBS_BOUNDS_SCALE_INNER",
                "boundsAlignment": 0,                 # center within box
                "boundsWidth": bw, "boundsHeight": bh,
            })
        print(f"  built layout    {scene}")

    cl.set_current_program_scene("Gameplay + Cams")
    print("\nDone. In OBS: double-click each 'Cam - …' source to pick its webcam, "
          "and 'Browser Window' to pick the browser.\n"
          "Tip: Edit Transform → 'Crop to Bounding Box' on the Just Us cams makes them fill their panels.")


if __name__ == "__main__":
    main()
