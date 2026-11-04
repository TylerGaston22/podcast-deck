"""Desktop stream deck for OBS.

A small always-on-top window with one button per layout and a Record button,
plus global hotkeys (ctrl+alt+1..9 for layouts, ctrl+alt+r for record) and
optional mouse side buttons, all of which work while a game has focus. Buttons are read live from OBS, so any scene you
add later shows up automatically. The Background menu and Play link box change the
background picture and the Video + Cams video without opening OBS.

Everyone on the show is in a group, and nobody controls anyone else's OBS. People who record run
this deck with their own OBS and arrange everyone's camera in their own show; people who don't just
send their camera (the camera-only window, CameraDeck). Cameras travel through VDO.Ninja.

The first launch asks your name and whether this PC records, and writes config.py itself.

    py C:\\Users\\<you>\\source\\repos\\podcast-deck\\deck.py
"""
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import keyboard
import mouse

import bgcontrol
import configfile
import control
import link
import media
import positions
from control import DeckError
import theme
import updater
from theme import BRAND_FONT, FONT, HINT_FONT, LABEL_FONT, ROW_FONT, STATUS_FONT


def paint():
    """Copy the current color scheme's colors (BG, LIT, OK, …) into this module's globals."""
    globals().update(theme.tokens())


paint()

HANDLE = 10                                    # px: grab this close to a box's corner to resize it
NOTES = os.path.join(media.APP_DIR, "NOTES.md")
cfg, RECORD, BACKGROUND_HOTKEY = None, True, "ctrl+alt+b"


def use_config(found):
    global cfg, RECORD, BACKGROUND_HOTKEY
    cfg = found
    RECORD = getattr(cfg, "RECORD", getattr(cfg, "ADMIN", True))   # older config.py: ADMIN meant "has OBS"
    BACKGROUND_HOTKEY = getattr(cfg, "BACKGROUND_HOTKEY", "ctrl+alt+b")
    theme.use(getattr(cfg, "THEME", theme.DEFAULT))
    paint()


def category(scene):
    """What kind of layout a scene is, for its color: game, talk, video, break, or other."""
    n = scene.lower()
    if "video" in n or "browser" in n:
        return "video"
    if "right back" in n or "brb" in n or "break" in n:
        return "break"
    if "game" in n or "desktop" in n:
        return "game"
    if "us" in n.split() or "cam" in n or "talk" in n:
        return "talk"
    return "other"


if configfile.load() is not None:              # no config.py yet: the welcome window makes one
    use_config(configfile.load())


INSTANCE_PORT = 4462                           # a deck that's already open listens here for group links
INSTANCE_HELLO = b"PODCAST-DECK-INVITE "


def find_invite(text):
    """The group link in text (the join page's address, or a podcast-deck:// link), or None."""
    text = (text or "").strip()
    return text if link.find_group(text) else None


def hand_to_running_deck(invite):
    """A group link was clicked while a deck is already open: pass it over. True if one took it."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", INSTANCE_PORT), timeout=1) as s:
            s.sendall(INSTANCE_HELLO + invite.encode() + b"\n")
        return True
    except OSError:
        return False


def listen_for_invites(on_invite):
    """Take group links clicked while this deck is open (see hand_to_running_deck). This PC only, and only
    lines that start with our hello, so a web page can't talk to it."""
    import socket
    try:
        server = socket.create_server(("127.0.0.1", INSTANCE_PORT))
    except OSError:
        return                                 # another deck has it

    def serve():
        while True:
            conn, _ = server.accept()
            with conn:
                conn.settimeout(2)
                try:
                    data = conn.recv(4096)
                except OSError:
                    continue
            if data.startswith(INSTANCE_HELLO):
                found = find_invite(data[len(INSTANCE_HELLO):].decode(errors="ignore"))
                if found:
                    on_invite(found)
    threading.Thread(target=serve, daemon=True).start()


def group_people():
    """Everyone in the group, by name (empty when there's no group)."""
    return list(getattr(cfg, "GROUP_PEOPLE", [])) if getattr(cfg, "GROUP", "") else []


def sends_camera():
    """Whether this PC sends its camera to the group: camera only, or recording in a group with others."""
    people = group_people()
    return bool(getattr(cfg, "ME", "")) and cfg.ME in people and (not RECORD or len(people) > 1)


