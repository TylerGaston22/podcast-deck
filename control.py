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

HIDDEN = {"_Sources (don't delete)"}
NOT_BUILT = "OBS doesn't have the new sources yet. Click Settings → Cameras → Rebuild layouts to add them."
OBS_CLOSED = "OBS not reachable. Open OBS; this window connects by itself."
NOW_SLOT = "podcast_deck.now"                  # {"bg": live background video, "video": Video + Cams title}
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
        self.bg_video = None                   # the live background video, read by OBS's Background Video page
        self.video_title = None                # what's in the Video + Cams box
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

    @_locked
    def rebuild(self):
        """Settings → Rebuild layouts."""
        cl = self.client()
        self._build(cl, keep_scene=cl.get_current_program_scene().current_program_scene_name)

    @_locked
    def state(self):
        cl = self.client()
        scenes = [s["sceneName"] for s in reversed(cl.get_scene_list().scenes)]
        recording = cl.get_record_status().output_active
        if not self.checked_layouts:
            self.checked_layouts = True
            if "Gameplay + Cams" not in scenes:  # a fresh OBS: set everything up without being asked
                self._build(cl)
                self.note = "Layouts set up in OBS. Pick webcams any time in Settings."
                scenes = [s["sceneName"] for s in reversed(cl.get_scene_list().scenes)]
            else:
                self._reset_all(cl)            # a new session starts from the default camera spots
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
            if i["sceneItemEnabled"] and (name.startswith("Cam - ") or name == "Video Panel"):
                self.ids[current, name] = i["sceneItemId"]
                items.append({"name": name, "box": list(positions.item_box(i["sceneItemTransform"]))})
        note, self.note = self.note, None
        return {"scenes": [s for s in scenes if s not in HIDDEN], "current": current,
                "recording": recording, "full": self._full(cl), "items": items, "canvas": list(self.canvas),
                "note": note, "now": self._now(cl), "names": positions.read(cl, positions.DISPLAY_NAMES, {})}

    def _now(self, cl):
        """What's showing: the background (video title or picture name) and the Video + Cams video."""
        if not self.now_loaded:
            self.now_loaded = True
            saved = positions.read(cl, NOW_SLOT, {})
            self.bg_video, self.video_title = saved.get("bg"), saved.get("video")
        if self.bg_video:
            background = "▶ " + (self.bg_video.get("title") or "video")
        else:
            try:
                path = cl.get_input_settings("Background").input_settings.get("file", "")
            except OBSSDKRequestError:
                path = ""
            background = os.path.splitext(os.path.basename(path))[0] if path else "plain color"
        return {"background": background, "video": self.video_title}

    def _save_now(self, cl):
        positions.write(cl, NOW_SLOT, {"bg": self.bg_video, "video": self.video_title})

    @_locked
    def set_bg_video(self, state):
        """Put a video in the background (or take it away with None). OBS's page picks it up in a moment."""
        self.bg_video = bgcontrol.valid_state(state)
        self._save_now(self.client())

    def live_bg(self):
        return self.bg_video

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
        """Move a camera, looking its id up again if the layouts were rebuilt since it was cached."""
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
                "layout_bgs": self._layout_bgs(cl)}

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
            pass                               # layouts built before name tags: Rebuild layouts adds them
        return shown or name

    @_locked
    def set_webcam(self, name, device):
        self.client().set_input_settings(f"Cam - {name}", {"video_device_id": device}, True)

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

    @_locked
    def play_video(self, vid=None, start=0, title=None):
        """Point player.html at a video (or at nothing) and reload the Video Panel."""
        cl = self.client()
        self.video_title = (title or "YouTube video")[:200] if vid else None
        self._save_now(cl)
        folder = cl.get_input_settings("Video Panel").input_settings.get("local_file") or ""
        try:
            media.write_now_playing(os.path.dirname(folder) or media.APP_DIR, vid, start)
        except OSError as e:
            raise DeckError(f"Couldn't update the video box. ({e})") from e
        cl.press_input_properties_button("Video Panel", "refreshnocache")


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

    def play_video(self, vid=None, start=0, title=None):
        self._do("play_video", vid=vid, start=start, title=title)

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
