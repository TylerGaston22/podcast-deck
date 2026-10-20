"""Desktop stream deck for OBS.

A small always-on-top window with one button per layout and a Record button,
plus global hotkeys (ctrl+alt+1..9 for layouts, ctrl+alt+r for record) and
optional mouse side buttons, all of which work while a game has focus. Buttons are read live from OBS, so any scene you
add later shows up automatically. The Background menu and Play link box change the
background picture and the Video + Cams video without opening OBS.

Hosts joining online run the deck too, as guests. The admin's deck (on the PC that runs OBS and
records) is the only thing that touches OBS. Guests' decks send it requests over Tailscale, using
an invite from the admin, and the admin's deck checks each one first. Guests can always move their
own camera on the screen map, and get every other control when the admin turns on full control.

The first launch asks one question (recording, or joining?) and writes config.py itself.

    py C:\\Users\\<you>\\source\\repos\\podcast-deck\\deck.py
"""
import os
import subprocess
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
from theme import BRAND_FONT, FONT, HINT_FONT, LABEL_FONT, ROW_FONT, STATUS_FONT


def paint():
    """Copy the current color scheme's colors (BG, LIT, OK, …) into this module's globals."""
    globals().update(theme.tokens())


paint()

HANDLE = 10                                    # px: grab this close to a box's corner to resize it
NOTES = os.path.join(media.APP_DIR, "NOTES.md")
cfg, ADMIN, DECK_PORT, BACKGROUND_HOTKEY = None, True, 4460, "ctrl+alt+b"


def use_config(found):
    global cfg, ADMIN, DECK_PORT, BACKGROUND_HOTKEY
    cfg = found
    ADMIN = getattr(cfg, "ADMIN", True)        # older config.py files are the single-PC setup
    DECK_PORT = getattr(cfg, "DECK_PORT", 4460)
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