class Deck:
    """The deck on a PC that records: it controls this PC's OBS, and nothing else."""

    def __init__(self, root):
        self.root = root
        self.backend, self.setup_problem = None, None
        try:
            self.backend = control.Local(cfg)
        except DeckError as e:
            self.setup_problem = str(e)

        self.scenes, self.current, self.recording = [], None, False
        self.me = f"Cam - {cfg.ME}" if getattr(cfg, "ME", "") else None
        self.buttons = {}
        self.hotkeys, self.control_hotkeys = [], []
        self.notice, self.notice_until = "", 0.0
        self.canvas = (cfg.CANVAS_W, cfg.CANVAS_H)
        self.items = []                        # cams and the video box in the current layout
        self.selected = self.me
        self.drag, self.pending, self.sending = None, None, False
        self.guides = []                       # snap lines shown while dragging
        self.hold_until = 0.0                  # keep the map as dragged until OBS has caught up
        self.names = {}                        # the name shown on each cam, if changed in Settings
        self.now = {}                          # what's showing: background and video titles
        self.bg_preview = None                 # the pasted background video's place in its preview
        self.mine = {"bg": False, "video": False}   # whether this deck's control page runs each channel live
        self.bg = bgcontrol.BgControl(self, True)    # this PC only: the browser control page, and OBS's feed

        self.last_state = None                 # the last OBS state, to redraw after a color scheme change
        self.meta = {"tabs": [positions.GENERAL], "tab": {}, "color": {}}   # layout tabs and marker colors
        self.tab = positions.GENERAL           # the tab being shown
        self.open_layout = None                # the layout whose + panel is open (opens by itself when it goes live)
        self.panel, self.panel_key = None, None
        self.pending_bg = False                # a pasted background video is waiting for Switch
        self.live = {}                         # whose camera is showing, by name
        root.title("Podcast Deck")
        root.attributes("-topmost", True)
        root.geometry("320x880")
        root.minsize(260, 320)
        self.build_ui()
        self.set_control_hotkeys(True)

        if cfg.MOUSE_BUTTONS:
            mouse.hook(self.on_mouse)
        if self.setup_problem:
            self.status.config(text=self.setup_problem)
        else:
            self.poll()
        listen_for_invites(lambda text: root.after(0, self.offer_invite, text))
        root.after(3000, self.check_update)

    def build_ui(self):
        """Header, layouts, screen map, media, record, status bar. Rebuilt when the color scheme changes."""
        root = self.root
        root.configure(bg=BG)

        # Header: the brand on the left, status pills on the right.
        header = tk.Frame(root, bg=PANEL)
        header.pack(fill="x")
        tk.Frame(root, bg=LINE, height=1).pack(fill="x")
        tk.Label(header, text="P", bg=LIT, fg=LIT_INK, font=LABEL_FONT, width=2).pack(side="left", padx=(12, 8), pady=10)
        tk.Label(header, text="PODCAST DECK", bg=PANEL, fg=INK, font=BRAND_FONT).pack(side="left")
        self.obs_pill = self.pill(header, "OBS")
        self.obs_pill["frame"].pack(side="right", padx=(4, 12))
        self.rec_pill = self.pill(header, "REC")
        # Who's on the show: a small square per person, green while their camera is showing.
        self.people_row = tk.Frame(root, bg=BG, height=20)
        self.people_row.pack(fill="x", padx=12, pady=(8, 0))
        self.people_row.bind("<Configure>", lambda _e: self.flow_people())
        self.people_shown, self.people_items = None, []

        # Status bar at the very bottom: what's happening, and messages.
        bar = tk.Frame(root, bg=PANEL)
        bar.pack(side="bottom", fill="x")
        tk.Frame(root, bg=LINE, height=1).pack(side="bottom", fill="x")
        self.status = tk.Label(bar, text=self.notice if time.monotonic() < self.notice_until else "Connecting…",
                               bg=PANEL, fg=INK_DIM, font=STATUS_FONT, anchor="w", justify="left", wraplength=290)
        self.status.pack(fill="x", padx=12, pady=6)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        # Everything under the layouts sits at the bottom and always stays visible; the layouts get the rest.
        bottom = tk.Frame(body, bg=BG)
        bottom.pack(side="bottom", fill="x")
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x", pady=(10, 4))
        self.section(head, "LAYOUTS").pack(side="left")
        new = tk.Label(head, text="＋ New layout", bg=BG, fg=LIT, font=LABEL_FONT, cursor="hand2", padx=8)
        new.pack(side="left")                  # always in view, however many layouts there are
        new.bind("<Button-1>", lambda _e: self.new_layout_box())
        self.tabs_bar = tk.Frame(body, bg=BG)       # General, plus tabs of your own
        self.tabs_bar.pack(fill="x", pady=(0, 4))
        self.grid = tk.Frame(body, bg=BG)
        self.grid.pack(fill="both", expand=True)

        # Screen map: drag a camera to move it, drag its corner to resize it.
        self.section(bottom, "SCREEN").pack(fill="x", pady=(10, 4))
        self.map = tk.Canvas(bottom, bg=BG, highlightthickness=0, height=150, cursor="hand2")
        self.map.pack(fill="x")
        self.map.bind("<Configure>", self.fit_map)
        self.map.bind("<ButtonPress-1>", self.map_press)
        self.map.bind("<B1-Motion>", self.map_drag)
        self.map.bind("<ButtonRelease-1>", self.map_release)
        under = tk.Frame(bottom, bg=BG)
        under.pack(fill="x", pady=(6, 0))
        self.reset_button = self.small_key(under, "Reset camera", self.reset_camera)
        self.reset_button.pack(side="left")
        self.small_key(under, "Settings…", self.settings_box).pack(side="right")
        if sends_camera():                     # in a group, your own cam reaches your OBS through it too
            start = self.small_key(under, "Start my camera", self.start_camera)
            start.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
            start.pack(side="right", padx=4)

        # Record. Background, Paste link, and Play link are in each layout's + panel.
        self.controls = tk.Frame(bottom, bg=BG)
        self.controls.pack(fill="x")
        self.rec = self.key(self.controls, "●  Record", self.toggle_record)
        self.rec.pack(fill="x", pady=(10, 12), ipady=8)
        self.draw_people()

    def section(self, parent, text):
        """A small uppercase section label, like the stream launcher's."""
        return tk.Label(parent, text=text, bg=BG, fg=MUTED, font=LABEL_FONT, anchor="w")

    def pill(self, parent, text):
        """A rounded-looking status pill: a colored dot and a word. Returns its parts."""
        frame = tk.Frame(parent, bg=NAV, highlightbackground=LINE, highlightthickness=1)
        dot = tk.Canvas(frame, width=10, height=10, bg=NAV, highlightthickness=0)
        dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="", tags="dot")
        dot.pack(side="left", padx=(8, 5), pady=6)
        label = tk.Label(frame, text=text, bg=NAV, fg=INK, font=LABEL_FONT)
        label.pack(side="left", padx=(0, 9))
        return {"frame": frame, "dot": dot, "label": label}

    def set_pill(self, pill, color, text=None):
        pill["dot"].itemconfig("dot", fill=color)
        if text is not None:
            pill["label"].config(text=text)

    def set_theme(self, scheme):
        """Settings → Look: switch color scheme right away, and remember it on this PC."""
        theme.use(scheme)
        paint()
        configfile.update(THEME=theme.name)
        cfg.THEME = theme.name
        self.redraw()
        self.root.after(50, lambda: self.settings_box(tab="Look"))

    def redraw(self):
        """Build the window again (new colors, or the group changed what it shows)."""
        for w in self.root.winfo_children():
            w.destroy()
        self.scenes, self.buttons = [], {}     # layout rows, their panel, and who's on are redrawn on the next draw
        self.panel_key = None
        self.build_ui()
        if self.last_state:
            self.render(self.last_state, None)

    def on_mouse(self, event):
        if not isinstance(event, mouse.ButtonEvent) or event.event_type != mouse.DOWN:
            return
        action = cfg.MOUSE_BUTTONS.get(event.button)
        if action is None:
            return
        if action == "record":
            self.root.after(0, self.toggle_record)
        elif action == "next":
            self.root.after(0, self.next_scene)
        elif action == "next background":
            self.root.after(0, self.next_background)
        else:
            self.root.after(0, self.switch, action)

    def next_scene(self):
        if not self.scenes:
            return
        order = self.ordered(self.scenes)      # the deck's own order, as dragged
        i = order.index(self.current) if self.current in order else -1
        self.switch(order[(i + 1) % len(order)])

    # --- Talking to OBS -----------------------------------------------------
    def call(self, fn, then=None, quiet=False):
        """Run fn(backend) on a worker thread, then refresh the window.

        `then` gets fn's result on the UI thread. If the request is refused, the reason is shown
        in a popup, or in the status line when `quiet` (hotkeys, so a game doesn't lose focus).
        """
        def work():
            result, problem = None, None
            try:
                try:
                    result = fn(self.backend)
                except DeckError as e:
                    problem = str(e)
                state, error = self.backend.state(), None
            except DeckError as e:
                state, error = None, str(e)
            except ConnectionError as e:
                state, error = None, str(e)
            self.root.after(0, self.render, state, error)
            if problem:
                self.root.after(0, self.tell, problem, quiet)
            elif then and error is None:
                self.root.after(0, then, result)
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        if self.backend is not None:
            self.call(lambda b: None)
        self.root.after(2000, self.poll)

    def switch(self, name):
        self.call(lambda b: b.switch(name))

    def toggle_record(self):
        self.call(lambda b: b.toggle_record())

    def set_control_hotkeys(self, on):
        for hk in self.control_hotkeys:
            keyboard.remove_hotkey(hk)
        self.control_hotkeys = []
        if not on:
            return
        for combo, fn in ((cfg.RECORD_HOTKEY, self.toggle_record), (BACKGROUND_HOTKEY, self.next_background)):
            if combo:                          # "" turns a hotkey off (Settings → Hotkeys → Clear)
                try:
                    self.control_hotkeys.append(keyboard.add_hotkey(combo, lambda f=fn: self.root.after(0, f)))
                except ValueError:
                    self.say(f"The hotkey {combo} isn't valid. Change it in Settings → Hotkeys.", 10)

    # --- Settings -----------------------------------------------------------
    def settings_box(self, tab=None):
        """Tabs for Cameras, Backgrounds, Group, Hotkeys, Help, and Look."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title("Settings")
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        win.bind("<Escape>", lambda _e: win.destroy())

        def heading(parent, text, first=False):
            tk.Label(parent, text=text, bg=BG, fg=INK, font=FONT, anchor="w").pack(
                fill="x", pady=(0 if first else 12, 4))

        def note(parent, text, color=INK_DIM):
            tk.Label(parent, text=text, bg=BG, fg=color, font=STATUS_FONT, anchor="w", justify="left",
                     wraplength=440).pack(fill="x")

        # Tabs: a row of small buttons, the chosen one lit, showing one page at a time.
        tabs = tk.Frame(win, bg=BG)
        tabs.pack(fill="x", pady=(0, 10))
        body = tk.Frame(win, bg=BG, width=460)
        body.pack(fill="both", expand=True)
        pages, buttons = {}, {}

        def show(name):
            for n, page in pages.items():
                page.pack_forget()
                buttons[n].config(bg=KEY, fg=INK)
            pages[name].pack(fill="both", expand=True)
            buttons[name].config(bg=LIT, fg=LIT_INK)

        def page(name):
            pages[name] = tk.Frame(body, bg=BG)
            buttons[name] = self.small_key(tabs, name, lambda: show(name))
            buttons[name].pack(side="left", padx=(0, 4))
            return pages[name]

        cams_page = page("Cameras")
        heading(cams_page, "Cameras", first=True)
        note(cams_page, "Each camera's name sits on it in the show and moves with it.")
        cams = tk.Frame(cams_page, bg=BG)
        cams.pack(fill="x")
        self.call(lambda b: b.devices(), then=lambda found: self.fill_devices(cams, found))
        names = tk.BooleanVar(value=True)
        tk.Checkbutton(cams_page, text="Show names on cams", variable=names, anchor="w", bg=BG, fg=INK_DIM,
                       selectcolor=KEY, activebackground=BG, activeforeground=INK, font=STATUS_FONT,
                       command=lambda: self.call(lambda b: b.set_name_tags(names.get()), then=lambda _: self.say(
                           "Names shown on cams" if names.get() else "Names hidden"))).pack(fill="x", pady=(4, 0))

        heading(cams_page, "Default camera spots")
        note(cams_page, "Moving a camera on the map only lasts for this session; each session starts from the "
                        "defaults. To change the defaults, place the cameras where you want them, then save.")
        row = tk.Frame(cams_page, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self.small_key(row, "Save camera spots as default", lambda: self.call(
            lambda b: b.save_defaults(), then=lambda _: self.say("Camera spots saved as default"))).pack(side="left")
        self.small_key(row, "Reset cameras to default", lambda: self.call(
            lambda b: b.reset_all(), then=lambda _: self.say("Cameras back on their default spots"))).pack(
            side="left", padx=6)

        heading(cams_page, "Repair")
        note(cams_page, "Deleted something in OBS by accident? Repair layouts puts back every source and layout "
                        "the deck made, and rebuilds the layouts. Your own scenes aren't touched. Cameras go "
                        "back to their default spots. Also use it after changing config.py.")
        row = tk.Frame(cams_page, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self.small_key(row, "Repair layouts", self.repair).pack(side="left")
        self.small_key(row, "Bring back deleted layouts", lambda: self.call(
            lambda b: b.restore_layouts(), then=lambda _: self.say("Deleted layouts are back"))).pack(side="left", padx=6)

        bg_page = page("Backgrounds")
        heading(bg_page, "Empty video box", first=True)
        note(bg_page, "What the Video + Cams box shows when no video is playing.")
        idle = tk.Frame(bg_page, bg=BG)
        idle.pack(fill="x", pady=(4, 0))
        self.call(lambda b: b.options(), then=lambda found: self.fill_idle(idle, found))

        heading(bg_page, "Backgrounds for each layout")
        note(bg_page, "Switching to a layout puts up its default background. Tick extras to have them at the "
                      "top of Background ▾ on that layout. Add picture… saves your own.")
        pics = tk.Frame(bg_page, bg=BG)
        pics.pack(fill="x", pady=(8, 0))
        self.call(lambda b: b.options(), then=lambda found: self.fill_options(pics, names, found))

        group_page = page("Group")
        heading(group_page, "This PC", first=True)
        note(group_page, "Record: this PC runs your own show with OBS. Camera only: you just send your camera to "
                         "the group. Either way, nobody controls anyone else's OBS.")
        self.small_key(group_page, "Switch to camera only…", self.switch_mode).pack(anchor="w", pady=(4, 0))
        heading(group_page, "Your group")
        note(group_page, "Invite / Join at the top makes the group link, adds people, or joins another group.")
        self.small_key(group_page, "Invite / Join…", lambda: (win.destroy(), self.group_box())).pack(
            anchor="w", pady=(4, 0))

        keys_page = page("Hotkeys")
        heading(keys_page, "Hotkeys", first=True)
        note(keys_page, "They work even while a game has focus. Click Change…, then press the keys you want (Esc "
                        "cancels). On this PC only. Layouts you haven't changed use their place in the list.")
        hotkeys = tk.Frame(keys_page, bg=BG)
        hotkeys.pack(fill="x", pady=(8, 0))
        self.fill_hotkeys(hotkeys)

        help_page = page("Help")
        heading(help_page, "Help", first=True)
        note(help_page, "How the group works, what each deck can do, and how it's kept safe.")
        self.small_key(help_page, "How it works", lambda: subprocess.Popen(["notepad.exe", NOTES])).pack(
            anchor="w", pady=(4, 0))

        look_page = page("Look")
        heading(look_page, "Color scheme", first=True)
        note(look_page, "Changes right away, on this PC only. The browser control pages follow it.")
        swatches = tk.Frame(look_page, bg=BG)
        swatches.pack(fill="x", pady=(6, 0))
        for i, (scheme, colors) in enumerate(theme.SCHEMES.items()):
            current = scheme == theme.name
            card = tk.Frame(swatches, bg=colors["BG"], highlightthickness=2,
                            highlightbackground=colors["LIT"] if current else LINE, cursor="hand2")
            card.grid(row=i // 2, column=i % 2, padx=(0, 8), pady=(0, 8), sticky="nsew")
            title = tk.Label(card, text=("✓ " if current else "") + scheme, bg=colors["BG"], fg=colors["INK"],
                             font=STATUS_FONT + ("bold",), anchor="w")
            title.pack(fill="x", padx=10, pady=(8, 4))
            chips = tk.Frame(card, bg=colors["BG"])
            chips.pack(fill="x", padx=10, pady=(0, 10))
            parts = [card, title, chips]
            for token in ("LIT", "OK", "WARN", "REC", "KEY"):
                chip = tk.Frame(chips, bg=colors[token], width=26, height=14)
                chip.pack(side="left", padx=(0, 4))
                parts.append(chip)
            for w in parts:
                w.bind("<Button-1>", lambda _e, sc=scheme: self.set_theme(sc))

        show(tab if tab in pages else next(iter(pages)))
        self.key(win, "Close", win.destroy).pack(anchor="e", pady=(14, 0))

    def repair(self):
        """Settings → Repair layouts. Asks first while recording, since the picture changes for a moment."""
        if self.recording and not messagebox.askyesno(
                "Podcast Deck", "You're recording. Repairing rebuilds the layouts, so the picture changes for a "
                                "moment. Repair now anyway?", parent=self.root):
            return
        self.call(lambda b: b.rebuild(), then=lambda _: self.say("Layouts repaired: everything the deck made is back"))

    def fill_devices(self, frame, found):
        """Settings: one row per camera (the name shown on it, and the webcam it uses), plus the browser
        window for Browser + Cams."""
        def dropdown(r, choices, current, on_pick):
            names = [n for n, _ in choices]
            box = ttk.Combobox(frame, values=names, state="readonly", width=26)
            box.set(next((n for n, v in choices if v == current), "Pick one…"))
            box.bind("<<ComboboxSelected>>", lambda _e: on_pick(choices[box.current()][1]))
            box.grid(row=r, column=1, padx=(8, 0), pady=3, sticky="w")

        def name_box(r, name):
            """The name shown on this camera. Type a new one and press Enter (or click away)."""
            e = tk.Entry(frame, width=18, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
            e.insert(0, self.names.get(name) or name)
            e.grid(row=r, column=0, sticky="w", ipady=4, pady=3)
            def save(_e=None):
                shown = positions.clean_display_name(e.get()) or name
                if shown != (self.names.get(name) or name):
                    self.names[name] = shown
                    self.call(lambda b: b.set_display_name(name, shown),
                              then=lambda now: self.say(f"Camera name: {now}"))
            e.bind("<Return>", save)
            e.bind("<FocusOut>", save)

        for c, text in enumerate(("Name on screen", "Webcam")):
            tk.Label(frame, text=text, bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w").grid(
                row=0, column=c, sticky="w", padx=(8 if c else 0, 0))
        r = 1
        for name, cam in found["cams"].items():
            name_box(r, name)
            if cam["online"]:
                tk.Label(frame, text="joins online (VDO.Ninja)", bg=BG, fg=INK_DIM, font=STATUS_FONT).grid(
                    row=r, column=1, padx=(8, 0), sticky="w")
            else:
                dropdown(r, cam["choices"], cam["current"],
                         lambda v, n=name: self.call(lambda b: b.set_webcam(n, v), then=lambda _: self.say("Webcam set")))
            r += 1
        tk.Label(frame, text="Browser window", bg=BG, fg=INK, font=STATUS_FONT, anchor="w").grid(
            row=r, column=0, sticky="w", pady=(8, 0))
        dropdown(r, found["windows"], found["window"],
                 lambda v: self.call(lambda b: b.set_window(v), then=lambda _: self.say("Browser window set")))

    def fill_options(self, frame, names, found):
        """Settings: the name tag switch, and for each layout that shows a background: its default, its extra
        backgrounds (ticked), and Add picture… to save one of your own."""
        names.set(found["name_tags"])
        for w in frame.winfo_children():
            w.destroy()
        pics = found["pictures"]
        label = lambda name: os.path.splitext(name)[0][:24]
        for layout in found["layouts"]:
            entry = found["layout_bgs"].get(layout, {})
            box = tk.Frame(frame, bg=BG)
            box.pack(fill="x", pady=(2, 8))
            top = tk.Frame(box, bg=BG)
            top.pack(fill="x")
            tk.Label(top, text=layout, bg=BG, fg=INK, font=STATUS_FONT + ("bold",), anchor="w", width=16).pack(side="left")
            tk.Label(top, text="Default", bg=BG, fg=INK_DIM, font=STATUS_FONT).pack(side="left")
            names_shown = ["None"] + [label(p) for p in pics]
            default = ttk.Combobox(top, values=names_shown, state="readonly", width=22)
            default.set(label(entry["default"]) if entry.get("default") in pics else "None")
            default.bind("<<ComboboxSelected>>", lambda _e, l=layout, d=default: self.call(
                lambda b: b.set_layout_bgs(l, default="" if d.current() == 0 else pics[d.current() - 1]),
                then=lambda _: self.say("Default background saved")))
            default.pack(side="left", padx=6)
            self.small_key(top, "Add picture…", lambda l=layout: self.add_layout_picture(frame, names, l)).pack(side="left")
            if not pics:
                continue
            extras = tk.Frame(box, bg=BG)
            extras.pack(fill="x", padx=(16, 0))
            ticked = set(entry.get("extras", []))
            for i, pic in enumerate(pics):
                var = tk.BooleanVar(value=pic in ticked)
                def toggle(l=layout, p=pic, v=var):
                    chosen = set(found["layout_bgs"].setdefault(l, {"default": "", "extras": []}).get("extras", []))
                    chosen = chosen | {p} if v.get() else chosen - {p}
                    found["layout_bgs"][l]["extras"] = [x for x in pics if x in chosen]
                    self.call(lambda b: b.set_layout_bgs(l, extras=found["layout_bgs"][l]["extras"]))
                tk.Checkbutton(extras, text=label(pic), variable=var, command=toggle, bg=BG, fg=INK_DIM,
                               selectcolor=KEY, activebackground=BG, activeforeground=INK, font=STATUS_FONT,
                               anchor="w").grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 8))
        if not found["layouts"]:
            tk.Label(frame, text="No layouts with a background yet. Click Repair layouts on the Cameras tab.", bg=BG,
                     fg=INK_DIM, font=STATUS_FONT, anchor="w").pack(fill="x")

    def fill_idle(self, frame, found):
        """Settings → Backgrounds → Empty video box: a text card, or one of the saved pictures."""
        idle = found["video_idle"]
        tk.Label(frame, text="Text", bg=BG, fg=INK_DIM, font=STATUS_FONT).grid(row=0, column=0, sticky="w")
        text = tk.Entry(frame, width=26, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
        text.insert(0, idle["text"])
        text.grid(row=0, column=1, padx=8, pady=3, sticky="w", ipady=4)
        def save_text(_e=None):
            self.call(lambda b: b.set_video_idle(text=text.get()), then=lambda _: self.say("Saved"))
        text.bind("<Return>", save_text)
        text.bind("<FocusOut>", save_text)
        tk.Label(frame, text="Or a picture", bg=BG, fg=INK_DIM, font=STATUS_FONT).grid(row=1, column=0, sticky="w")
        pics = found["pictures"]
        box = ttk.Combobox(frame, values=["None (show the text)"] + [os.path.splitext(p)[0] for p in pics],
                           state="readonly", width=24)
        box.set(os.path.splitext(idle["picture"])[0] if idle["picture"] in pics else "None (show the text)")
        box.bind("<<ComboboxSelected>>", lambda _e: self.call(
            lambda b: b.set_video_idle(picture="" if box.current() == 0 else pics[box.current() - 1]),
            then=lambda _: self.say("Saved")))
        box.grid(row=1, column=1, padx=8, pady=3, sticky="w")

    def add_layout_picture(self, frame, names, layout):
        """Settings → Add picture… for one layout: pick a picture of your own; it's saved and added."""
        path = filedialog.askopenfilename(
            parent=self.root, title=f"Choose a background for {layout}",
            filetypes=[("Pictures", " ".join("*" + t for t in media.IMAGE_TYPES)), ("All files", "*.*")])
        if not path:
            return
        self.call(lambda b: b.add_layout_picture(layout, path), then=lambda name: (
            self.say(f"{os.path.splitext(name)[0]} saved for {layout}"),
            self.call(lambda b: b.options(), then=lambda found: self.fill_options(frame, names, found))))

    # --- Your camera ---------------------------------------------------------
    def start_camera(self):
        """Send your camera and mic to the group: a VDO.Ninja page in the browser. Everyone recording shows it
        in their own OBS (and so does yours). Keep the tab open while you're on the show."""
        group, me = getattr(cfg, "GROUP", ""), getattr(cfg, "ME", "")
        if not (group and me):
            self.tell("Join a group first: Invite / Join at the top.")
            return
        webbrowser.open(link.vdo_push(link.camera_id(group, me), me))
        self.say("Your camera page opened. Allow the camera and mic, and keep that tab open while you're on.", 10)

    def scale(self):
        return self.map.winfo_width() / self.canvas[0]

    def fit_map(self, _event=None):
        height = round(self.map.winfo_width() * self.canvas[1] / self.canvas[0])
        if abs(int(self.map.cget("height")) - height) > 1:
            self.map.config(height=height)
        self.draw_map()

    def movable(self, name):
        return name.startswith("Cam - ")

    def draw_map(self):
        c, s = self.map, self.scale()
        c.delete("all")
        c.create_rectangle(0, 0, self.canvas[0] * s - 1, self.canvas[1] * s - 1, fill=KEY, outline=KEY_HOVER)
        for axis, pos in self.guides:          # what a dragged camera snapped to
            if axis == "x":
                c.create_line(pos * s, 0, pos * s, self.canvas[1] * s, fill=LIT, dash=(2, 2))
            else:
                c.create_line(0, pos * s, self.canvas[0] * s, pos * s, fill=LIT, dash=(2, 2))
        if self.now.get("background") and any(i["name"] == "Video Panel" or i["name"].startswith("Cam - ")
                                              for i in self.items):
            c.create_text(6, 4, text="Background: " + self.now["background"], anchor="nw", fill=INK_DIM,
                          font=STATUS_FONT, width=self.canvas[0] * s - 12)
        for item in self.items:
            x, y, w, h = (v * s for v in item["box"])
            name = item["name"]
            if name == "Video Panel":
                c.create_rectangle(x, y, x + w, y + h, outline=INK_DIM, dash=(3, 3))
                c.create_text(x + w / 2, y + h / 2, text="▶ " + (self.now.get("video") or "Video"), width=max(w - 8, 10),
                              fill=INK_DIM, font=STATUS_FONT)
                continue
            mine = name == self.selected
            c.create_rectangle(x, y, x + w, y + h, fill=LIT if mine else KEY_HOVER,
                               outline=LIT if mine else (INK if self.movable(name) else INK_DIM))
            base = name.removeprefix("Cam - ")
            c.create_text(x + w / 2, y + h / 2, text=self.names.get(base) or base, width=max(w - 4, 10),
                          fill=LIT_INK if mine else (INK if self.movable(name) else INK_DIM), font=STATUS_FONT)
            if mine and self.movable(name):
                c.create_rectangle(x + w - 6, y + h - 6, x + w, y + h, fill=LIT_INK, outline=LIT_INK)

    def item_at(self, px, py):
        """The topmost movable camera under a point on the map."""
        s = self.scale()
        for item in reversed(self.items):
            x, y, w, h = (v * s for v in item["box"])
            if self.movable(item["name"]) and x <= px <= x + w and y <= py <= y + h:
                return item
        return None

    def map_press(self, e):
        item = self.item_at(e.x, e.y)
        if item is None:
            return
        self.selected = item["name"]
        s = self.scale()
        x, y, w, h = (v * s for v in item["box"])
        resize = e.x >= x + w - HANDLE and e.y >= y + h - HANDLE
        self.drag = {"item": item, "scene": self.current, "resize": resize, "start": (e.x, e.y),
                     "box": item["box"]}
        self.draw_map()

    def map_drag(self, e):
        d = self.drag
        if not d:
            return
        s = self.scale()
        dx, dy = (e.x - d["start"][0]) / s, (e.y - d["start"][1]) / s
        self.guides = []
        if d["resize"]:
            box = positions.clamp_resize(d["box"], dx, self.canvas, min_w=self.canvas[0] * 0.08)
        else:
            box = positions.clamp_move(d["box"], dx, dy, self.canvas)
            if not e.state & 0x0001:            # Shift held: move freely, no snapping
                box, self.guides = positions.snap(box, self.canvas, margin=self.canvas[0] * 24 / 1920,
                                                  reach=10 / s)
        d["item"]["box"] = box
        self.draw_map()
        self.push(d["scene"], d["item"]["name"], box)

    def map_release(self, _e):
        d, self.drag = self.drag, None
        self.guides = []
        self.draw_map()
        if not d or d["item"]["box"] == d["box"]:
            return
        name, scene, box = d["item"]["name"], d["scene"], d["item"]["box"]
        self.push(scene, name, box)
        self.say(f"{'Your camera' if name == self.me else name.removeprefix('Cam - ')} moved for this session")

    def push(self, scene, cam, box):
        """Send a camera's new spot, dropping in-between spots if the other end is slower than the mouse."""
        self.pending = lambda: self.backend.move(scene, cam, box)
        self.hold_until = time.monotonic() + 1.5
        if not self.sending:
            self.send_next()

    def send_next(self):
        if self.pending is None:
            self.sending = False
            return
        job, self.pending, self.sending = self.pending, None, True
        def work():
            try:
                job()
            except (DeckError, ConnectionError) as e:
                self.root.after(0, self.say, str(e), 8)
            self.root.after(0, self.send_next)
        threading.Thread(target=work, daemon=True).start()

    def reset_camera(self):
        cam, scene = self.selected, self.current
        if not cam:
            self.say("Click a camera on the map first.")
            return
        if not any(i["name"] == cam for i in self.items):
            self.say(f"{cam.removeprefix('Cam - ')} isn't in this layout.")
            return
        self.call(lambda b: b.reset(scene, cam), then=lambda ok: self.say(
            "Camera back on its default spot" if ok
            else "This layout has no usual spot for that camera. Run build_scenes.py to set one."))

    # --- Background --------------------------------------------------------
    def background_menu(self):
        """Pop up the saved pictures, plus Add picture…, Plain color, and Open folder."""
        def show(found):
            current = os.path.normcase(found["current"] or "")
            default = os.path.normcase(found.get("default") or "")
            mine = found.get("mine", [])
            m = tk.Menu(self.root, tearoff=0, bg=KEY, fg=INK, activebackground=LIT, activeforeground=LIT_INK,
                        font=STATUS_FONT, bd=0)

            def item(pic):
                tick = "✓  " if os.path.normcase(pic) == current else "     "
                star = "  ★ default" if os.path.normcase(pic) == default else ""
                m.add_command(label=tick + os.path.splitext(os.path.basename(pic))[0] + star,
                              command=lambda p=pic: self.set_background(p))
            if mine:                                  # this layout's own backgrounds first
                m.add_command(label=f"{found.get('layout')}", state="disabled")
                for pic in mine:
                    item(pic)
                m.add_separator()
            others = [p for p in found["pictures"] if os.path.normcase(p) not in {os.path.normcase(x) for x in mine}]
            if others:
                m.add_command(label="All backgrounds" if mine else "Backgrounds", state="disabled")
                for pic in others:
                    item(pic)
                m.add_separator()
            m.add_command(label="Add picture…", command=self.add_background)
            m.add_command(label=("✓  " if not current else "     ") + "Plain color",
                          command=lambda: self.set_background(""))
            m.add_command(label="Open backgrounds folder", command=self.open_backgrounds)
            b = self.bg_button
            m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        self.call(lambda b: b.backgrounds(), then=show)

    def set_background(self, path):
        """Show a picture. It also becomes the live layout's default, so switching away and back keeps it."""
        name = os.path.splitext(os.path.basename(path))[0] if path else "plain color"

        def work(b):
            b.set_background(path)
            return b.make_default(path) if path else None
        self.call(work, then=lambda layout: self.say(f"Background: {name}" + (f", saved for {layout}" if layout else "")))

    def add_background(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Choose a background picture",
            filetypes=[("Pictures", " ".join("*" + t for t in media.IMAGE_TYPES)), ("All files", "*.*")])
        if not path:
            return
        try:
            self.set_background(media.add_background(path))
        except OSError as e:
            self.tell(f"Couldn't copy that picture into the backgrounds folder. ({e})")

    def open_backgrounds(self):
        os.makedirs(media.BACKGROUNDS, exist_ok=True)
        os.startfile(media.BACKGROUNDS)

    def next_background(self):
        """Hotkey: step to the next saved picture."""
        self.call(lambda b: b.next_background(), quiet=True, then=lambda nxt: self.say(
            f"Background: {os.path.splitext(os.path.basename(nxt))[0]}" if nxt
            else "No saved backgrounds yet. Use Background ▾ → Add picture… first."))

    # --- Pasted background (picture or video) --------------------------------
    def bg_link_box(self):
        """Paste a picture or video for the background. Pictures switch right away; videos open a control
        page in the browser, and the background only switches when someone clicks Use as background
        there (or Switch on the deck)."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title("Background")
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text="Paste a picture or video for the background", bg=BG, fg=INK, font=FONT,
                 anchor="w").pack(fill="x")
        tk.Label(win, text="A picture file or link, a YouTube link, or a video link (.mp4).", bg=BG, fg=INK_DIM,
                 font=STATUS_FONT, anchor="w").pack(fill="x")
        entry = tk.Entry(win, width=48, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
        entry.pack(fill="x", pady=(8, 4), ipady=6)
        note = tk.Label(win, text="", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w", justify="left",
                        wraplength=380)
        note.pack(fill="x")
        try:
            clip = self.root.clipboard_get()
            if media.parse_background(clip):
                entry.insert(0, clip.strip())
        except tk.TclError:
            pass

        def use(_e=None):
            found = media.parse_background(entry.get())
            if not found:
                note.config(text="That isn't a picture or video link. Copy the whole link and try again.", fg=REC)
                return
            kind = found["kind"]
            if kind == "picture_file":
                try:
                    self.set_background(media.add_background(found["path"]))
                except OSError as e:
                    note.config(text=f"Couldn't copy that picture. ({e})", fg=REC)
                    return
                win.destroy()
            elif kind == "picture_url":
                note.config(text="Getting the picture…", fg=INK_DIM)
                self.call(lambda b: b.add_background_url(found["url"]),
                          then=lambda name: self.say(f"Background: {name}"))
                win.destroy()
            elif kind == "youtube":
                note.config(text="Checking the video…", fg=INK_DIM)
                def check():
                    problem, title = media.youtube_check(found["id"])
                    def done():
                        if not win.winfo_exists():
                            return
                        if problem:
                            note.config(text=problem, fg=REC)
                        else:
                            self.open_bg_preview(dict(found, title=title or "YouTube video"))
                            win.destroy()
                    self.root.after(0, done)
                threading.Thread(target=check, daemon=True).start()
            else:
                name = os.path.basename(found["url"].split("?")[0])
                self.open_bg_preview(dict(found, title=name))
                win.destroy()

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", pady=(12, 0))
        go = self.key(row, "Use", use)
        go.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
        go.pack(side="left", ipady=4)
        self.key(row, "Cancel", win.destroy).pack(side="right", ipady=4)
        win.bind("<Return>", use)
        win.bind("<Escape>", lambda _e: win.destroy())
        entry.focus_set()
        entry.select_range(0, "end")

    def open_control(self, channel, source, live=False):
        """Open the browser control page for a video: "bg" (a pasted background, live only after Use as
        background) or "video" (the Video + Cams box, live straight away)."""
        if not self.bg.httpd:
            self.tell("The deck couldn't start its video page. Close other decks on this PC and reopen this one.")
            return False
        self.bg.pending[channel] = dict(source, live=live)
        self.mine[channel] = live
        webbrowser.open(self.bg.page_url(channel))
        return True

    def open_bg_preview(self, source):
        """Open the browser control page for a pasted background video."""
        self.bg_preview = None
        if self.open_control("bg", source):
            self.pending_bg = True
            self.refresh_panel()
            self.say("Control the video in your browser. It switches when you click Use as background or Switch.", 10)

    def hide_pending(self):
        self.pending_bg = False
        self.refresh_panel()

    def switch_background(self):
        """The deck's Switch button: put the previewed video in the background, from where the preview is."""
        src = self.bg.pending.get("bg")
        if not src:
            return
        state = self.bg_preview or {"kind": src["kind"], "id": src.get("id"), "url": src.get("url"),
                                    "title": src.get("title", ""), "time": src.get("start", 0)}
        state = dict(state, seek=(state.get("seek") or 0) + 1)
        self.call(lambda b: b.set_bg_video(state), then=lambda _: self.went_live())

    def went_live(self):
        self.mine["bg"] = True
        self.hide_pending()
        self.say("Background video is live. Your browser tab controls it.", 8)

    # Called by the local server (bgcontrol.py), from its own thread.
    def live_state(self, channel):
        return self.backend.live(channel) if isinstance(self.backend, control.Local) else None

    def page_colors(self):
        """The color scheme, as CSS variables, for the browser control pages."""
        return theme.css()

    def idle_state(self):
        """What the empty Video + Cams box shows (admin only): {"text", "picture"}."""
        if not isinstance(self.backend, control.Local):
            return None
        try:
            return self.backend.video_idle()
        except (DeckError, ConnectionError):
            return None

    def control(self, channel, state, action):
        """A browser control page did something: preview, go_live, update, or stop."""
        if channel == "bg" and action == "preview":
            self.bg_preview = state
            return ""
        if action == "preview":
            return ""
        if self.backend is None:
            raise DeckError("The deck isn't connected yet.")
        put = self.backend.set_bg_video if channel == "bg" else self.backend.set_video
        if action == "go_live":
            put(state)
            self.mine[channel] = True
            if channel == "bg":
                self.root.after(0, self.went_live)
            return "Live"
        if action == "update":
            if self.mine.get(channel):
                put(state)
            return ""
        put(None)                                           # stop
        self.mine[channel] = False
        self.root.after(0, self.say, "Background video stopped" if channel == "bg" else "Video stopped")
        return "Stopped"

    def closing(self):
        """Closing the admin's deck stops both videos in OBS, so nothing keeps playing without a way to stop it."""
        if isinstance(self.backend, control.Local):
            for put in (self.backend.set_video, self.backend.set_bg_video):
                try:
                    put(None)
                except (DeckError, ConnectionError):
                    pass
        self.root.destroy()

    # --- Video link --------------------------------------------------------
    def play_link(self):
        self.call(lambda b: b.video_settings(), then=self.link_box)

    def play_video(self, vid=None, start=0, title=None):
        """Play a video in the Video + Cams box and open its browser control page, or stop it (vid None)."""
        if vid is None:
            self.call(lambda b: b.set_video(None), then=lambda _: self.say("Video stopped"))
            return
        source = {"kind": "youtube", "id": vid, "start": start, "title": title or "YouTube video"}
        state = {"kind": "youtube", "id": vid, "title": source["title"], "playing": True, "muted": False,
                 "volume": 100, "time": start, "seek": 1}
        self.call(lambda b: b.set_video(state), then=lambda _: (
            self.open_control("video", source, live=True),
            self.say("Playing in Video + Cams. Pause, mute, or stop it in the browser tab that opened.", 10)))

    def link_box(self, settings):
        """The paste box: YouTube link in, video playing in Video + Cams out."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title("Play link")
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)

        tk.Label(win, text="Paste a YouTube link, then press Enter", bg=BG, fg=INK, font=FONT,
                 anchor="w").pack(fill="x")
        entry = tk.Entry(win, width=48, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
        entry.pack(fill="x", pady=(8, 4), ipady=6)
        note = tk.Label(win, text="", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w", justify="left",
                        wraplength=380)
        note.pack(fill="x")
        restart = tk.BooleanVar(value=bool(settings.get("shutdown", False)))
        tk.Checkbutton(win, text="Restart the video when I switch away from Video + Cams", variable=restart,
                       bg=BG, fg=INK_DIM, selectcolor=KEY, activebackground=BG, activeforeground=INK,
                       font=STATUS_FONT, anchor="w",
                       command=lambda: self.call(lambda b: b.set_restart(restart.get()))).pack(fill="x", pady=(6, 0))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", pady=(12, 0))

        # A copied YouTube link is the usual case, so start with it already pasted.
        try:
            clip = self.root.clipboard_get()
            if media.parse_youtube(clip):
                entry.insert(0, clip.strip())
        except tk.TclError:
            pass

        def load(vid=None, start=0, title=None):
            self.play_video(vid, start, title)
            win.destroy()

        def play(_event=None):
            found = media.parse_youtube(entry.get())
            if not found:
                note.config(text="That doesn't look like a YouTube link.", fg=REC)
                return
            note.config(text="Checking the video…", fg=INK_DIM)
            def check():
                problem, title = media.youtube_check(found[0])
                def done():
                    if not win.winfo_exists():
                        return
                    if problem:
                        note.config(text=problem, fg=REC)
                    else:
                        load(*found, title)
                self.root.after(0, done)
            threading.Thread(target=check, daemon=True).start()

        play_btn = self.key(row, "Play", play)
        play_btn.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
        play_btn.pack(side="left", ipady=4)
        self.key(row, "Stop video", lambda: load()).pack(side="left", padx=6, ipady=4)
        self.key(row, "Cancel", win.destroy).pack(side="right", ipady=4)

        win.bind("<Return>", play)
        win.bind("<Escape>", lambda _e: win.destroy())
        entry.focus_set()
        entry.select_range(0, "end")

    # --- UI ----------------------------------------------------------------
    def key(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, font=FONT, bg=KEY, fg=INK, activebackground=KEY_HOVER,
                      activeforeground=INK, relief="flat", bd=0, cursor="hand2", anchor="w", padx=14)
        return b

    def small_key(self, parent, text, cmd):
        b = self.key(parent, text, cmd)
        b.config(font=STATUS_FONT, padx=10, pady=4)
        return b

    def say(self, text, seconds=4):
        """Show a short message in the status line, without stealing focus."""
        self.notice, self.notice_until = text, time.monotonic() + seconds
        self.status.config(text=text)

    def tell(self, text, quiet=False):
        if quiet:
            self.say(text, seconds=8)
        else:
            messagebox.showwarning("Podcast Deck", text, parent=self.root)

    def render(self, state, error):
        if error:
            self.status.config(text=error)
            self.set_pill(self.obs_pill, BAD, "OBS OFFLINE")
            self.rec_pill["frame"].pack_forget()
            return
        self.last_state = state
        self.set_pill(self.obs_pill, OK, "OBS")
        self.names = state.get("names") or {}
        if state.get("note"):
            self.say(state["note"], seconds=10)
        self.now = state.get("now") or {}
        self.live = state.get("live") or {}
        self.draw_people()
        if state["current"] != self.current:   # a layout went live: its panel opens by itself
            self.open_layout = state["current"]
        self.canvas = tuple(state["canvas"])
        meta = state.get("meta") or self.meta
        if state["scenes"] != self.scenes or meta != self.meta or not self.buttons:
            self.meta = meta
            if self.tab not in meta["tabs"]:
                self.tab = positions.GENERAL
            self.current = state["current"]
            self.rebuild(state["scenes"])
        self.current, self.recording = state["current"], state["recording"]
        if not self.drag and time.monotonic() >= self.hold_until:  # don't snap a camera back mid-move
            self.items = state["items"]
            self.draw_map()
        rec_txt = "Recording" if self.recording else "Not recording"
        if self.recording and cfg.RECORD_HOTKEY:
            rec_txt += f" ({cfg.RECORD_HOTKEY})"
        if time.monotonic() >= self.notice_until:
            self.status.config(text=f"{self.current}  ·  {rec_txt}")
        if self.recording:                     # a red REC pill with the running time, like a real recorder
            secs = int((state.get("rec_ms") or 0) / 1000)
            self.set_pill(self.rec_pill, REC, f"REC {secs // 3600}:{secs // 60 % 60:02d}:{secs % 60:02d}"
                          if secs >= 3600 else f"REC {secs // 60:02d}:{secs % 60:02d}")
            if not self.rec_pill["frame"].winfo_ismapped():
                self.rec_pill["frame"].pack(side="right", padx=4)
        else:
            self.rec_pill["frame"].pack_forget()
        for name in self.buttons:
            self.paint_row(name)
        self.refresh_panel()
        self.rec.config(text="■  Stop recording" if self.recording else "●  Record",
                        bg=REC if self.recording else KEY, fg="#FFFFFF" if self.recording else INK,
                        activebackground=REC if self.recording else KEY_HOVER)

    def ordered(self, scenes):
        """Layouts in the order they were dragged into; new ones go at the end, in OBS's order."""
        order = [n for n in self.meta.get("order", []) if n in scenes]
        return order + [n for n in scenes if n not in order]

    def rebuild(self, scenes):
        """The tab strip, then one row per layout in the current tab: a color marker, its name, a ⋯ menu
        (admin), and + for its panel. The live one is lit. Hotkeys (shown in the panel) follow the deck's order,
        whatever tab is showing, unless changed in Settings → Hotkeys."""
        self.scenes = scenes
        self.draw_tabs()
        for w in self.grid.winfo_children():
            w.destroy()
        for hk in self.hotkeys:
            keyboard.remove_hotkey(hk)
        self.hotkeys, self.buttons = [], {}
        live = True
        keys = self.layout_hotkeys()
        if live:
            for name, combo in keys.items():
                try:
                    self.hotkeys.append(keyboard.add_hotkey(combo, lambda n=name: self.root.after(0, self.switch, n)))
                except ValueError:             # a hotkey typed by hand into config.py that isn't valid
                    self.say(f"The hotkey for {name} ({combo}) isn't valid. Change it in Settings → Hotkeys.", 10)
        for name in self.ordered(scenes):
            if self.meta["tab"].get(name, positions.GENERAL) != self.tab:
                continue
            row = tk.Frame(self.grid, bg=NAV, cursor="hand2" if live else "arrow")
            row.pack(fill="both", expand=True, pady=1)
            bar = tk.Frame(row, bg=NAV, width=3)
            bar.pack(side="left", fill="y")
            color = self.meta["color"].get(name) or theme.category_color(category(name))
            chip = tk.Frame(row, bg=color, width=10, height=10)
            chip.pack(side="left", padx=(10, 10))
            label = tk.Label(row, text=name, bg=NAV, fg=INK if live else INK_DIM, font=ROW_FONT, anchor="w")
            label.pack(side="left", fill="x", expand=True, pady=3)
            toggle = None
            if live:                           # + opens this layout's panel (switching to it), − closes it
                toggle = tk.Label(row, text="−" if name == self.open_layout else "+", bg=NAV, fg=INK_DIM,
                                  font=FONT, cursor="hand2", width=2)
                toggle.pack(side="right", padx=(0, 6))
                toggle.bind("<Button-1>", lambda _e, n=name: self.toggle_panel(n) or "break")
            dots = tk.Label(row, text="⋯", bg=NAV, fg=NAV, font=FONT, cursor="hand2")
            if dots:
                dots.pack(side="right")
                dots.bind("<Button-1>", lambda e, n=name: self.layout_menu(n, e) or "break")
            self.buttons[name] = {"row": row, "bar": bar, "label": label, "dots": dots, "live": live,
                                  "toggle": toggle}
            for w in (row, label, chip) + ((dots,) if dots else ()) + ((toggle,) if toggle else ()):
                if live and w not in (dots, toggle):   # click switches; press and drag moves the row
                    w.bind("<ButtonPress-1>", lambda e, n=name: self.row_press(n, e))
                    w.bind("<B1-Motion>", lambda e, n=name: self.row_drag(n, e))
                    w.bind("<ButtonRelease-1>", lambda e, n=name: self.row_release(n, e))
                w.bind("<Enter>", lambda _e, n=name: self.paint_row(n, hover=True))
                w.bind("<Leave>", lambda _e, n=name: self.paint_row(n))
                w.bind("<Button-3>", lambda e, n=name: self.layout_menu(n, e))
            self.paint_row(name)
        if not self.buttons:
            tk.Label(self.grid, text="No layouts in this tab yet. Click ＋ New layout above, or use a layout's ⋯ → Tab.",
                     bg=BG, fg=MUTED, font=STATUS_FONT, wraplength=280, justify="left", anchor="w").pack(fill="x")

    def new_layout_box(self):
        """＋ New layout: a name, and what to start from. It goes into the tab that's showing."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title("New layout")
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text="New layout" + ("" if self.tab == positions.GENERAL else f" in {self.tab}"), bg=BG, fg=INK,
                 font=FONT, anchor="w").pack(fill="x")
        tk.Label(win, text="Name", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w").pack(fill="x", pady=(8, 0))
        name = tk.Entry(win, width=34, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
        name.pack(fill="x", ipady=5)
        name.focus_set()
        tk.Label(win, text="Start from", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w").pack(fill="x", pady=(8, 0))
        empty = "Empty (background + cams side by side)"
        choices = [empty] + [f"A copy of {s}" for s in self.scenes]
        start = ttk.Combobox(win, values=choices, state="readonly", width=34)
        start.set(empty)
        start.pack(fill="x")
        note = tk.Label(win, text="", bg=BG, fg=REC, font=STATUS_FONT, anchor="w", wraplength=300, justify="left")
        note.pack(fill="x", pady=(6, 0))

        def create(_e=None):
            text = name.get().strip()
            if not text:
                note.config(text="Give the layout a name.")
                return
            base = "" if start.current() == 0 else self.scenes[start.current() - 1]
            tab = self.tab
            win.destroy()
            self.call(lambda b: b.new_layout(text, base, tab), then=lambda made: self.say(
                f"{made} made. Drag cameras on the map; ⋯ sets its background and color."))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        go = self.small_key(row, "Create", create)
        go.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
        go.pack(side="left")
        self.small_key(row, "Cancel", win.destroy).pack(side="right")
        win.bind("<Return>", create)
        win.bind("<Escape>", lambda _e: win.destroy())

    # Drag a layout row to reorder (admin). A plain click still switches to it.
    def row_press(self, name, e):
        self.row_drag_state = {"name": name, "y": e.y_root, "moving": False, "line": None}

    def row_target(self, y_root):
        """Where a dragged row would land: the index among the rows showing."""
        rows = [r["row"] for r in self.buttons.values()]
        return sum(1 for r in rows if r.winfo_rooty() + r.winfo_height() / 2 < y_root)

    def row_drag(self, name, e):
        d = getattr(self, "row_drag_state", None)
        if not d or abs(e.y_root - d["y"]) < 6:
            return
        d["moving"] = True
        rows = [r["row"] for r in self.buttons.values()]
        i = self.row_target(e.y_root)
        y = (rows[i].winfo_y() - 2) if i < len(rows) else (rows[-1].winfo_y() + rows[-1].winfo_height())
        if d["line"] is None:
            d["line"] = tk.Frame(self.grid, bg=LIT, height=3)
        d["line"].place(x=0, y=max(0, y), relwidth=1)
        d["line"].lift()

    def row_release(self, name, e):
        d, self.row_drag_state = getattr(self, "row_drag_state", None), None
        if not d or not d["moving"]:
            self.switch(name)
            return
        if d["line"] is not None:
            d["line"].destroy()
        showing = list(self.buttons)
        i = self.row_target(e.y_root)
        before = showing[i] if i < len(showing) else None
        order = [n for n in self.ordered(self.scenes) if n != name]
        if before == name:
            return
        order.insert(order.index(before) if before in order else
                     (order.index(showing[-1]) + 1 if showing[-1] in order else len(order)), name)
        self.meta["order"] = order
        self.rebuild(self.scenes)
        self.call(lambda b: b.set_order(order), then=lambda _: self.say(f"{name} moved"))

    def draw_tabs(self):
        """General, your own tabs, and ＋ to make another. Right-click a tab to rename or delete it."""
        for w in self.tabs_bar.winfo_children():
            w.destroy()
        tabs = self.meta["tabs"]
        for tab in tabs:
            on = tab == self.tab
            t = tk.Label(self.tabs_bar, text=tab, bg=LIT if on else NAV, fg=LIT_INK if on else INK_DIM,
                         font=STATUS_FONT + ("bold",), padx=10, pady=3, cursor="hand2")
            t.pack(side="left", padx=(0, 4))
            t.bind("<Button-1>", lambda _e, tb=tab: self.show_tab(tb))
            if tab != positions.GENERAL:
                t.bind("<Button-3>", lambda e, tb=tab: self.tab_menu(tb, e))
        plus = tk.Label(self.tabs_bar, text="＋ Tab", bg=NAV, fg=INK_DIM, font=STATUS_FONT + ("bold",), padx=8,
                        pady=3, cursor="hand2")
        plus.pack(side="left")
        plus.bind("<Button-1>", lambda _e: self.ask_text("New tab", "Name the tab (for example: Solo, 4 people):", "",
                                                         lambda name: self.call(lambda b: b.add_tab(name),
                                                                                then=lambda made: self.show_tab(made))))

    def show_tab(self, tab):
        self.tab = tab
        self.rebuild(self.scenes)

    def tab_menu(self, tab, event):
        m = self.menu()
        m.add_command(label="Rename tab…", command=lambda: self.ask_text(
            "Rename tab", "New name:", tab, lambda new: self.call(lambda b: b.rename_tab(tab, new),
                                                                   then=lambda made: self.show_tab(made))))
        m.add_command(label="Delete tab (its layouts go back to General)", command=lambda: self.call(
            lambda b: b.delete_tab(tab), then=lambda _: self.say(f"Tab {tab} deleted")))
        m.tk_popup(event.x_root, event.y_root)

    def menu(self):
        return tk.Menu(self.root, tearoff=0, bg=KEY, fg=INK, activebackground=LIT, activeforeground=LIT_INK,
                       font=STATUS_FONT, bd=0)

    MARKERS = (("Blue", "#4DA3FF"), ("Green", "#46D39A"), ("Magenta", "#D06BFF"), ("Yellow", "#F2C14E"),
               ("Orange", "#FF8B3D"), ("Red", "#FF3D4F"), ("Teal", "#18D2B5"), ("Gray", "#6C7888"))

    def layout_menu(self, name, event):
        """A layout's menu (⋯ or right-click): rename, start on it, default background, tab, color, reset
        its cameras, delete."""
        x, y = event.x_root, event.y_root

        def show(info):
            m = self.menu()
            m.add_command(label=name, state="disabled")
            m.add_command(label="Rename…", command=lambda: self.ask_text(
                "Rename layout", "New name (OBS's scene is renamed too):", name,
                lambda new: self.call(lambda b: b.rename_layout(name, new), then=lambda made: self.renamed(name, made))))
            m.add_command(label=("✓  " if info["start"] else "") + "Start on this layout", command=lambda: self.call(
                lambda b: b.set_start_layout("" if info["start"] else name),
                then=lambda _: self.say("The deck won't switch layouts when it opens" if info["start"]
                                        else f"The deck opens on {name}")))
            if info["background"]:
                bgs = self.menu()
                bgs.add_command(label=("✓  " if not info["default"] else "     ") + "None", command=lambda: self.call(
                    lambda b: b.set_layout_bgs(name, default=""), then=lambda _: self.say("Saved")))
                for pic in info["pictures"]:
                    bgs.add_command(label=("✓  " if pic == info["default"] else "     ") + os.path.splitext(pic)[0],
                                    command=lambda p=pic: self.call(lambda b: b.set_layout_bgs(name, default=p),
                                                                    then=lambda _: self.say("Default background saved")))
                m.add_cascade(label="Default background", menu=bgs)
            tabs = self.menu()
            here = self.meta["tab"].get(name, positions.GENERAL)
            for tab in self.meta["tabs"]:
                tabs.add_command(label=("✓  " if tab == here else "     ") + tab, command=lambda tb=tab: self.call(
                    lambda b: b.set_layout_tab(name, tb), then=lambda _: self.say(f"{name} moved to {tb}")))
            m.add_cascade(label="Tab", menu=tabs)
            colors = self.menu()
            mine = self.meta["color"].get(name, "")
            colors.add_command(label=("✓  " if not mine else "     ") + "Automatic (by kind)", command=lambda: self.call(
                lambda b: b.set_layout_color(name, "")))
            for label, hexcode in self.MARKERS:
                colors.add_command(label=("✓  " if mine == hexcode else "■  ") + label, foreground=hexcode,
                                   command=lambda h=hexcode: self.call(lambda b: b.set_layout_color(name, h)))
            m.add_cascade(label="Color", menu=colors)
            m.add_command(label="Save layout as it is now", command=lambda: self.save_layout(name))
            m.add_command(label="Reset cameras here", command=lambda: self.call(
                lambda b: b.reset_layout(name), then=lambda _: self.say(f"Cameras in {name} back on their default spots")))
            m.add_separator()
            m.add_command(label="Delete layout…", foreground=REC, command=lambda: self.delete_layout(name))
            m.tk_popup(x, y)
        self.call(lambda b: b.layout_info(name), then=show)

    def renamed(self, old, new):
        """A layout was renamed: its own hotkey (Settings → Hotkeys) goes with it."""
        mine = dict(getattr(cfg, "LAYOUT_HOTKEYS", {}) or {})
        if old in mine:
            mine[new] = mine.pop(old)
            self.save_hotkeys(layouts=mine)
        self.say(f"Renamed to {new}")

    def save_layout(self, name=None):
        """Save layout: the live layout (or the one whose ⋯ menu was used) becomes its own default, exactly
        as it is now, including the background picture."""
        name = name or self.current
        if not name:
            return
        self.call(lambda b: b.save_layout(name), then=lambda pic: self.say(
            f"{name} saved as it is now" + (f", with {os.path.splitext(pic)[0]} as its background" if pic else ""),
            seconds=8))

    def delete_layout(self, name):
        if not messagebox.askyesno("Podcast Deck", f"Delete the layout {name} from OBS?\n\nRepair layouts won't "
                                   "bring it back. Settings → Cameras → Bring back deleted layouts will (for the "
                                   "deck's own layouts).", parent=self.root):
            return
        self.call(lambda b: b.delete_layout(name), then=lambda _: self.say(f"{name} deleted"))

    def ask_text(self, title, prompt, initial, done):
        """A small dark box asking for one line of text. done(text) runs on OK or Enter."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title(title)
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text=prompt, bg=BG, fg=INK, font=STATUS_FONT, anchor="w").pack(fill="x")
        e = tk.Entry(win, width=34, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
        e.insert(0, initial)
        e.pack(fill="x", pady=(6, 10), ipady=5)
        e.focus_set()
        e.select_range(0, "end")
        def ok(_e=None):
            text = e.get().strip()
            win.destroy()
            if text:
                done(text)
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x")
        go = self.small_key(row, "OK", ok)
        go.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
        go.pack(side="left")
        self.small_key(row, "Cancel", win.destroy).pack(side="right")
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda _e: win.destroy())

    def paint_row(self, name, hover=False):
        """A layout row's look: the live layout is raised with an accent bar; hovering lightens a row."""
        r = self.buttons.get(name)
        if not r:
            return
        lit = name == self.current
        bg = KEY if lit else (KEY_HOVER if hover and r["live"] else NAV)
        for w in (r["row"], r["label"]):
            w.config(bg=bg)
        r["bar"].config(bg=LIT if lit else bg)
        r["label"].config(fg=INK if (lit or r["live"]) else INK_DIM)
        if r["toggle"]:
            r["toggle"].config(bg=bg, text="−" if name == self.open_layout else "+")
        if r["dots"]:                          # the ⋯ menu button shows on hover
            r["dots"].config(bg=bg, fg=INK_DIM if hover else bg)

    # --- Hotkeys -------------------------------------------------------------
    def layout_hotkeys(self):
        """{layout: hotkey}. Each layout's own from Settings → Hotkeys ("" for none), otherwise
        HOTKEY_PREFIX + its place in the list (1–9). A default that's taken by a hotkey of your own is skipped."""
        mine = getattr(cfg, "LAYOUT_HOTKEYS", {}) or {}
        taken = {k for k in mine.values() if k} | {cfg.RECORD_HOTKEY, BACKGROUND_HOTKEY}
        found = {}
        for i, name in enumerate(self.ordered(self.scenes), start=1):
            if name in mine:
                combo = mine[name]
            else:
                combo = f"{cfg.HOTKEY_PREFIX}{i}" if i <= 9 else ""
                combo = "" if combo in taken else combo
            if combo:
                found[name] = combo
        return found

    def save_hotkeys(self, layouts=None, record=None, background=None):
        """Settings → Hotkeys: remember them in config.py on this PC, and use them straight away."""
        global BACKGROUND_HOTKEY
        values = {}
        if layouts is not None:
            cfg.LAYOUT_HOTKEYS = values["LAYOUT_HOTKEYS"] = layouts
        if record is not None:
            cfg.RECORD_HOTKEY = values["RECORD_HOTKEY"] = record
        if background is not None:
            BACKGROUND_HOTKEY = cfg.BACKGROUND_HOTKEY = values["BACKGROUND_HOTKEY"] = background
        configfile.update(**values)
        self.set_control_hotkeys(True)
        self.rebuild(self.scenes)
        self.refresh_panel()

    def fill_hotkeys(self, frame):
        """Settings → Hotkeys: one row per layout, plus Record and Next background. Change… listens for the
        next keys pressed; Clear turns that hotkey off; Default goes back to the usual one."""
        for w in frame.winfo_children():
            w.destroy()
        keys = self.layout_hotkeys()
        mine = dict(getattr(cfg, "LAYOUT_HOTKEYS", {}) or {})
        rows = [(name, keys.get(name, ""), name in mine) for name in self.ordered(self.scenes)]
        rows += [("● Record", cfg.RECORD_HOTKEY, cfg.RECORD_HOTKEY != "ctrl+alt+r"),
                 ("Next background", BACKGROUND_HOTKEY, BACKGROUND_HOTKEY != "ctrl+alt+b")]
        # Hotkeys you set yourself can't be shared. A layout's usual hotkey just gives way to one of yours.
        in_use = {combo: name for name, combo in mine.items() if combo}
        in_use.update({cfg.RECORD_HOTKEY: "● Record", BACKGROUND_HOTKEY: "Next background"})
        in_use.pop("", None)

        def put(name, combo):
            if name == "● Record":
                self.save_hotkeys(record=combo if combo is not None else "ctrl+alt+r")
            elif name == "Next background":
                self.save_hotkeys(background=combo if combo is not None else "ctrl+alt+b")
            else:
                if combo is None:
                    mine.pop(name, None)
                else:
                    mine[name] = combo
                self.save_hotkeys(layouts=mine)
            self.fill_hotkeys(frame)

        def listen(name, button):
            button.config(text="Press the keys…", bg=LIT, fg=LIT_INK)
            for hk in self.hotkeys + self.control_hotkeys:   # so pressing one doesn't also switch layout
                keyboard.remove_hotkey(hk)
            self.hotkeys, self.control_hotkeys = [], []

            def work():
                combo = keyboard.read_hotkey(suppress=False)
                self.root.after(0, done, combo)

            def done(combo):
                other = in_use.get(combo)
                if combo in ("esc", "escape") or (other and other != name) or not frame.winfo_exists():
                    if other and other != name:
                        self.say(f"{combo} is already used by {other}. Clear that one first.", 8)
                    self.set_control_hotkeys(True)   # put everything back as it was
                    self.rebuild(self.scenes)
                    if frame.winfo_exists():
                        self.fill_hotkeys(frame)
                    return
                put(name, combo)
                self.say(f"{name}: {combo}")
            threading.Thread(target=work, daemon=True).start()

        for r, (name, combo, changed) in enumerate(rows):
            tk.Label(frame, text=name, bg=BG, fg=INK, font=STATUS_FONT, anchor="w").grid(
                row=r, column=0, sticky="w", pady=2)
            tk.Label(frame, text=combo or "none", bg=BG, fg=LIT if combo else MUTED, font=HINT_FONT, anchor="w",
                     width=16).grid(row=r, column=1, sticky="w", padx=(10, 6))
            change = self.small_key(frame, "Change…", None)
            change.config(command=lambda n=name, b=change: listen(n, b))
            change.grid(row=r, column=2, padx=(0, 4))
            self.small_key(frame, "Clear", lambda n=name: put(n, "")).grid(row=r, column=3, padx=(0, 4))
            if changed:
                self.small_key(frame, "Default", lambda n=name: put(n, None)).grid(row=r, column=4)
        frame.columnconfigure(0, weight=1)

    # --- A layout's + panel ------------------------------------------------
    def toggle_panel(self, name):
        """+ opens a layout's panel (switching to it first, since its buttons change what's live); − closes it."""
        if name == self.open_layout:
            self.open_layout = None
        else:
            self.open_layout = name
            if name != self.current:
                self.switch(name)
        for n in self.buttons:
            self.paint_row(n)
        self.refresh_panel()

    def refresh_panel(self):
        """Draw the open layout's panel under its row, once that layout is live. Only redrawn when
        something in it changes, so a click isn't lost to the poll."""
        show = self.open_layout == self.current and self.open_layout in self.buttons
        has_video = any(i["name"] == "Video Panel" for i in self.items)
        key = (show and self.open_layout, tuple(sorted(self.now.items())) if show else None, self.pending_bg, has_video,
               show and self.layout_hotkeys().get(self.open_layout))
        if key == self.panel_key and (not show or (self.panel and self.panel.winfo_exists())):
            return
        self.panel_key = key
        if self.panel is not None and self.panel.winfo_exists():
            self.panel.destroy()
        self.panel = None
        if not show:
            return
        panel = tk.Frame(self.grid, bg=NAV, padx=10, pady=6)
        panel.pack(fill="x", pady=(0, 1), after=self.buttons[self.open_layout]["row"])
        self.panel = panel
        short = lambda t, n: t if len(t) <= n else t[:n - 1] + "…"
        combo = self.layout_hotkeys().get(self.open_layout)
        text = (f"Hotkey: {combo}\n" if combo else "") + "Background: " + short(self.now.get("background") or "plain color", 24)
        if self.now.get("video"):
            text += "\n▶ " + short(self.now["video"], 34)
        tk.Label(panel, text=text, bg=NAV, fg=INK_DIM, font=STATUS_FONT, anchor="w", justify="left").pack(fill="x")
        if self.pending_bg:                    # a pasted background video waits here until someone switches to it
            row = tk.Frame(panel, bg=NAV)
            row.pack(fill="x", pady=(4, 0))
            tk.Label(row, text="Video ready", bg=NAV, fg=LIT, font=STATUS_FONT,
                     anchor="w").pack(side="left")
            self.small_key(row, "✕", self.hide_pending).pack(side="right")
            go = self.small_key(row, "Switch", self.switch_background)
            go.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
            go.pack(side="right", padx=4)
        keys = tk.Frame(panel, bg=NAV)
        keys.pack(fill="x", pady=(6, 0))
        buttons = [("Background ▾", self.background_menu), ("Paste link", self.bg_link_box)]
        if has_video:                          # only where there's a video box to play in
            buttons.append(("Play link…", self.play_link))
        buttons.append(("Save layout", self.save_layout))
        for i, (label, cmd) in enumerate(buttons):
            b = self.small_key(keys, label, cmd)
            b.config(padx=6, anchor="center")
            b.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 3, 0), pady=(0 if i < 2 else 3, 0),
                   ipady=4)
            if i == 0:
                self.bg_button = b
        keys.columnconfigure(0, weight=1)
        keys.columnconfigure(1, weight=1)

    # --- Who's on the show ----------------------------------------------------
    def show_people(self):
        """(name, square color) for the row at the top: everyone on your show and in your group. Green while
        their camera is showing in your OBS, gray while it isn't."""
        names = link.clean_names(list(cfg.CAMS) + group_people())
        return [(n, OK if self.live.get(n) else MUTED) for n in names]

    def draw_people(self):
        """The row under the header: a small square and name per person, and Invite / Join on the right.
        Click a name to take them off your show."""
        shown = [(name, self.names.get(name) or name, color) for name, color in self.show_people()]
        if shown == self.people_shown:
            return
        self.people_shown = shown
        for w in self.people_row.winfo_children():
            w.destroy()
        self.people_items = []
        for name, label, color in shown:
            item = tk.Frame(self.people_row, bg=BG)
            square = tk.Frame(item, bg=color, width=9, height=9)
            square.pack(side="left", padx=(0, 5))
            text = tk.Label(item, text=label, bg=BG, fg=INK if color != MUTED else INK_DIM, font=STATUS_FONT)
            text.pack(side="left", padx=(0, 12))
            if name != getattr(cfg, "ME", ""):
                for w in (item, square, text):
                    w.config(cursor="hand2")
                    w.bind("<Button-1>", lambda e, n=name: self.person_menu(n, e))
                    w.bind("<Button-3>", lambda e, n=name: self.person_menu(n, e))
            self.people_items.append(item)
        self.group_button = self.small_key(self.people_row, "Invite / Join", self.group_box)
        self.group_button.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK, pady=2)
        self.flow_people()

    def flow_people(self):
        """Lay out the who's-on row: Invite / Join on the right, names left to right beside it, wrapping onto
        more lines when the window is narrow."""
        if getattr(self, "flowing", False):
            return
        self.flowing = True
        try:
            self.people_row.update_idletasks()   # so new names have their real sizes
        finally:
            self.flowing = False
        width = self.people_row.winfo_width()
        if width <= 1:                         # not drawn yet: <Configure> calls this again
            width = self.root.winfo_width() - 24
        button = getattr(self, "group_button", None)
        line = 0
        if button is not None and button.winfo_exists():
            button.place(relx=1.0, x=0, y=0, anchor="ne")
            width -= button.winfo_reqwidth() + 8
            line = button.winfo_reqheight()
        x = y = 0
        for item in self.people_items:
            w, h = item.winfo_reqwidth(), item.winfo_reqheight()
            if x and x + w > width:
                x, y = 0, y + line
                line = 0
            item.place(x=x, y=y + 4 if y == 0 else y)   # first line: centered on the button
            x, line = x + w, max(line, h)
        height = y + line or 20
        if int(self.people_row.cget("height")) != height:
            self.people_row.config(height=height)

    def person_menu(self, name, event):
        """Click someone in the row: take them off your show (their own deck isn't affected)."""
        m = self.menu()
        m.add_command(label=name, state="disabled")
        m.add_command(label="Remove from my show…", foreground=REC, command=lambda: self.remove_person(name))
        m.tk_popup(event.x_root, event.y_root)

    def remove_person(self, name):
        """Take someone off your show: their camera leaves your layouts, and your group link leaves them out."""
        if not messagebox.askyesno("Podcast Deck", f"Take {name} off your show?\n\nTheir camera leaves your layouts. "
                                   "Their own deck isn't affected.", parent=self.root):
            return
        if name in getattr(cfg, "GROUP_PEOPLE", []):
            cfg.GROUP_PEOPLE = [n for n in cfg.GROUP_PEOPLE if n != name]
        if name in cfg.CAMS:
            cfg.CAMS = [n for n in cfg.CAMS if n != name]
        configfile.update(CAMS=cfg.CAMS, GROUP_PEOPLE=list(getattr(cfg, "GROUP_PEOPLE", [])))
        self.people_shown = None
        self.layouts_changed(f"{name} is off your show.")

    def layouts_changed(self, message):
        """Your show's people changed: rebuild your layouts with their cameras (after the recording, if one
        is running)."""
        self.draw_people()
        self.call(lambda b: b.rebuild_soon(), then=lambda msg: self.say(f"{message} {msg}", 8))

    # --- The group ---------------------------------------------------------------
    def group_box(self):
        """Invite / Join: the group link to send everyone, adding someone, and joining another group."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title("Invite / Join")
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        win.bind("<Escape>", lambda _e: win.destroy())

        def heading(text, first=False):
            tk.Label(win, text=text, bg=BG, fg=INK, font=FONT, anchor="w").pack(fill="x", pady=(0 if first else 16, 0))

        def say(text, color=INK_DIM):
            label = tk.Label(win, text=text, bg=BG, fg=color, font=STATUS_FONT, anchor="w", justify="left",
                             wraplength=380)
            label.pack(fill="x", pady=(4, 0))
            return label

        def box(value="", readonly=False):
            e = tk.Entry(win, width=44, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT,
                         readonlybackground=KEY)
            e.insert(0, value)
            if readonly:
                e.config(state="readonly")
            e.pack(fill="x", pady=(6, 0), ipady=6)
            return e

        group = getattr(cfg, "GROUP", "")
        heading("Invite people", first=True)
        if group:
            say("Send this link to everyone on the show. It's the same for everyone, and it walks them through "
                "downloading the deck and joining. Keep it within the group.")
            link_box = box(link.group_link(group, group_people()), readonly=True)
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", pady=(6, 0))
            self.small_key(row, "Copy link", lambda: self.copy_group_link()).pack(side="left")
            self.small_key(row, "New link…", lambda: self.new_group_link(win)).pack(side="left", padx=6)
        else:
            say("Start a group, then send its link to everyone on the show.")
            link_box = None
            self.small_key(win, "Start a group", lambda: (self.start_group(), win.destroy(), self.group_box())).pack(
                anchor="w", pady=(6, 0))

        heading("Add someone")
        say("Their name, as they'll type it when they join:")
        name_box = box()
        here = tk.BooleanVar(value=False)
        if RECORD:
            tk.Checkbutton(win, text="They're here with me (their camera is on this PC)", variable=here, bg=BG,
                           fg=INK_DIM, selectcolor=KEY, activebackground=BG, activeforeground=INK, font=STATUS_FONT,
                           anchor="w").pack(fill="x", pady=(4, 0))
        note = say("", REC)

        def add(_e=None):
            name = link.clean_names([name_box.get()])
            if not name:
                note.config(text="Type their name first.")
                return
            name = name[0]
            if any(n.casefold() == name.casefold() for n in list(cfg.CAMS) + group_people()):
                note.config(text=f"{name} is already on your show.")
                return
            self.add_person(name, joining=not here.get())
            win.destroy()
        self.small_key(win, "Add", add).pack(anchor="w", pady=(6, 0))
        name_box.bind("<Return>", add)

        heading("Join a group")
        say("Got a group link from someone? Paste it here." + (" You'll leave your current group." if group else ""))
        try:
            clip = self.root.clipboard_get().strip()
        except tk.TclError:
            clip = ""
        code_box = box(find_invite(clip) or "")
        code_note = say("")

        def join(_e=None):
            text = find_invite(code_box.get())
            if not text:
                code_note.config(text="That doesn't look like a group link. Paste the whole link.", fg=REC)
                return
            win.destroy()
            self.offer_invite(text)
        self.small_key(win, "Join", join).pack(anchor="w", pady=(6, 0))
        code_box.bind("<Return>", join)
        self.key(win, "Close", win.destroy).pack(anchor="e", pady=(16, 0))
        if link_box is None:
            name_box.focus_set()

    def copy_group_link(self):
        text = link.group_link(cfg.GROUP, group_people())
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.say("Group link copied. Send it to everyone on the show.", 8)
        return text

    def new_group_link(self, win):
        """A link got out: a new group code for the same people. The old link stops showing anyone's camera."""
        if not messagebox.askyesno("Podcast Deck", "Make a new group link? The old one stops working, so everyone "
                                   "needs the new one (it's copied for you).", parent=win):
            return
        cfg.GROUP = link.new_group()
        configfile.update(GROUP=cfg.GROUP)
        win.destroy()
        self.copy_group_link()
        self.after_group_change("New group link copied. Send it to everyone.")

    def start_group(self):
        """A new group with everyone on your show who isn't here with you (and you)."""
        me = getattr(cfg, "ME", "") or (cfg.CAMS[0] if cfg.CAMS else "Host 1")
        cfg.GROUP, cfg.ME = link.new_group(), me
        cfg.GROUP_PEOPLE = link.clean_names([me] + list(cfg.CAMS))
        configfile.update(GROUP=cfg.GROUP, ME=me, GROUP_PEOPLE=cfg.GROUP_PEOPLE)
        self.after_group_change("Group started.")

    def add_person(self, name, joining=True):
        """Add someone to your show. Someone joining from elsewhere goes into the group too (their camera comes
        through it); someone here with you gets a webcam on this PC."""
        if RECORD:
            cfg.CAMS = list(cfg.CAMS) + [name]
            configfile.update(CAMS=cfg.CAMS)
        if joining:
            if not getattr(cfg, "GROUP", ""):
                self.start_group()
            cfg.GROUP_PEOPLE = link.clean_names(list(cfg.GROUP_PEOPLE) + [name])
            configfile.update(GROUP_PEOPLE=cfg.GROUP_PEOPLE)
            self.copy_group_link()
        self.after_group_change(f"{name} added." + (" The group link is copied: send it to everyone again so "
                                                    "their decks know." if joining else ""))

    def offer_invite(self, text):
        """A group link was clicked or pasted. Ask first (links can come from anywhere), then join it."""
        found = link.find_group(text)
        if not found:
            return
        group, names = found
        self.root.deiconify()
        self.root.lift()
        if group == getattr(cfg, "GROUP", "") and set(names) <= set(group_people()):
            self.say("You're already in that group.")
            return
        who = ", ".join(names) if names else "this group"
        if not messagebox.askyesno("Podcast Deck", f"Join the group with {who}?\n\nTheir cameras go into your show, "
                                   "and yours to theirs. Nobody can control your OBS.", parent=self.root):
            return
        me = getattr(cfg, "ME", "")
        if not me:
            self.ask_text("Join a group", "Your name, as the others know you:", "", lambda typed: self.join_group(
                group, names, typed))
            return
        self.join_group(group, names, me)

    def join_group(self, group, names, me):
        me = link.clean_names([me])[0] if link.clean_names([me]) else "Me"
        known = {n.casefold(): n for n in names}
        me = known.get(me.casefold(), me)      # use the spelling the group already has
        people = link.clean_names(names + [me])
        here = [n for n in cfg.CAMS if n not in group_people() and n != me] if RECORD else []
        cfg.GROUP, cfg.GROUP_PEOPLE, cfg.ME = group, people, me
        values = dict(GROUP=group, GROUP_PEOPLE=people, ME=me)
        if RECORD:
            cfg.CAMS = values["CAMS"] = link.clean_names(people + here)
        configfile.update(**values)
        added = me not in names
        if added:                              # tell the others: the link now has you in it
            self.copy_group_link()
        self.after_group_change("Joined the group." + (" You weren't in its link yet: the new link is copied, "
                                                       "send it to everyone." if added else ""))

    def after_group_change(self, message):
        """The group changed: redraw, rebuild the layouts (recording deck), and offer to send the camera."""
        self.people_shown = None
        self.redraw()                          # Start my camera shows once you're in a group with others
        self.layouts_changed(message)

    def switch_mode(self):
        """Switch this PC between recording (its own show, with OBS) and camera only."""
        to_record = not RECORD
        question = ("Record your own show on this PC? You'll need OBS installed." if to_record else
                    "Switch this PC to camera only? It stops running a show; your layouts in OBS aren't touched, "
                    "and you can switch back any time.")
        if messagebox.askyesno("Podcast Deck", question, parent=self.root):
            values = {"RECORD": to_record}
            if to_record and getattr(cfg, "ME", "") and cfg.ME not in cfg.CAMS:
                values["CAMS"] = link.clean_names([cfg.ME] + group_people())
            configfile.update(**values)
            self.restart()

    def check_update(self):
        """Installed app: if there's a newer version, install it and reopen. Never mid-recording."""
        if not updater.installed():
            return

        def work():
            url = updater.newer()
            if url:
                self.root.after(0, go, url)

        def go(url):
            if self.recording:
                self.say("A deck update is ready. It installs the next time you open the deck.", 8)
                return
            self.status.config(text="Updating Podcast Deck… it reopens in a moment.")

            def fetch():
                try:
                    updater.install(url)
                except OSError:
                    self.root.after(0, self.say, "Couldn't download the update. The deck tries again next time.", 8)
                    return
                self.root.after(0, self.closing)
            threading.Thread(target=fetch, daemon=True).start()
        threading.Thread(target=work, daemon=True).start()

    def restart(self):
        """Open the deck again (after switching between recording and camera only)."""
        args = [sys.executable] + [a for a in (sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv)
                                   if not find_invite(a)]   # don't offer a clicked link again
        subprocess.Popen(args, cwd=media.APP_DIR, env=dict(os.environ, PODCAST_DECK_WAIT="2"))
        self.closing()


