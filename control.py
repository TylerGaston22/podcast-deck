"""Everything the deck can do, behind one interface.

Local controls the OBS on this PC (the admin's deck uses it, and so does its door for guests).
Remote asks the admin's deck to do things instead (guests' decks use it). A guest's deck never
talks to anyone's OBS, so no OBS password ever leaves the admin's PC.
"""
import functools
import json
import math
import os
import threading
import urllib.error
import urllib.request

import obsws_python as obs
from obsws_python.error import OBSSDKRequestError

import bgcontrol
import link
import media
import obsconfig
import positions

HIDDEN_LIB = "_Sources (don't delete)"
HIDDEN = {HIDDEN_LIB}
NOT_BUILT = "Something the deck made is missing in OBS. Click Settings → Cameras → Repair layouts to put it back."
OBS_CLOSED = "OBS not reachable. Open OBS; this window connects by itself."
NOW_SLOT = "podcast_deck.now"                  # {"bg": live background video, "video": live Video + Cams video}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class DeckError(Exception):
    """A problem to show the person, in plain words."""


def _locked(fn):
    """One OBS request at a time: the window and guests' requests share one connection."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            try:
                return fn(self, *args, **kwargs)
            except OBSSDKRequestError as e:
                raise DeckError(NOT_BUILT if e.code == 600 else str(e)) from e   # 600: no source by that name
            except DeckError:
                raise
            except SystemExit as e:            # build_scenes.py explaining a config problem
                raise DeckError(str(e)) from e
            except ConnectionError:
                self.cl = None
                raise
            except Exception as e:
                self.cl = None
                raise ConnectionError(OBS_CLOSED) from e
    return wrapper


class Local:
    """Controls the OBS on this PC, and only this PC."""

    def __init__(self, cfg):
        if cfg.OBS_HOST not in LOCAL_HOSTS:
            raise DeckError("OBS_HOST must be \"localhost\". The deck only controls the OBS on its own PC.")
        self.cfg = cfg
        self.cl = None
        self.lock = threading.Lock()
        self.canvas = (cfg.CANVAS_W, cfg.CANVAS_H)
        self.ids = {}                          # (layout, source name) → OBS scene item id
        self.checked_layouts = False           # first connection: build the layouts if OBS has none yet
        self.rebuild_waiting = False           # a guest's camera arrived mid-recording; rebuild after
        self.note = None                       # something the window should mention once
        self.last_scene = None                 # switching to a layout puts up its default background
        self.shapes = {}                       # cam source → its camera's (width, height), to fit boxes to it
        self.webcam_tries = 15                 # polls left to give webcams without a device one (about 30 s)
        self.bg_video = None                   # the live background video, read by OBS's Background Video page
        self.video = None                      # the Video + Cams video, run from the browser control page
        self.now_loaded = False                # both are kept in OBS, so they survive restarts

    def client(self):
        """Connect with OBS's own password, read from OBS's settings, so nobody has to copy it."""
        if self.cl is None:
            try:
                cl = obs.ReqClient(host=self.cfg.OBS_HOST, port=obsconfig.port(self.cfg),
                                   password=obsconfig.password(self.cfg), timeout=3)
            except Exception as e:  # noqa: BLE001
                raise ConnectionError(obsconfig.problem() or OBS_CLOSED) from e
            video = cl.get_video_settings()
            self.canvas = (video.base_width, video.base_height)
            self.cl = cl
        return self.cl

    def _build(self, cl, keep_scene=None):
        import build_scenes                    # needs config.py, so only imported once there is one
        build_scenes.build(cl, log=lambda _line: None, keep_scene=keep_scene)
        self.ids.clear()

    def _pick_webcams(self, cl):
        """Give every webcam source with no device picked yet the next unused camera. True when none are left
        without one (or there's nothing to pick from)."""
        import build_scenes
        cams = []
        for name in self.cfg.CAMS:
            try:
                found = cl.get_input_settings(f"Cam - {name}")
            except OBSSDKRequestError:
                continue
            if found.input_kind.startswith("dshow_input"):
                cams.append(f"Cam - {name}")
        before = {c: cl.get_input_settings(c).input_settings.get("video_device_id") for c in cams}
        if all(before.values()):
            return True
        picked = []
        build_scenes.assign_webcams(cl, cams, log=picked.append)
        if picked:
            self.note = "Webcam picked: " + picked[0].split("picked webcam", 1)[-1].strip().split(" for ")[0]
        return all(cl.get_input_settings(c).input_settings.get("video_device_id") for c in cams)

    @_locked
    def rebuild(self):
        """Settings → Repair layouts: put back anything the deck made, and rebuild the layouts."""
        cl = self.client()
        self._build(cl, keep_scene=cl.get_current_program_scene().current_program_scene_name)

    @_locked
    def state(self):
        cl = self.client()
        scenes = [s["sceneName"] for s in reversed(cl.get_scene_list().scenes)]
        record = cl.get_record_status()
        recording = record.output_active
        if not self.checked_layouts:
            self.checked_layouts = True
            for page in ("Video Panel", "Background Video"):   # load the current player pages
                try:
                    cl.press_input_properties_button(page, "refreshnocache")
                except OBSSDKRequestError:
                    pass
            if HIDDEN_LIB not in scenes:       # a fresh OBS: set everything up without being asked
                self._build(cl)
                self.note = "Layouts set up in OBS. Pick webcams any time in Settings."
                scenes = [s["sceneName"] for s in reversed(cl.get_scene_list().scenes)]
            else:
                self._reset_all(cl)            # a new session starts from the default camera spots
            start = positions.read(cl, positions.START_LAYOUT, "")
            if start and start in scenes:      # Start on this layout
                cl.set_current_program_scene(start)
        if self.webcam_tries > 0:              # OBS can take a moment to list webcams after making a source
            self.webcam_tries -= 1
            if self._pick_webcams(cl):
                self.webcam_tries = 0
        if self.rebuild_waiting and not recording:
            self.rebuild_waiting = False
            self._build(cl, keep_scene=cl.get_current_program_scene().current_program_scene_name)
            self.note = "A guest's camera was added."
        current = cl.get_current_program_scene().current_program_scene_name
        if current != self.last_scene:         # however the layout changed (deck, hotkey, guest, OBS itself)
            self.last_scene = current
            self._layout_default(cl, current)
        items = []
        for i in cl.get_scene_item_list(current).scene_items:
            name = i["sourceName"]
            t = i["sceneItemTransform"]
            if name.startswith("Cam - ") and t.get("sourceWidth") and t.get("sourceHeight"):
                shape = (t["sourceWidth"], t["sourceHeight"])
                if self.shapes.get(name) not in (None, shape):   # a camera changed shape: refit it everywhere
                    self.shapes[name] = shape
                    self._refit(cl, name)
                self.shapes[name] = shape
            if i["sceneItemEnabled"] and (name.startswith("Cam - ") or name == "Video Panel"):
                self.ids[current, name] = i["sceneItemId"]
                items.append({"name": name, "box": list(positions.item_box(i["sceneItemTransform"]))})
        note, self.note = self.note, None
        return {"scenes": [s for s in scenes if s not in HIDDEN], "current": current,
                "recording": recording, "rec_ms": getattr(record, "output_duration", 0), "full": self._full(cl), "items": items, "canvas": list(self.canvas),
                "note": note, "now": self._now(cl), "meta": self._meta(cl), "names": positions.read(cl, positions.DISPLAY_NAMES, {})}

    def _now(self, cl):
        """What's showing: the background (video title or picture name) and the Video + Cams video."""
        if not self.now_loaded:
            self.now_loaded = True
            saved = positions.read(cl, NOW_SLOT, {})
            self.bg_video = saved.get("bg")
            self.video = saved.get("video") if isinstance(saved.get("video"), dict) else None
        if self.bg_video:
            background = "▶ " + (self.bg_video.get("title") or "video")
        else:
            try:
                path = cl.get_input_settings("Background").input_settings.get("file", "")
            except OBSSDKRequestError:
                path = ""
            background = os.path.splitext(os.path.basename(path))[0] if path else "plain color"
        return {"background": background, "video": (self.video.get("title") or "video") if self.video else None}

    def _save_now(self, cl):
        positions.write(cl, NOW_SLOT, {"bg": self.bg_video, "video": self.video})

    @_locked
    def set_bg_video(self, state):
        """Put a video in the background (or take it away with None). OBS's page picks it up in a moment."""
        self.bg_video = bgcontrol.valid_state(state)
        self._save_now(self.client())

    def live_bg(self):
        return self.bg_video

    @_locked
    def set_video(self, state):
        """Put a video in the Video + Cams box (or empty it with None). The browser control page runs it."""
        self.video = bgcontrol.valid_state(state)
        self._save_now(self.client())

    def live(self, channel):
        """What OBS's player page for a channel ("bg" or "video") should show right now."""
        return self.bg_video if channel == "bg" else self.video

    def _full(self, cl):
        return bool(positions.read(cl, positions.GUESTS_FULL_CONTROL, False))

    @_locked
    def full(self):
        return self._full(self.client())

    @_locked
    def set_full(self, on):
        positions.write(self.client(), positions.GUESTS_FULL_CONTROL, bool(on))

    @_locked
    def switch(self, scene):
        cl = self.client()
        cl.set_current_program_scene(scene)
        self.last_scene = scene
        self._layout_default(cl, scene)

    # --- Each layout's backgrounds: a default, plus extras to flip between ----------------------
    def _layout_bgs(self, cl):
        return positions.read(cl, positions.LAYOUT_BGS, {})

    def _layout_pictures(self, cl, scene):
        """This layout's backgrounds as full paths, default first. Pictures deleted from the folder are skipped."""
        entry = self._layout_bgs(cl).get(scene, {})
        names = ([entry["default"]] if entry.get("default") else []) + [
            n for n in entry.get("extras", []) if n != entry.get("default")]
        paths = [os.path.join(media.BACKGROUNDS, n) for n in names]
        return [p for p in paths if os.path.exists(p)]

    def _layout_default(self, cl, scene):
        """Put up this layout's default background, if it has one."""
        entry = self._layout_bgs(cl).get(scene, {})
        path = os.path.join(media.BACKGROUNDS, entry["default"]) if entry.get("default") else ""
        if not path or not os.path.exists(path):
            return
        try:
            cl.set_input_settings("Background", {"file": path}, True)
        except OBSSDKRequestError:
            return
        if self.bg_video:
            self.bg_video = None
            self._save_now(cl)

    @_locked
    def set_layout_bgs(self, layout, default=None, extras=None):
        """Settings: a layout's default background (file name, "" for none) and its extra ones."""
        cl = self.client()
        found = self._layout_bgs(cl)
        entry = found.setdefault(layout, {"default": "", "extras": []})
        if default is not None:
            entry["default"] = default
        if extras is not None:
            entry["extras"] = list(extras)
        positions.write(cl, positions.LAYOUT_BGS, found)
        if layout == self.last_scene and default:
            self._layout_default(cl, layout)

    def add_layout_picture(self, layout, path):
        """Settings → Add picture…: save a picture of your own and add it to this layout (as its default if
        it has none yet). Returns the picture's file name."""
        try:
            name = os.path.basename(media.add_background(path))
        except OSError as e:
            raise DeckError(f"Couldn't copy that picture into the backgrounds folder. ({e})") from e
        entry = self.options()["layout_bgs"].get(layout, {"default": "", "extras": []})
        self.set_layout_bgs(layout, default=entry.get("default") or name,
                            extras=list(dict.fromkeys(entry.get("extras", []) + [name])))
        return name

    @_locked
    def make_default(self, path):
        """Background ▾ → Make this the default for the current layout."""
        cl = self.client()
        found = self._layout_bgs(cl)
        entry = found.setdefault(self.last_scene, {"default": "", "extras": []})
        old = [entry["default"]] if entry.get("default") else []   # the old default stays as an extra
        entry["default"] = os.path.basename(path)
        entry["extras"] = list(dict.fromkeys(entry.get("extras", []) + old + [entry["default"]]))
        positions.write(cl, positions.LAYOUT_BGS, found)
        return self.last_scene

    @_locked
    def toggle_record(self):
        self.client().toggle_record()

    def _place(self, cl, scene, cam, box):
        """Move a camera, looking its id up again if the layouts were rebuilt since it was cached. The box
        takes the camera's own shape, inside the spot asked for."""
        box = positions.fit_box(box, *self.shapes.get(cam, (0, 0)))
        for attempt in (1, 2):
            if (scene, cam) not in self.ids:
                self.ids[scene, cam] = cl.get_scene_item_id(scene, cam).scene_item_id
            try:
                cl.set_scene_item_transform(scene, self.ids[scene, cam], positions.box_transform(*box))
                return positions.place_tag(cl, scene, cam, box)
            except OBSSDKRequestError as e:
                if e.code != 600 or attempt == 2:
                    raise
                del self.ids[scene, cam]

    @_locked
    def move(self, scene, cam, box):
        """Move a camera for this session only. Defaults change only from Settings."""
        self._place(self.client(), scene, cam, box)

    def _default(self, cl, scene, cam):
        """A camera's default spot in a layout: the one saved in Settings, or the layout's own."""
        return (positions.read(cl, positions.cam_slot(cam), {}).get(scene)
                or positions.read(cl, positions.DEFAULTS, {}).get(scene, {}).get(cam))

    @_locked
    def reset(self, scene, cam):
        """Put a camera back on its default spot. False if the layout has none."""
        cl = self.client()
        box = self._default(cl, scene, cam)
        if box is None:
            return False
        self._place(cl, scene, cam, box)
        return True

    def _reset_all(self, cl):
        layouts = positions.read(cl, positions.DEFAULTS, {})
        for scene, cams in layouts.items():
            for cam in cams:
                try:
                    self._place(cl, scene, cam, self._default(cl, scene, cam))
                except OBSSDKRequestError:
                    pass                       # that layout or cam isn't in OBS any more

    # --- Tabs and marker colors for the layout list -------------------------------------------
    def _meta(self, cl):
        found = positions.read(cl, positions.LAYOUT_META, {})
        tabs = [t for t in found.get("tabs", []) if isinstance(t, str) and t != positions.GENERAL]
        return {"tabs": [positions.GENERAL] + tabs, "tab": found.get("tab", {}), "color": found.get("color", {}),
                "order": [n for n in found.get("order", []) if isinstance(n, str)]}

    def _save_meta(self, cl, meta):
        positions.write(cl, positions.LAYOUT_META, {"tabs": meta["tabs"][1:], "tab": meta["tab"], "color": meta["color"],
                                                    "order": meta.get("order", [])})

    @_locked
    def set_order(self, order):
        """Drag to reorder: the deck's own order for layouts (OBS's scene list stays as it is)."""
        cl = self.client()
        meta = self._meta(cl)
        meta["order"] = [n for n in order if isinstance(n, str)]
        self._save_meta(cl, meta)

    @_locked
    def add_tab(self, name):
        cl = self.client()
        meta, name = self._meta(cl), positions.clean_display_name(name)[:24]
        if not name or name in meta["tabs"]:
            raise DeckError("Give the tab a new name." if not name else f"There's already a tab called {name}.")
        meta["tabs"].append(name)
        self._save_meta(cl, meta)
        return name

    @_locked
    def rename_tab(self, old, new):
        cl = self.client()
        meta, new = self._meta(cl), positions.clean_display_name(new)[:24]
        if old == positions.GENERAL or old not in meta["tabs"]:
            raise DeckError("General can't be renamed.")
        if not new or new in meta["tabs"]:
            raise DeckError(f"There's already a tab called {new}." if new else "Give the tab a name.")
        meta["tabs"][meta["tabs"].index(old)] = new
        meta["tab"] = {k: (new if v == old else v) for k, v in meta["tab"].items()}
        self._save_meta(cl, meta)
        return new

    @_locked
    def delete_tab(self, name):
        """Delete a tab. Its layouts go back to General."""
        cl = self.client()
        meta = self._meta(cl)
        if name == positions.GENERAL or name not in meta["tabs"]:
            raise DeckError("General can't be deleted.")
        meta["tabs"].remove(name)
        meta["tab"] = {k: v for k, v in meta["tab"].items() if v != name}
        self._save_meta(cl, meta)

    @_locked
    def set_layout_tab(self, layout, tab):
        cl = self.client()
        meta = self._meta(cl)
        if tab not in meta["tabs"]:
            raise DeckError("That tab doesn't exist any more.")
        if tab == positions.GENERAL:
            meta["tab"].pop(layout, None)
        else:
            meta["tab"][layout] = tab
        self._save_meta(cl, meta)

    @_locked
    def set_layout_color(self, layout, color):
        """A layout's marker color ("" = automatic, by what kind of layout it is)."""
        cl = self.client()
        meta = self._meta(cl)
        if color:
            meta["color"][layout] = color
        else:
            meta["color"].pop(layout, None)
        self._save_meta(cl, meta)

    # --- One layout's menu (⋯ / right-click on its row) --------------------------------------
    def _move_key(self, cl, slot, old, new):
        found = positions.read(cl, slot, {})
        if old in found:
            found[new] = found.pop(old)
            positions.write(cl, slot, found)

    @_locked
    def rename_layout(self, old, new):
        """Rename a layout, in OBS too. Everything kept for it (camera spots, backgrounds, start) follows."""
        cl = self.client()
        new = positions.clean_display_name(new)[:40]
        scenes = [s["sceneName"] for s in cl.get_scene_list().scenes]
        if not new or new == old:
            return old
        if new in scenes or new in HIDDEN:
            raise DeckError(f"There's already a layout called {new}.")
        cl.set_scene_name(old, new)
        renames = positions.read(cl, positions.RENAMES, {})
        original = next((k for k, v in renames.items() if v == old), old)
        renames[original] = new
        positions.write(cl, positions.RENAMES, renames)
        for slot in (positions.DEFAULTS, positions.LAYOUT_BGS):
            self._move_key(cl, slot, old, new)
        for name in self.cfg.CAMS:
            self._move_key(cl, positions.cam_slot(f"Cam - {name}"), old, new)
        if positions.read(cl, positions.START_LAYOUT, "") == old:
            positions.write(cl, positions.START_LAYOUT, new)
        meta = self._meta(cl)
        for key in ("tab", "color"):
            if old in meta[key]:
                meta[key][new] = meta[key].pop(old)
        meta["order"] = [new if n == old else n for n in meta["order"]]
        self._save_meta(cl, meta)
        if self.last_scene == old:
            self.last_scene = new
        self.ids.clear()
        return new

    @_locked
    def delete_layout(self, name):
        """Delete a layout from OBS. Repair won't bring it back; Bring back deleted layouts will."""
        cl = self.client()
        if name in HIDDEN:
            raise DeckError("That one holds every source; it can't be deleted.")
        renames = positions.read(cl, positions.RENAMES, {})
        original = next((k for k, v in renames.items() if v == name), name)
        import build_scenes
        if original in build_scenes.LAYOUTS:   # one the deck builds: remember it was deleted on purpose
            removed = positions.read(cl, positions.REMOVED, [])
            positions.write(cl, positions.REMOVED, sorted(set(removed) | {original}))
        cl.remove_scene(name)
        found = positions.read(cl, positions.LAYOUT_BGS, {})
        if found.pop(name, None) is not None:
            positions.write(cl, positions.LAYOUT_BGS, found)
        if positions.read(cl, positions.START_LAYOUT, "") == name:
            positions.write(cl, positions.START_LAYOUT, "")
        meta = self._meta(cl)
        meta["tab"].pop(name, None)
        meta["color"].pop(name, None)
        self._save_meta(cl, meta)
        self.ids.clear()

    COPYABLE = ("positionX", "positionY", "rotation", "scaleX", "scaleY", "alignment", "boundsType",
                "boundsAlignment", "boundsWidth", "boundsHeight", "cropLeft", "cropRight", "cropTop", "cropBottom")

    @_locked
    def new_layout(self, name, start_from, tab):
        """＋ New layout: a copy of an existing layout, or (start_from "") the background with every cam side
        by side. It goes into `tab` and gets usual cam spots, so Reset camera works in it."""
        import build_scenes
        cl = self.client()
        name = positions.clean_display_name(name)[:40]
        scenes = [s["sceneName"] for s in cl.get_scene_list().scenes]
        if not name:
            raise DeckError("Give the layout a name.")
        if name in scenes or name in HIDDEN:
            raise DeckError(f"There's already a layout called {name}.")
        cl.create_scene(name)
        spots = {}
        if start_from:
            for item in cl.get_scene_item_list(start_from).scene_items:   # bottom to top
                new_id = cl.create_scene_item(name, item["sourceName"], item["sceneItemEnabled"]).scene_item_id
                t = item["sceneItemTransform"]
                cl.set_scene_item_transform(name, new_id, {k: t[k] for k in self.COPYABLE if k in t})
                if item["sourceName"].startswith("Cam - "):
                    spots[item["sourceName"]] = [round(v) for v in positions.item_box(t)]
        else:
            video = cl.get_video_settings()
            build_scenes.set_canvas(video.base_width, video.base_height)
            names_on = bool(positions.read(cl, positions.NAME_TAGS, True))
            for src, x, y, w, h in build_scenes.with_names(build_scenes.backdrop() + build_scenes.cams_split()):
                tag = src.startswith("Name - ")
                new_id = cl.create_scene_item(name, src, names_on if tag else True).scene_item_id
                cl.set_scene_item_transform(name, new_id, positions.tag_transform((x, y, w, h)) if tag
                                            else positions.box_transform(x, y, w, h, fill=src in build_scenes.FILL))
                if src.startswith("Cam - "):
                    spots[src] = [x, y, w, h]
        defaults = positions.read(cl, positions.DEFAULTS, {})
        defaults[name] = spots
        positions.write(cl, positions.DEFAULTS, defaults)
        if start_from:                          # the copy gets the same default background
            source_bgs = self._layout_bgs(cl).get(start_from)
            if source_bgs:
                found = self._layout_bgs(cl)
                found[name] = dict(source_bgs)
                positions.write(cl, positions.LAYOUT_BGS, found)
        meta = self._meta(cl)
        if tab in meta["tabs"] and tab != positions.GENERAL:
            meta["tab"][name] = tab
            self._save_meta(cl, meta)
        cl.set_current_program_scene(name)
        return name

    @_locked
    def restore_layouts(self):
        """Settings → Bring back deleted layouts."""
        cl = self.client()
        positions.write(cl, positions.REMOVED, [])
        self._build(cl, keep_scene=cl.get_current_program_scene().current_program_scene_name)

    @_locked
    def set_start_layout(self, name):
        positions.write(self.client(), positions.START_LAYOUT, name or "")

    @_locked
    def layout_info(self, name):
        """For a layout's menu: whether it shows a background, its default background, saved pictures,
        and whether it's the start layout."""
        cl = self.client()
        shows_bg = any(i["sourceName"] == "Background" for i in cl.get_scene_item_list(name).scene_items)
        return {"background": shows_bg, "default": self._layout_bgs(cl).get(name, {}).get("default", ""),
                "pictures": [os.path.basename(p) for p in media.list_backgrounds()],
                "start": positions.read(cl, positions.START_LAYOUT, "") == name}

    @_locked
    def save_layout(self, scene):
        """Save layout: this layout, exactly as it is now, becomes its default. Every source's position and
        size, the cameras' default spots, and the background picture showing now. Returns the picture's name,
        or "" if there wasn't one (a background video can't be saved as a default)."""
        cl = self.client()
        saved = positions.read(cl, positions.SAVED_LAYOUTS, {})
        saved[scene] = {}
        usual = positions.read(cl, positions.DEFAULTS, {}).get(scene, {})
        for item in cl.get_scene_item_list(scene).scene_items:
            src, t = item["sourceName"], item["sceneItemTransform"]
            saved[scene][src] = {k: t[k] for k in self.COPYABLE if k in t}
            if src.startswith("Cam - "):
                box = positions.item_box(t)
                if src in usual and all(abs(a - b) < 1 for a, b in zip(box, usual[src])):
                    positions.forget(cl, src, scene)
                else:
                    positions.save(cl, src, scene, box)
        positions.write(cl, positions.SAVED_LAYOUTS, saved)
        picture = ""
        if any(i["sourceName"] == "Background" for i in cl.get_scene_item_list(scene).scene_items):
            path = cl.get_input_settings("Background").input_settings.get("file", "")
            if path and os.path.dirname(os.path.abspath(path)) != media.BACKGROUNDS and os.path.exists(path):
                path = media.add_background(path)        # keep a copy with the other saved pictures
            if path and os.path.exists(path):
                picture = os.path.basename(path)
                found = self._layout_bgs(cl)
                entry = found.setdefault(scene, {"default": "", "extras": []})
                entry["default"] = picture
                entry["extras"] = list(dict.fromkeys(entry.get("extras", []) + [picture]))
                positions.write(cl, positions.LAYOUT_BGS, found)
        return picture

    @_locked
    def reset_layout(self, scene):
        """This layout's cameras back on their default spots."""
        cl = self.client()
        for cam in positions.read(cl, positions.DEFAULTS, {}).get(scene, {}):
            try:
                self._place(cl, scene, cam, self._default(cl, scene, cam))
            except OBSSDKRequestError:
                pass

    def _refit(self, cl, cam):
        """Put a camera back on its default spot in every layout, fitted to its new shape."""
        for scene in positions.read(cl, positions.DEFAULTS, {}):
            box = self._default(cl, scene, cam)
            if box:
                try:
                    self._place(cl, scene, cam, box)
                except OBSSDKRequestError:
                    pass

    @_locked
    def reset_all(self):
        """Settings: every camera back on its default spot, in every layout."""
        self._reset_all(self.client())

    @_locked
    def save_defaults(self):
        """Settings: make every camera's current spot its default, in every layout."""
        cl = self.client()
        layouts = positions.read(cl, positions.DEFAULTS, {})
        for scene, cams in layouts.items():
            try:
                found = {i["sourceName"]: positions.item_box(i["sceneItemTransform"])
                         for i in cl.get_scene_item_list(scene).scene_items}
            except OBSSDKRequestError:
                continue
            for cam, usual in cams.items():
                if cam not in found:
                    continue
                if all(abs(a - b) < 1 for a, b in zip(found[cam], usual)):
                    positions.forget(cl, cam, scene)   # back to the layout's own spot
                else:
                    positions.save(cl, cam, scene, found[cam])

    @_locked
    def devices(self):
        """For Settings: each cam's webcam choices, and the browser window choices."""
        import build_scenes
        cl = self.client()
        cams = {}
        for name in self.cfg.CAMS:
            cam = f"Cam - {name}"
            found = cl.get_input_settings(cam)
            if found.input_kind.startswith("dshow_input"):
                cams[name] = {"online": False, "current": found.input_settings.get("video_device_id", ""),
                              "choices": build_scenes.webcams(cl, cam)}
            else:
                cams[name] = {"online": True}
        items = cl.get_input_properties_list_property_items("Browser Window", "window").property_items
        current = cl.get_input_settings("Browser Window").input_settings.get("window", "")
        return {"cams": cams, "window": current,
                "windows": [(i["itemName"], i["itemValue"]) for i in items if i["itemValue"]]}

    @_locked
    def options(self):
        """For Settings: name tags on or off, every layout that shows a background, saved pictures, and
        each layout's default and extra backgrounds."""
        cl = self.client()
        layouts = []
        for s in reversed(cl.get_scene_list().scenes):
            name = s["sceneName"]
            if name not in HIDDEN and any(i["sourceName"] == "Background"
                                          for i in cl.get_scene_item_list(name).scene_items):
                layouts.append(name)
        return {"name_tags": bool(positions.read(cl, positions.NAME_TAGS, True)), "layouts": layouts,
                "pictures": [os.path.basename(p) for p in media.list_backgrounds()],
                "layout_bgs": self._layout_bgs(cl), "video_idle": self._video_idle(cl)}

    def _video_idle(self, cl):
        found = positions.read(cl, positions.VIDEO_IDLE, {})
        return {"text": found.get("text", positions.IDLE_TEXT), "picture": found.get("picture", "")}

    @_locked
    def video_idle(self):
        """What the empty Video + Cams box shows: a picture from the backgrounds folder, or a text card."""
        found = self._video_idle(self.client())
        if found["picture"] and not os.path.exists(os.path.join(media.BACKGROUNDS, found["picture"])):
            found["picture"] = ""
        return found

    @_locked
    def set_video_idle(self, text=None, picture=None):
        """Settings → Backgrounds → Empty video box."""
        cl = self.client()
        found = self._video_idle(cl)
        if text is not None:
            found["text"] = positions.clean_display_name(text.replace("\n", " "))[:32] if text.strip() else ""
        if picture is not None:
            found["picture"] = os.path.basename(picture)
        positions.write(cl, positions.VIDEO_IDLE, found)

    @_locked
    def set_name_tags(self, on):
        """Show or hide every cam's name tag, in every layout."""
        cl = self.client()
        positions.write(cl, positions.NAME_TAGS, bool(on))
        for s in cl.get_scene_list().scenes:
            for i in cl.get_scene_item_list(s["sceneName"]).scene_items:
                if i["sourceName"].startswith("Name - "):
                    cl.set_scene_item_enabled(s["sceneName"], i["sceneItemId"], bool(on))

    @_locked
    def set_display_name(self, name, shown):
        """The name shown on a cam (its tag, the screen maps). Empty goes back to the cam's own name."""
        cl = self.client()
        shown = positions.clean_display_name(shown)
        found = positions.read(cl, positions.DISPLAY_NAMES, {})
        if shown and shown != name:
            found[name] = shown
        else:
            found.pop(name, None)
        positions.write(cl, positions.DISPLAY_NAMES, found)
        try:
            cl.set_input_settings(f"Name - {name}", {"text": f" {shown or name} "}, True)
        except OBSSDKRequestError:
            pass                               # layouts built before name tags: Repair layouts adds them
        return shown or name

    @_locked
    def set_webcam(self, name, device):
        import build_scenes
        cl = self.client()
        cl.set_input_settings(f"Cam - {name}", {"video_device_id": device}, True)
        build_scenes.widescreen(cl, f"Cam - {name}")

    @_locked
    def set_window(self, window):
        self.client().set_input_settings("Browser Window", {"window": window}, True)

    @_locked
    def set_remote_cam(self, name, cam_id):
        """A guest pressed Start my camera: show their VDO.Ninja camera in their Cam source."""
        cl = self.client()
        changed = link.save_remote_cam(name, cam_id)
        cam = f"Cam - {name}"
        found = cl.get_input_settings(cam)
        if found.input_kind == "browser_source":
            if changed or found.input_settings.get("url") != link.vdo_view(cam_id):
                cl.set_input_settings(cam, {"url": link.vdo_view(cam_id)}, True)
            return "Your camera is in the show."
        # Their cam was a webcam source: it has to be swapped, which rebuilds the layouts. Never mid-recording.
        if cl.get_record_status().output_active:
            self.rebuild_waiting = True
            return "Your camera will be added as soon as the recording stops."
        self._build(cl, keep_scene=cl.get_current_program_scene().current_program_scene_name)
        return "Your camera is in the show."

    @_locked
    def backgrounds(self):
        """For the Background menu: the current picture, this layout's backgrounds (default first), and
        every saved picture. Pictures are files on this PC, in the backgrounds folder."""
        cl = self.client()
        entry = self._layout_bgs(cl).get(self.last_scene, {})
        return {"current": cl.get_input_settings("Background").input_settings.get("file", ""),
                "layout": self.last_scene, "mine": self._layout_pictures(cl, self.last_scene),
                "default": os.path.join(media.BACKGROUNDS, entry["default"]) if entry.get("default") else "",
                "pictures": media.list_backgrounds()}

    @_locked
    def set_background(self, path):
        cl = self.client()
        cl.set_input_settings("Background", {"file": path}, True)
        if self.bg_video:                      # a picture replaces a background video
            self.bg_video = None
            self._save_now(cl)

    def add_background_url(self, url):
        """Download a picture link into the backgrounds folder and show it. Not locked: downloads take a while."""
        try:
            path = media.download_picture(url)
        except (ValueError, OSError) as e:
            raise DeckError(f"Couldn't get that picture. ({e})") from e
        self.set_background(path)
        return os.path.splitext(os.path.basename(path))[0]

    @_locked
    def next_background(self):
        """Hotkey: the next of this layout's backgrounds, or of all saved ones if the layout has fewer than two."""
        cl = self.client()
        current = cl.get_input_settings("Background").input_settings.get("file", "")
        mine = self._layout_pictures(cl, self.last_scene)
        if len(mine) >= 2:
            norm = [os.path.normcase(p) for p in mine]
            i = norm.index(os.path.normcase(current)) if os.path.normcase(current) in norm else -1
            nxt = mine[(i + 1) % len(mine)]
        else:
            nxt = media.next_background(current)
        if nxt:
            cl.set_input_settings("Background", {"file": nxt}, True)
            if self.bg_video:
                self.bg_video = None
                self._save_now(cl)
        return nxt

    @_locked
    def video_settings(self):
        return {"shutdown": bool(self.client().get_input_settings("Video Panel").input_settings.get("shutdown"))}

    @_locked
    def set_restart(self, on):
        self.client().set_input_settings("Video Panel", {"shutdown": bool(on)}, True)



class Remote:
    """A guest's deck: asks the admin's deck to do things, over Tailscale only."""

    def __init__(self, invite):
        self.host, self.port, self.code = link.parse_invite(invite)   # refuses anything outside Tailscale
        self.base = f"http://{self.host}:{self.port}"

    def _ask(self, path, body=None):
        req = urllib.request.Request(self.base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.code}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read()).get("message")
            except (ValueError, AttributeError):
                message = None
            if e.code == 503:
                raise ConnectionError(message or "The admin's OBS isn't reachable right now.") from e
            raise DeckError(message or f"The admin's deck said no ({e.code}).") from e
        except (urllib.error.URLError, OSError) as e:
            raise ConnectionError("Can't reach the admin's deck. Check that Tailscale is on for both of you "
                                  "and that the admin's deck is open; this window keeps trying.") from e

    def _do(self, action, **args):
        return self._ask("/action", {"do": action, "args": args})

    def state(self):
        return self._ask("/state")

    def switch(self, scene):
        self._do("switch", scene=scene)

    def toggle_record(self):
        self._do("toggle_record")

    def move(self, scene, cam, box):
        self._do("move", scene=scene, cam=cam, box=list(box))

    def reset(self, scene, cam):
        return self._do("reset", scene=scene, cam=cam)

    def backgrounds(self):
        return self._do("backgrounds")

    def set_background(self, path):
        return self._do("set_background", path=path)

    def next_background(self):
        return self._do("next_background")

    def video_settings(self):
        return self._do("video_settings")

    def set_restart(self, on):
        self._do("set_restart", on=on)

    def set_video(self, state):
        self._do("video", state=state)

    def set_bg_video(self, state):
        self._do("bg_video", state=state)

    def add_background_url(self, url):
        return self._do("background_url", url=url)

    def camera(self, cam_id):
        return self._do("camera", id=cam_id)

    def set_display_name(self, shown):
        return self._do("display_name", name=shown)


def valid_box(box, canvas):
    """A box from a guest, checked: four finite numbers, on screen, not absurdly small."""
    if not (isinstance(box, list) and len(box) == 4
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)):
        raise DeckError("That camera spot doesn't make sense.")
    x, y, w, h = box
    cw, ch = canvas
    w, h = min(max(w, 16), cw), min(max(h, 9), ch)
    return [min(max(0, x), cw - w), min(max(0, y), ch - h), w, h]