class Deck:
    def __init__(self, root):
        self.root = root
        self.backend, self.setup_problem, self.link = None, None, None
        self.linking, self.next_link_try = False, 0.0
        try:
            self.backend = control.Local(cfg) if ADMIN else None
        except DeckError as e:
            self.setup_problem = str(e)

        self.scenes, self.current, self.recording = [], None, False
        self.full, self.built_full = False, None   # guests: whether the admin gave them full control
        self.me = f"Cam - {cfg.ME}" if ADMIN and getattr(cfg, "ME", "") else None
        self.buttons = {}
        self.hotkeys, self.control_hotkeys = [], []
        self.notice, self.notice_until = "", 0.0
        self.canvas = (cfg.CANVAS_W, cfg.CANVAS_H)
        self.items = []                        # cams and the video box in the current layout
        self.selected = self.me
        self.drag, self.pending, self.sending = None, None, False
        self.guides = []                       # snap lines shown while dragging
        self.hold_until = 0.0                  # keep the map as dragged until OBS has caught up
        self.names, self.sent_name = {}, False  # display names guests chose, by cam name
        self.now = {}                          # what's showing: background and video titles
        self.bg_preview = None                 # the pasted background video's place in its preview
        self.mine = {"bg": False, "video": False}   # whether this deck's control page runs each channel live
        self.bg = bgcontrol.BgControl(self, ADMIN)    # this PC only: the browser control page, and OBS's feed

        self.last_state = None                 # the last OBS state, to redraw after a color scheme change
        self.meta = {"tabs": [positions.GENERAL], "tab": {}, "color": {}}   # layout tabs and marker colors
        self.tab = positions.GENERAL           # the tab being shown
        root.title("Podcast Deck" if ADMIN else "Podcast Deck · guest")
        root.attributes("-topmost", True)
        root.geometry("320x880" if ADMIN else "320x600")
        root.minsize(260, 320)
        self.build_ui()
        self.set_control_hotkeys(ADMIN)

        if cfg.MOUSE_BUTTONS:
            mouse.hook(self.on_mouse)
        if self.setup_problem:
            self.status.config(text=self.setup_problem)
        else:
            self.poll()

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
        self.obs_pill = self.pill(header, "OBS" if ADMIN else "ADMIN")
        self.obs_pill["frame"].pack(side="right", padx=(4, 12))
        self.rec_pill = self.pill(header, "REC")

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
        if ADMIN:                              # always in view, however many layouts there are
            new = tk.Label(head, text="＋ New layout", bg=BG, fg=LIT, font=LABEL_FONT, cursor="hand2", padx=8)
            new.pack(side="left")
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
        self.reset_button = self.small_key(under, "Reset camera" if ADMIN else "Reset my camera", self.reset_camera)
        self.reset_button.pack(side="left")
        if ADMIN:
            self.small_key(under, "Save layout", self.save_layout).pack(side="left", padx=4)
        self.small_key(under, "Settings…", self.settings_box).pack(side="right")
        if not ADMIN:
            start = self.small_key(under, "Start my camera", self.start_camera)
            start.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
            start.pack(side="right", padx=4)

        # Media and Record: always on the admin deck, on guests' only with full control.
        self.controls = tk.Frame(bottom, bg=BG)
        self.controls.pack(fill="x")
        self.section(self.controls, "MEDIA").pack(fill="x", pady=(10, 4))
        self.now_label = tk.Label(self.controls, text="", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w")
        self.now_label.pack(fill="x")
        # A pasted background video waits here until someone switches to it.
        self.pending_row = tk.Frame(self.controls, bg=BG)
        tk.Label(self.pending_row, text="Video ready in your browser", bg=BG, fg=LIT,
                 font=STATUS_FONT, anchor="w").pack(side="left")
        self.small_key(self.pending_row, "✕", self.hide_pending).pack(side="right")
        switch = self.small_key(self.pending_row, "Switch", self.switch_background)
        switch.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
        switch.pack(side="right", padx=4)
        extras = tk.Frame(self.controls, bg=BG)
        extras.pack(fill="x", pady=(6, 0))
        self.extras = extras
        # Small, side by side: the background menu, its Paste link box, and the Video + Cams link box.
        for col, (text, cmd) in enumerate((("Background ▾", self.background_menu), ("Paste link", self.bg_link_box),
                                          ("Play link…", self.play_link))):
            b = self.small_key(extras, text, cmd)
            b.config(padx=6, anchor="center")
            b.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 3, 0), ipady=6)
            extras.columnconfigure(col, weight=1)
            if col == 0:
                self.bg_button = b
        self.rec = self.key(self.controls, "●  Record", self.toggle_record)
        self.rec.pack(fill="x", pady=(10, 12), ipady=8)
        if not ADMIN and not self.full:
            self.controls.pack_forget()

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
        for w in self.root.winfo_children():
            w.destroy()
        self.scenes, self.buttons = [], {}     # layout rows are rebuilt on the next draw
        self.now = {}                          # and the Now line is refilled
        self.build_ui()
        if self.last_state:
            self.render(self.last_state, None)
        self.root.after(50, lambda: self.settings_box(tab="Look"))

    def on_mouse(self, event):
        if not isinstance(event, mouse.ButtonEvent) or event.event_type != mouse.DOWN:
            return
        action = cfg.MOUSE_BUTTONS.get(event.button)
        if action is None or not self.can_control():
            return
        if action == "record":
            self.root.after(0, self.toggle_record)
        elif action == "next":
            self.root.after(0, self.next_scene)
        elif action == "next background":
            self.root.after(0, self.next_background)
        else:
            self.root.after(0, self.switch, action)

    def can_control(self):
        """Layouts, recording, background, video, and every camera: the admin, or guests given full control."""
        return ADMIN or self.full

    def next_scene(self):
        if not self.scenes or not self.can_control():
            return
        i = self.scenes.index(self.current) if self.current in self.scenes else -1
        self.switch(self.scenes[(i + 1) % len(self.scenes)])

    # --- Talking to OBS (admin) or the admin's deck (guests) ----------------
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
        self.ensure_link()
        if self.backend is not None:
            self.call(lambda b: None)
        self.root.after(2000, self.poll)

    def ensure_link(self):
        """Admin: open the door for guests. Guest: connect to the admin's deck. Both over Tailscale only.

        Tailscale may be started after the deck, so this keeps trying every ten seconds until it works.
        """
        need = (ADMIN and not (self.link and self.link.httpd)) or (not ADMIN and self.backend is None)
        if not need or self.linking or time.monotonic() < self.next_link_try:
            return
        self.linking, self.next_link_try = True, time.monotonic() + 10

        def work():
            try:
                result, problem = (link.LinkServer(self.backend, DECK_PORT) if ADMIN
                                   else control.Remote(getattr(cfg, "INVITE", ""))), None
            except DeckError as e:
                result, problem = None, str(e)
            self.root.after(0, done, result, problem)

        def done(result, problem):
            self.linking = False
            if ADMIN:
                self.link = result
            elif result:
                self.backend = result
            else:
                self.status.config(text=problem)
        threading.Thread(target=work, daemon=True).start()

    def switch(self, name):
        if self.can_control():
            self.call(lambda b: b.switch(name))

    def toggle_record(self):
        if self.can_control():
            self.call(lambda b: b.toggle_record())

    def set_full(self, full):
        self.call(lambda b: b.set_full(full),
                  then=lambda _: self.say("Guests now have full control" if full
                                          else "Guests can only move their own camera now"))

    def set_control_hotkeys(self, on):
        for hk in self.control_hotkeys:
            keyboard.remove_hotkey(hk)
        self.control_hotkeys = [
            keyboard.add_hotkey(cfg.RECORD_HOTKEY, lambda: self.root.after(0, self.toggle_record)),
            keyboard.add_hotkey(BACKGROUND_HOTKEY, lambda: self.root.after(0, self.next_background)),
        ] if on else []

    # --- Settings -----------------------------------------------------------
    def settings_box(self, tab=None):
        """Admin: tabs for Cameras, Backgrounds, Guests, and Help. Guest: change invite, and Help."""
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

        if ADMIN:
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

            guests_page = page("Guests")
            heading(guests_page, "Guests", first=True)
            on = self.link and self.link.httpd
            note(guests_page, f"Guests connect over Tailscale ({self.link.ip}). Send each person their own invite, "
                              "privately." if on else "Tailscale isn't running on this PC, so guests can't connect "
                              "yet. Start Tailscale; the deck notices within ten seconds.", INK_DIM if on else REC)
            rows = tk.Frame(guests_page, bg=BG)
            rows.pack(fill="x", pady=(4, 0))
            self.fill_guests(rows, on)
            heading(guests_page, "Full control")
            note(guests_page, "Off: guests can only move their own camera. On: they get every control here "
                              "(layouts, Record, backgrounds, videos, every camera). Only you can change this.")
            full = tk.BooleanVar(value=self.full)
            tk.Checkbutton(guests_page, text="Guests get full control", variable=full, anchor="w",
                           command=lambda: self.set_full(full.get()), bg=BG, fg=INK, selectcolor=KEY,
                           activebackground=BG, activeforeground=INK, font=STATUS_FONT).pack(fill="x", pady=(4, 0))
        else:
            you_page = page("You")
            heading(you_page, "Your name", first=True)
            note(you_page, "Shown on your camera and on everyone's screen map.")
            row = tk.Frame(you_page, bg=BG)
            row.pack(fill="x", pady=(4, 0))
            name_box = tk.Entry(row, width=28, bg=KEY, fg=INK, insertbackground=INK, relief="flat", font=STATUS_FONT)
            name_box.insert(0, getattr(cfg, "DISPLAY_NAME", "") or (self.me or "").removeprefix("Cam - "))
            name_box.pack(side="left", ipady=5)
            save = lambda _e=None: self.set_display_name(name_box.get())
            name_box.bind("<Return>", save)
            self.small_key(row, "Save", save).pack(side="left", padx=6)

            heading(you_page, "Invite")
            note(you_page, "Got a new invite from the admin? Copy it, then click Paste invite.")
            self.small_key(you_page, "Paste invite", lambda: self.paste_invite(win)).pack(anchor="w", pady=(4, 0))

        help_page = page("Help")
        heading(help_page, "Help", first=True)
        note(help_page, "How hosts joining online works, what each deck can do, and how it's kept safe.")
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

    def fill_guests(self, rows, on):
        for w in rows.winfo_children():
            w.destroy()
        invites = link.load_invites()
        for r, name in enumerate(n for n in cfg.CAMS if f"Cam - {n}" != self.me):
            shown = self.names.get(name)
            tk.Label(rows, text=f"{name} · {shown}" if shown else name, bg=BG, fg=INK, font=STATUS_FONT,
                     anchor="w").grid(row=r, column=0, sticky="w")
            tk.Label(rows, text="invited" if name in invites else "not invited", bg=BG, fg=INK_DIM,
                     font=STATUS_FONT).grid(row=r, column=1, padx=10)
            copy = self.small_key(rows, "Copy invite", lambda n=name: self.copy_invite(rows, on, n, fresh=False))
            copy.config(state="normal" if on else "disabled")
            copy.grid(row=r, column=2, pady=2)
            if name in invites:
                self.small_key(rows, "New", lambda n=name: self.copy_invite(rows, on, n, fresh=True)).grid(
                    row=r, column=3, padx=4)
                self.small_key(rows, "Remove", lambda n=name: self.remove_invite(rows, on, n)).grid(row=r, column=4)

    def copy_invite(self, rows, on, name, fresh):
        code = link.load_invites().get(name)
        if fresh or not code:
            code = link.new_invite(name)
        self.root.clipboard_clear()
        self.root.clipboard_append(link.invite_text(self.link.ip, DECK_PORT, code))
        self.say(f"Invite for {name} copied. Send it to them privately."
                 + (" Their old invite no longer works." if fresh else ""), seconds=8)
        self.fill_guests(rows, on)

    def remove_invite(self, rows, on, name):
        link.remove_invite(name)
        self.say(f"{name}'s invite removed. Their deck can't connect any more.", seconds=8)
        self.fill_guests(rows, on)

    def paste_invite(self, win=None):
        """Guest: take a new invite from the clipboard and reconnect with it."""
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            text = ""
        if not text.startswith(link.PREFIX):
            self.tell("There's no invite on the clipboard. Copy the whole invite the admin sent you, then try again.")
            return
        configfile.update(INVITE=text)
        cfg.INVITE = text
        self.backend, self.next_link_try = None, 0.0
        self.say("Invite saved. Connecting…")
        if win:
            win.destroy()

    def set_display_name(self, text):
        """Guest: the name shown on your camera. Saved here and sent to the admin's deck."""
        shown = positions.clean_display_name(text)
        configfile.update(DISPLAY_NAME=shown)
        cfg.DISPLAY_NAME = shown
        if self.backend is None:
            self.say("Name saved. It's sent when your deck connects.")
            return
        self.call(lambda b: b.set_display_name(shown), then=lambda now: self.say(f"Your camera now shows: {now}"))

    # --- Camera (guest) ----------------------------------------------------
    def start_camera(self):
        """Guest: send your camera and mic with VDO.Ninja, and have the admin's deck put it in the show."""
        cam_id = getattr(cfg, "CAMERA_ID", "") or link.new_camera_id()
        if cam_id != getattr(cfg, "CAMERA_ID", ""):
            configfile.update(CAMERA_ID=cam_id)
            cfg.CAMERA_ID = cam_id
        webbrowser.open(link.vdo_push(cam_id))
        if self.backend is None:
            self.say("Opened your camera page. It's added to the show once your deck connects; click again then.")
            return
        self.call(lambda b: b.camera(cam_id), then=lambda msg: self.say(
            f"Opened your camera page: allow the camera and mic there. {msg}", seconds=10))

    # --- Screen map --------------------------------------------------------
    def scale(self):
        return self.map.winfo_width() / self.canvas[0]

    def fit_map(self, _event=None):
        height = round(self.map.winfo_width() * self.canvas[1] / self.canvas[0])
        if abs(int(self.map.cget("height")) - height) > 1:
            self.map.config(height=height)
        self.draw_map()

    def movable(self, name):
        return name.startswith("Cam - ") and (self.can_control() or name == self.me)

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
            if ADMIN and current and current != default and found.get("layout"):
                m.add_command(label=f"Make this the default for {found['layout']}", command=lambda: self.call(
                    lambda b: b.make_default(found["current"]),
                    then=lambda layout: self.say(f"Default background for {layout} saved")))
            if ADMIN:
                m.add_command(label="Add picture…", command=self.add_background)
            m.add_command(label=("✓  " if not current else "     ") + "Plain color",
                          command=lambda: self.set_background(""))
            if ADMIN:
                m.add_command(label="Open backgrounds folder", command=self.open_backgrounds)
            else:
                m.add_command(label="New pictures are added on the admin's deck", state="disabled")
            b = self.bg_button
            m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        self.call(lambda b: b.backgrounds(), then=show)

    def set_background(self, path):
        name = os.path.splitext(os.path.basename(path))[0] if path else "plain color"
        self.call(lambda b: b.set_background(path), then=lambda _: self.say(f"Background: {name}"))

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
        if not self.can_control():
            return
        self.call(lambda b: b.next_background(), quiet=True, then=lambda nxt: self.say(
            f"Background: {os.path.splitext(os.path.basename(nxt))[0]}" if nxt
            else "No saved backgrounds yet. Use Background ▾ → Add picture… on the admin's deck first."))

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
                if not ADMIN:
                    note.config(text="Pictures from your PC can only be added on the admin's deck. "
                                     "Paste a picture link instead.", fg=REC)
                    return
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
            self.pending_row.pack(fill="x", padx=12, pady=(6, 0), before=self.extras)
            self.say("Control the video in your browser. It switches when you click Use as background or Switch.", 10)

    def hide_pending(self):
        self.pending_row.pack_forget()

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
        return self.backend.live(channel) if ADMIN and isinstance(self.backend, control.Local) else None

    def page_colors(self):
        """The color scheme, as CSS variables, for the browser control pages."""
        return theme.css()

    def idle_state(self):
        """What the empty Video + Cams box shows (admin only): {"text", "picture"}."""
        if not (ADMIN and isinstance(self.backend, control.Local)):
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
        if ADMIN and isinstance(self.backend, control.Local):
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
            self.set_pill(self.obs_pill, BAD, "OBS OFFLINE" if ADMIN else "ADMIN OFFLINE")
            self.rec_pill["frame"].pack_forget()
            return
        self.last_state = state
        self.set_pill(self.obs_pill, OK, "OBS" if ADMIN else "ADMIN")
        if not ADMIN:
            you = state.get("you")
            self.me = f"Cam - {you}" if you else None
            if self.selected is None:
                self.selected = self.me
            mine = getattr(cfg, "DISPLAY_NAME", "")
            if you and mine and not self.sent_name:    # tell the admin's deck our name once per session
                self.sent_name = True
                self.call(lambda b: b.set_display_name(mine))
        self.names = state.get("names") or {}
        if not ADMIN:
            you = state.get("you")
            self.root.title(f"Deck · {self.names.get(you) or you}" if you else "Deck · guest")
        if state.get("note"):
            self.say(state["note"], seconds=10)
        now = state.get("now") or {}
        if now != self.now:
            self.now = now
            short = lambda t, n: t if len(t) <= n else t[:n - 1] + "…"
            text = "Now: " + short(now.get("background") or "plain color", 22)
            if now.get("video"):
                text += "  ·  ▶ " + short(now["video"], 20)
            self.now_label.config(text=text)
        self.canvas = tuple(state["canvas"])
        full = state["full"]
        self.full = full
        if not ADMIN and full != self.built_full:
            self.guest_controls(full)
        meta = state.get("meta") or self.meta
        if (state["scenes"] != self.scenes or meta != self.meta or not self.buttons
                or (not ADMIN and full != self.built_full)):
            self.meta = meta
            if self.tab not in meta["tabs"]:
                self.tab = positions.GENERAL
            self.current = state["current"]
            self.rebuild(state["scenes"])
        self.built_full = full
        self.current, self.recording = state["current"], state["recording"]
        if not self.drag and time.monotonic() >= self.hold_until:  # don't snap a camera back mid-move
            self.items = state["items"]
            self.draw_map()
        rec_txt = "Recording" if self.recording else "Not recording"
        if self.recording and self.can_control():
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
        self.rec.config(text="■  Stop recording" if self.recording else "●  Record",
                        bg=REC if self.recording else KEY, fg="#FFFFFF" if self.recording else INK,
                        activebackground=REC if self.recording else KEY_HOVER)

    def guest_controls(self, full):
        """Guest deck: show or hide the admin's controls when full control is turned on or off."""
        if full:
            self.controls.pack(fill="x", after=self.reset_button.master)
            self.root.geometry(f"{self.root.winfo_width()}x880")
            self.reset_button.config(text="Reset camera")
            if self.built_full is not None:
                self.say("The admin gave you full control")
        else:
            self.controls.pack_forget()
            self.root.geometry(f"{self.root.winfo_width()}x600")
            self.reset_button.config(text="Reset my camera")
            self.selected = self.me
            if self.built_full:
                self.say("Full control turned off: you can move your own camera")
        self.set_control_hotkeys(full)

    def rebuild(self, scenes):
        """The tab strip, then one row per layout in the current tab: a color marker, its name, a ⋯ menu
        (admin), and its hotkey. The live one is lit. Hotkeys follow OBS's order, whatever tab is showing."""
        self.scenes = scenes
        self.draw_tabs()
        for w in self.grid.winfo_children():
            w.destroy()
        for hk in self.hotkeys:
            keyboard.remove_hotkey(hk)
        self.hotkeys, self.buttons = [], {}
        live = self.can_control()
        for i, name in enumerate(scenes, start=1):
            if i <= 9 and live:
                self.hotkeys.append(keyboard.add_hotkey(
                    f"{cfg.HOTKEY_PREFIX}{i}", lambda n=name: self.root.after(0, self.switch, n)))
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
            hint = tk.Label(row, text=f"{cfg.HOTKEY_PREFIX}{i}" if i <= 9 and live else "", bg=NAV, fg=MUTED,
                            font=HINT_FONT)
            hint.pack(side="right", padx=(4, 10))
            dots = tk.Label(row, text="⋯", bg=NAV, fg=NAV, font=FONT, cursor="hand2") if ADMIN else None
            if dots:
                dots.pack(side="right")
                dots.bind("<Button-1>", lambda e, n=name: self.layout_menu(n, e) or "break")
            self.buttons[name] = {"row": row, "bar": bar, "label": label, "hint": hint, "dots": dots, "live": live}
            for w in (row, label, hint, chip) + ((dots,) if dots else ()):
                if live and w is not dots:
                    w.bind("<Button-1>", lambda _e, n=name: self.switch(n))
                w.bind("<Enter>", lambda _e, n=name: self.paint_row(n, hover=True))
                w.bind("<Leave>", lambda _e, n=name: self.paint_row(n))
                if ADMIN:
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

    def draw_tabs(self):
        """General, your own tabs, and ＋ (admin) to make another. Right-click a tab to rename or delete it."""
        for w in self.tabs_bar.winfo_children():
            w.destroy()
        tabs = self.meta["tabs"]
        if len(tabs) == 1 and not ADMIN:
            return                             # just General: no strip needed
        for tab in tabs:
            on = tab == self.tab
            t = tk.Label(self.tabs_bar, text=tab, bg=LIT if on else NAV, fg=LIT_INK if on else INK_DIM,
                         font=STATUS_FONT + ("bold",), padx=10, pady=3, cursor="hand2")
            t.pack(side="left", padx=(0, 4))
            t.bind("<Button-1>", lambda _e, tb=tab: self.show_tab(tb))
            if ADMIN and tab != positions.GENERAL:
                t.bind("<Button-3>", lambda e, tb=tab: self.tab_menu(tb, e))
        if ADMIN:
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
                lambda new: self.call(lambda b: b.rename_layout(name, new), then=lambda made: self.say(f"Renamed to {made}"))))
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
        for w in (r["row"], r["label"], r["hint"]):
            w.config(bg=bg)
        r["bar"].config(bg=LIT if lit else bg)
        r["label"].config(fg=INK if (lit or r["live"]) else INK_DIM)
        r["hint"].config(fg=LIT if lit else MUTED)
        if r["dots"]:                          # the ⋯ menu button shows on hover
            r["dots"].config(bg=bg, fg=INK_DIM if hover else bg)