class CameraDeck(Deck):
    """The window on a PC that doesn't record: who's in the group, Start my camera, and Invite / Join. It
    never touches OBS."""

    def __init__(self, root):
        self.root = root
        self.backend, self.recording, self.last_state = None, False, None
        self.names, self.live, self.camera_on = {}, {}, False
        self.notice, self.notice_until = "", 0.0
        self.people_shown, self.people_items = None, []
        root.title("Podcast Deck · camera only")
        root.attributes("-topmost", True)
        root.geometry("320x420")
        root.minsize(260, 320)
        self.build_ui()
        listen_for_invites(lambda text: root.after(0, self.offer_invite, text))
        root.after(3000, self.check_update)

    def build_ui(self):
        root = self.root
        root.configure(bg=BG)
        header = tk.Frame(root, bg=PANEL)
        header.pack(fill="x")
        tk.Frame(root, bg=LINE, height=1).pack(fill="x")
        tk.Label(header, text="P", bg=LIT, fg=LIT_INK, font=LABEL_FONT, width=2).pack(side="left", padx=(12, 8), pady=10)
        tk.Label(header, text="PODCAST DECK", bg=PANEL, fg=INK, font=BRAND_FONT).pack(side="left")
        self.people_row = tk.Frame(root, bg=BG, height=20)
        self.people_row.pack(fill="x", padx=12, pady=(8, 0))
        self.people_row.bind("<Configure>", lambda _e: self.flow_people())
        self.people_shown = None

        bar = tk.Frame(root, bg=PANEL)
        bar.pack(side="bottom", fill="x")
        tk.Frame(root, bg=LINE, height=1).pack(side="bottom", fill="x")
        in_group = bool(getattr(cfg, "GROUP", ""))
        self.status = tk.Label(bar, text="Camera only: this PC doesn't record." if in_group else
                               "Not in a group yet.", bg=PANEL, fg=INK_DIM, font=STATUS_FONT, anchor="w",
                               justify="left", wraplength=290)
        self.status.pack(fill="x", padx=12, pady=6)

        body = tk.Frame(root, bg=BG, padx=12)
        body.pack(fill="both", expand=True)
        self.section(body, "YOUR CAMERA").pack(fill="x", pady=(14, 4))
        if in_group:
            tk.Label(body, text="Everyone recording shows your camera in their own show. Keep the camera tab open "
                                "while you're on.", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w", justify="left",
                     wraplength=290).pack(fill="x")
            start = self.key(body, "▶  Start my camera", self.start_camera)
            start.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK, anchor="center")
            start.pack(fill="x", pady=(10, 0), ipady=8)
        else:
            tk.Label(body, text="Got a group link? Click Invite / Join and paste it, or open the link and click "
                                "Join.", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w", justify="left",
                     wraplength=290).pack(fill="x")
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", side="bottom", pady=(0, 10))
        self.small_key(row, "Settings…", self.settings_box).pack(side="right")
        self.draw_people()

    def show_people(self):
        """Everyone in the group. This PC can't see the others' cameras, so only yours goes green (once
        you've started it)."""
        return [(n, OK if self.camera_on and n == getattr(cfg, "ME", "") else MUTED) for n in group_people()]

    def start_camera(self):
        Deck.start_camera(self)
        self.camera_on = True
        self.people_shown = None
        self.draw_people()

    def layouts_changed(self, message):
        self.draw_people()                     # no OBS here: nothing to rebuild
        self.say(message, 8)

    def redraw(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.build_ui()

    def settings_box(self, tab=None):
        """Your name, and switching this PC to recording."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title("Settings")
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        win.bind("<Escape>", lambda _e: win.destroy())
        tk.Label(win, text="Your name", bg=BG, fg=INK, font=FONT, anchor="w").pack(fill="x")
        tk.Label(win, text="As the others know you. It's on your camera in everyone's show.", bg=BG, fg=INK_DIM,
                 font=STATUS_FONT, anchor="w").pack(fill="x")
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        name_box = tk.Entry(row, width=28, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
        name_box.insert(0, getattr(cfg, "ME", ""))
        name_box.pack(side="left", ipady=5)

        def save(_e=None):
            new = link.clean_names([name_box.get()])
            if not new or new[0] == getattr(cfg, "ME", ""):
                return
            old, cfg.ME = getattr(cfg, "ME", ""), new[0]
            cfg.GROUP_PEOPLE = link.clean_names([cfg.ME if n == old else n for n in group_people()] + [cfg.ME])
            configfile.update(ME=cfg.ME, GROUP_PEOPLE=cfg.GROUP_PEOPLE)
            if getattr(cfg, "GROUP", ""):
                self.copy_group_link()
            self.after_group_change("Name saved. The group link is copied: send it to everyone so their decks "
                                    "show your new name.")
        name_box.bind("<Return>", save)
        self.small_key(row, "Save", save).pack(side="left", padx=6)
        tk.Label(win, text="This PC", bg=BG, fg=INK, font=FONT, anchor="w").pack(fill="x", pady=(16, 0))
        tk.Label(win, text="Have OBS? Record your own show here, with everyone's cameras.", bg=BG, fg=INK_DIM,
                 font=STATUS_FONT, anchor="w").pack(fill="x")
        self.small_key(win, "Record my own show…", self.switch_mode).pack(anchor="w", pady=(6, 0))
        self.key(win, "Close", win.destroy).pack(anchor="e", pady=(16, 0))


def open_deck(root):
    """The recording deck, or the camera-only window, as config.py says."""
    deck = Deck(root) if RECORD else CameraDeck(root)
    root.protocol("WM_DELETE_WINDOW", deck.closing)
    return deck


def welcome(root, invite=None):
    """First launch: your name, and whether this PC records its own show or just sends a camera. Then
    config.py is written and the deck opens. Opened from a group link, you join that group."""
    root.title("Podcast Deck")
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.geometry("420x420")
    frame = tk.Frame(root, bg=BG, padx=20, pady=18)
    frame.pack(fill="both", expand=True)
    key = lambda parent, text, cmd: Deck.key(None, parent, text, cmd)   # the deck's button style, no deck yet
    found = link.find_group(invite) if invite else None

    def clear():
        for w in frame.winfo_children():
            w.destroy()

    def label(text, font=STATUS_FONT, color=INK_DIM):
        tk.Label(frame, text=text, bg=BG, fg=color, font=font, anchor="w", justify="left",
                 wraplength=370).pack(fill="x", pady=(0, 8))

    def entry(value):
        e = tk.Entry(frame, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
        e.insert(0, value)
        e.pack(fill="x", ipady=6, pady=(0, 6))
        e.focus_set()
        return e

    def done(me, record, group="", names=()):
        names = list(names)
        known = {n.casefold(): n for n in names}
        me = known.get(me.casefold(), me)
        people = link.clean_names(names + [me]) if group else []
        values = dict(RECORD=record, ME=me, GROUP=group, GROUP_PEOPLE=people)
        if record:
            values["CAMS"] = people or [me]
        if configfile.load() is None:
            configfile.create(**values)
        else:
            configfile.update(**values)
        use_config(configfile.load())
        root.unbind("<Return>")
        frame.destroy()
        deck = open_deck(root)
        if group and me not in names:          # the others' link doesn't have you yet
            deck.copy_group_link()
            deck.say("You're in. The group link now includes you and is copied: send it to everyone.", 12)

    def first():
        clear()
        label("Podcast Deck", FONT, INK)
        if found:
            label("You're joining the group with " + (", ".join(found[1]) or "your friends") + ".")
        label("Your name, as the others know you (it's on your camera):")
        name = entry(os.environ.get("USERNAME", ""))
        problem = tk.Label(frame, text="", bg=BG, fg=REC, font=STATUS_FONT, anchor="w")
        problem.pack(fill="x")
        label("Does this PC record its own show?")

        def go(record):
            me = link.clean_names([name.get()])
            if not me:
                problem.config(text="Type your name first.")
                return
            if found:
                done(me[0], record, *found)
            elif record:
                others(me[0])
            else:
                done(me[0], False)
        big = dict(fill="x", ipady=10, pady=4)
        key(frame, "Record my own show (this PC has OBS)", lambda: go(True)).pack(**big)
        key(frame, "Camera only (just send my camera)", lambda: go(False)).pack(**big)

    def others(me):
        clear()
        label("Who else is on the show?", FONT, INK)
        label("Names, separated by commas. Leave it empty if it's just you; you can add people any time with "
              "Invite / Join.")
        names = entry("")

        def go(_e=None):
            done(me, True, link.new_group(), [me] + [n for n in names.get().split(",")])
        key(frame, "Start", go).pack(anchor="e", pady=(8, 0))
        root.bind("<Return>", go)

    first()


if __name__ == "__main__":
    time.sleep(float(os.environ.pop("PODCAST_DECK_WAIT", 0) or 0))   # a restart: let the old window close first
    opened_with = next((find_invite(a) for a in sys.argv[1:] if find_invite(a)), None)   # a group link was clicked
    if opened_with and hand_to_running_deck(opened_with):
        sys.exit()                             # the deck that's already open takes it
    root = tk.Tk()
    if cfg is None:
        welcome(root, opened_with)
    else:
        deck = open_deck(root)
        if opened_with:
            root.after(800, deck.offer_invite, opened_with)
    root.mainloop()
