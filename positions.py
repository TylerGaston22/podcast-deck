"""Camera spots and the guest permission switch, stored inside the admin's OBS.

OBS keeps these in its profile (obs-websocket "persistent data"), so they survive restarts and
re-running build_scenes.py. Boxes are (x, y, width, height) in
canvas pixels, the same shape build_scenes.py uses for layouts.
"""
REALM = "OBS_WEBSOCKET_DATA_REALM_PROFILE"
GUESTS_FULL_CONTROL = "podcast_deck.guests_full_control"   # True: guests get every admin control
DEFAULTS = "podcast_deck.default_positions"     # {layout: {cam source: box}}, written by build_scenes.py
NAME_TAGS = "podcast_deck.name_tags"            # show names on cams (default on)
BG_LAYOUTS = "podcast_deck.bg_layouts"          # {background picture file name: layout to switch to}


def cam_slot(cam):
    """Each camera's moved spots live in their own slot ({layout: box}), so two people dragging at
    once never overwrite each other."""
    return f"podcast_deck.cam.{cam}"


def read(cl, slot, default=None):
    value = cl.get_persistent_data(REALM, slot).slot_value
    return default if value is None else value


def write(cl, slot, value):
    cl.set_persistent_data(REALM, slot, value)


def save(cl, cam, layout, box):
    spots = read(cl, cam_slot(cam), {})
    spots[layout] = [round(v) for v in box]
    write(cl, cam_slot(cam), spots)


def forget(cl, cam, layout):
    spots = read(cl, cam_slot(cam), {})
    if spots.pop(layout, None) is not None:
        write(cl, cam_slot(cam), spots)


def box_transform(x, y, w, h, fill=False, align=0):
    """OBS transform that fits a source inside a box (or covers it, when `fill`), anchored top-left.
    align: where in the box the source sits (0 = center, 9 = bottom-left)."""
    return {
        "positionX": x, "positionY": y,
        "alignment": 5,                       # top-left anchor
        "boundsType": "OBS_BOUNDS_SCALE_OUTER" if fill else "OBS_BOUNDS_SCALE_INNER",
        "boundsAlignment": align,
        "boundsWidth": w, "boundsHeight": h,
    }


def tag_name(cam):
    """The name tag source that goes with a cam: "Cam - Host 1" → "Name - Host 1"."""
    return "Name - " + cam.removeprefix("Cam - ")


def tag_box(box):
    """Where a cam's name tag sits: the bottom-left corner of the cam, sized to the cam."""
    x, y, w, h = box
    th, m = max(18, h * 0.13), max(4, h * 0.04)
    return x + m, y + h - th - m, w * 0.7, th


def tag_transform(box):
    return box_transform(*tag_box(box), align=9)


def place_tag(cl, scene, cam, box):
    """Move a cam's name tag along with it. Layouts without name tags are fine."""
    from obsws_python.error import OBSSDKRequestError
    try:
        tag_id = cl.get_scene_item_id(scene, tag_name(cam)).scene_item_id
    except OBSSDKRequestError:
        return
    cl.set_scene_item_transform(scene, tag_id, tag_transform(box))


def item_box(t):
    """The on-screen box of a scene item, from its OBS transform. Works for items placed by hand too."""
    if t.get("boundsType", "OBS_BOUNDS_NONE") != "OBS_BOUNDS_NONE":
        w, h = t["boundsWidth"], t["boundsHeight"]
    else:
        w, h = t["width"], t["height"]
    x, y, align = t["positionX"], t["positionY"], t.get("alignment", 5)
    if not align & 1:                         # anchor isn't the left edge: right edge or center
        x -= w if align & 2 else w / 2
    if not align & 4:                         # anchor isn't the top edge: bottom edge or center
        y -= h if align & 8 else h / 2
    return x, y, w, h


def clamp_move(box, dx, dy, canvas):
    """Box moved by (dx, dy), kept fully on screen."""
    x, y, w, h = box
    cw, ch = canvas
    return min(max(0, x + dx), cw - w), min(max(0, y + dy), ch - h), w, h


def clamp_resize(box, dx, canvas, min_w):
    """Box widened by dx from its top-left corner, keeping its shape and staying on screen."""
    x, y, w, h = box
    cw, ch = canvas
    aspect = h / w
    new_w = max(min_w, w + dx)
    new_w = min(new_w, cw - x, (ch - y) / aspect)
    return x, y, new_w, new_w * aspect