def welcome(root):
    """First launch: one question, then config.py is written and the deck opens."""
    root.title("Podcast Deck")
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.geometry("420x380")
    frame = tk.Frame(root, bg=BG, padx=20, pady=18)
    frame.pack(fill="both", expand=True)
    key = lambda parent, text, cmd: Deck.key(None, parent, text, cmd)   # the deck's button style, no deck yet

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

    def done(**values):
        if configfile.load() is None:
            configfile.create(**values)
        else:
            configfile.update(**values)
        use_config(configfile.load())
        root.unbind("<Return>")
        frame.destroy()
        deck = Deck(root)
        root.protocol("WM_DELETE_WINDOW", deck.closing)

    def recording():
        clear()
        label("Who's on the show?", FONT, INK)
        label("One name per camera, left to right, separated by commas. People sharing a camera share a name.")
        names = entry("Host 1, Host 2, Host 3")
        problem = tk.Label(frame, text="", bg=BG, fg=REC, font=STATUS_FONT, anchor="w")
        problem.pack(fill="x")

        def go(_e=None):
            cams = [n.strip() for n in names.get().split(",") if n.strip()]
            if not cams:
                problem.config(text="Add at least one name.")
                return
            done(ADMIN=True, CAMS=cams)
        key(frame, "Start", go).pack(anchor="e", pady=(8, 0))
        root.bind("<Return>", go)

    def joining():
        clear()
        label("Paste your invite", FONT, INK)
        label("The admin sends you an invite that starts with podcast-deck://. Copy all of it and paste it here.")
        try:
            clip = root.clipboard_get().strip()
        except tk.TclError:
            clip = ""
        invite = entry(clip if clip.startswith(link.PREFIX) else "")
        label("Your name, shown on your camera (you can change it later in Settings):")
        shown = entry(os.environ.get("USERNAME", ""))
        invite.focus_set()
        problem = tk.Label(frame, text="", bg=BG, fg=REC, font=STATUS_FONT, anchor="w", wraplength=370,
                           justify="left")
        problem.pack(fill="x")

        def go(_e=None):
            text = invite.get().strip()
            if not text.startswith(link.PREFIX):
                problem.config(text="That doesn't look like an invite. It starts with podcast-deck://")
                return
            done(ADMIN=False, INVITE=text, DISPLAY_NAME=positions.clean_display_name(shown.get()))
        key(frame, "Join", go).pack(anchor="e", pady=(8, 0))
        root.bind("<Return>", go)

    if cfg is not None and not ADMIN:           # a guest whose invite is missing
        joining()
        return
    label("Podcast Deck", FONT, INK)
    label("Is this the PC that runs OBS and records, or are you joining someone else's recording?")
    big = dict(fill="x", ipady=10, pady=4)
    key(frame, "I'm recording (this PC runs OBS)", recording).pack(**big)
    key(frame, "I'm joining from somewhere else", joining).pack(**big)


if __name__ == "__main__":
    root = tk.Tk()
    if cfg is None or (not ADMIN and not getattr(cfg, "INVITE", "")):
        welcome(root)
    else:
        deck = Deck(root)
        root.protocol("WM_DELETE_WINDOW", deck.closing)
    root.mainloop()
