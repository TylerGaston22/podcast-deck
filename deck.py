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
from theme import BG, KEY, KEY_HOVER, INK, INK_DIM, LIT, LIT_INK, REC, FONT, STATUS_FONT

HANDLE = 10                                    # px: grab this close to a box's corner to resize it
NOTES = os.path.join(media.APP_DIR, "NOTES.md")
cfg, ADMIN, DECK_PORT, BACKGROUND_HOTKEY = None, True, 4460, "ctrl+alt+b"


def use_config(found):
    global cfg, ADMIN, DECK_PORT, BACKGROUND_HOTKEY
    cfg = found
    ADMIN = getattr(cfg, "ADMIN", True)        # older config.py files are the single-PC setup
    DECK_PORT = getattr(cfg, "DECK_PORT", 4460)
    BACKGROUND_HOTKEY = getattr(cfg, "BACKGROUND_HOTKEY", "ctrl+alt+b")


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
        self.hold_until = 0.0                  # keep the map as dragged until OBS has caught up
        self.now = {}                          # what's showing: background and video titles
        self.bg_preview, self.bg_mine = None, False   # the pasted background video, and whether it's live
        self.bg = bgcontrol.BgControl(self, ADMIN)    # this PC only: the browser control page, and OBS's feed

        root.title("Deck" if ADMIN else "Deck · guest")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.geometry("300x800" if ADMIN else "300x560")
        root.minsize(220, 300)

        self.status = tk.Label(root, text="Connecting…", bg=BG, fg=INK_DIM, font=STATUS_FONT,
                               anchor="w", justify="left", wraplength=280)
        self.status.pack(fill="x", padx=12, pady=(12, 6))
        self.grid = tk.Frame(root, bg=BG)
        # Everything under the layout buttons sits at the bottom and always stays visible; the layout
        # buttons get whatever room is left.
        bottom = tk.Frame(root, bg=BG)
        bottom.pack(side="bottom", fill="x")
        self.grid.pack(fill="both", expand=True, padx=12)

        # Screen map: drag a camera to move it, drag its corner to resize it.
        self.map = tk.Canvas(bottom, bg=BG, highlightthickness=0, height=150, cursor="hand2")
        self.map.pack(fill="x", padx=12, pady=(12, 0))
        self.map.bind("<Configure>", self.fit_map)
        self.map.bind("<ButtonPress-1>", self.map_press)
        self.map.bind("<B1-Motion>", self.map_drag)
        self.map.bind("<ButtonRelease-1>", self.map_release)
        under = tk.Frame(bottom, bg=BG)
        under.pack(fill="x", padx=12, pady=(6, 0))
        self.reset_button = self.small_key(under, "Reset camera" if ADMIN else "Reset my camera", self.reset_camera)
        self.reset_button.pack(side="left")
        self.small_key(under, "Settings…", self.settings_box).pack(side="right")
        if not ADMIN:
            start = self.small_key(under, "Start my camera", self.start_camera)
            start.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
            start.pack(side="right", padx=4)
        if ADMIN:
            self.full_var = tk.BooleanVar(value=False)
            tk.Checkbutton(bottom, text="Guests get full control", variable=self.full_var, anchor="w",
                           command=self.set_full, bg=BG, fg=INK_DIM, selectcolor=KEY, activebackground=BG,
                           activeforeground=INK, font=STATUS_FONT).pack(fill="x", padx=8, pady=(6, 0))

        # Record, Background, and Play link: always on the admin deck, on guests' only with full control.
        self.controls = tk.Frame(bottom, bg=BG)
        self.controls.pack(fill="x")
        self.now_label = tk.Label(self.controls, text="", bg=BG, fg=INK_DIM, font=STATUS_FONT, anchor="w")
        self.now_label.pack(fill="x", padx=12, pady=(10, 0))
        # A pasted background video waits here until someone switches to it.
        self.pending_row = tk.Frame(self.controls, bg=BG)
        tk.Label(self.pending_row, text="Video ready in your browser", bg=BG, fg=LIT,
                 font=STATUS_FONT, anchor="w").pack(side="left")
        self.small_key(self.pending_row, "✕", self.hide_pending).pack(side="right")
        switch = self.small_key(self.pending_row, "Switch", self.switch_background)
        switch.config(bg=LIT, fg=LIT_INK, activebackground=LIT, activeforeground=LIT_INK)
        switch.pack(side="right", padx=4)
        extras = tk.Frame(self.controls, bg=BG)
        extras.pack(fill="x", padx=12, pady=(6, 0))
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
        self.rec = self.key(self.controls, "Record", self.toggle_record)
        self.rec.pack(fill="x", padx=12, pady=12, ipady=8)
        tk.Frame(bottom, bg=BG, height=12).pack()
        if not ADMIN:
            self.controls.pack_forget()
        self.set_control_hotkeys(ADMIN)

        if cfg.MOUSE_BUTTONS:
            mouse.hook(self.on_mouse)
        if self.setup_problem:
            self.status.config(text=self.setup_problem)
        else:
            self.poll()

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

    def set_full(self):
        full = self.full_var.get()
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
    def settings_box(self):
        """Admin: cameras, browser window, rebuild, guests. Guest: change invite. Both: how it works."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=14)
        win.title("Settings")
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        win.bind("<Escape>", lambda _e: win.destroy())

        def heading(text):
            tk.Label(win, text=text, bg=BG, fg=INK, font=FONT, anchor="w").pack(fill="x", pady=(10, 4))

        def note(text, color=INK_DIM):
            tk.Label(win, text=text, bg=BG, fg=color, font=STATUS_FONT, anchor="w", justify="left",
                     wraplength=420).pack(fill="x")

        if ADMIN:
            heading("Cameras")
            cams = tk.Frame(win, bg=BG)
            cams.pack(fill="x")
            self.call(lambda b: b.devices(), then=lambda found: self.fill_devices(cams, found))

            heading("Layouts")
            note("Rebuild after changing config.py. Cameras you've moved stay where they are.")
            self.small_key(win, "Rebuild layouts", lambda: self.call(
                lambda b: b.rebuild(), then=lambda _: self.say("Layouts rebuilt"))).pack(anchor="w", pady=(4, 0))

            heading("Guests")
            on = self.link and self.link.httpd
            note(f"Guests connect over Tailscale ({self.link.ip}). Send each person their own invite, privately."
                 if on else "Tailscale isn't running on this PC, so guests can't connect yet. Start Tailscale; "
                            "the deck notices within ten seconds.", INK_DIM if on else REC)
            rows = tk.Frame(win, bg=BG)
            rows.pack(fill="x", pady=(4, 0))
            self.fill_guests(rows, on)
        else:
            heading("Invite")
            note("Copy the new invite the admin sent you, then click Paste invite.")
            self.small_key(win, "Paste invite", lambda: self.paste_invite(win)).pack(anchor="w", pady=(4, 0))

        heading("Help")
        self.small_key(win, "How it works", lambda: subprocess.Popen(["notepad.exe", NOTES])).pack(anchor="w")
        self.key(win, "Close", win.destroy).pack(anchor="e", pady=(14, 0))

    def fill_devices(self, frame, found):
        """Settings: one dropdown per webcam camera, plus the browser window for Browser + Cams."""
        def row(r, label, choices, current, on_pick):
            tk.Label(frame, text=label, bg=BG, fg=INK, font=STATUS_FONT, anchor="w").grid(row=r, column=0, sticky="w")
            names = [n for n, _ in choices]
            box = ttk.Combobox(frame, values=names, state="readonly", width=34)
            box.set(next((n for n, v in choices if v == current), "Pick one…"))
            box.bind("<<ComboboxSelected>>", lambda _e: on_pick(choices[box.current()][1]))
            box.grid(row=r, column=1, padx=8, pady=2, sticky="w")

        r = 0
        for name, cam in found["cams"].items():
            if cam["online"]:
                tk.Label(frame, text=name, bg=BG, fg=INK, font=STATUS_FONT).grid(row=r, column=0, sticky="w")
                tk.Label(frame, text="joins online (VDO.Ninja)", bg=BG, fg=INK_DIM, font=STATUS_FONT).grid(
                    row=r, column=1, padx=8, sticky="w")
            else:
                row(r, name, cam["choices"], cam["current"],
                    lambda v, n=name: self.call(lambda b: b.set_webcam(n, v), then=lambda _: self.say("Webcam set")))
            r += 1
        row(r, "Browser window", found["windows"], found["window"],
            lambda v: self.call(lambda b: b.set_window(v), then=lambda _: self.say("Browser window set")))

    def fill_guests(self, rows, on):
        for w in rows.winfo_children():
            w.destroy()
        invites = link.load_invites()
        for r, name in enumerate(n for n in cfg.CAMS if f"Cam - {n}" != self.me):
            tk.Label(rows, text=name, bg=BG, fg=INK, font=STATUS_FONT, anchor="w").grid(row=r, column=0, sticky="w")
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
            c.create_text(x + w / 2, y + h / 2, text=name.removeprefix("Cam - "), width=max(w - 4, 10),
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
        if d["resize"]:
            box = positions.clamp_resize(d["box"], dx, self.canvas, min_w=self.canvas[0] * 0.08)
        else:
            box = positions.clamp_move(d["box"], dx, dy, self.canvas)
        d["item"]["box"] = box
        self.draw_map()
        self.push(d["scene"], d["item"]["name"], box)

    def map_release(self, _e):
        d, self.drag = self.drag, None
        if not d or d["item"]["box"] == d["box"]:
            return
        name, scene, box = d["item"]["name"], d["scene"], d["item"]["box"]
        self.push(scene, name, box, save=True)
        self.say(f"{'Your camera' if name == self.me else name.removeprefix('Cam - ')} moved in {scene}")

    def push(self, scene, cam, box, save=False):
        """Send a camera's new spot, dropping in-between spots if the other end is slower than the mouse."""
        self.pending = lambda: self.backend.move(scene, cam, box, save=save)
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
            "Camera back to its usual spot" if ok
            else "This layout has no usual spot for that camera. Run build_scenes.py to set one."))

    # --- Background --------------------------------------------------------
    def background_menu(self):
        """Pop up the saved pictures, plus Add picture…, Plain color, and Open folder."""
        def show(found):
            current, pics = found
            current = os.path.normcase(current or "")
            m = tk.Menu(self.root, tearoff=0, bg=KEY, fg=INK, activebackground=LIT, activeforeground=LIT_INK,
                        font=STATUS_FONT, bd=0)
            for pic in pics:
                tick = "✓  " if os.path.normcase(pic) == current else "     "
                m.add_command(label=tick + os.path.basename(pic), command=lambda p=pic: self.set_background(p))
            if m.index("end") is not None:
                m.add_separator()
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

    def open_bg_preview(self, source):
        """Open the browser control page for a pasted background video."""
        if not self.bg.httpd:
            self.tell("The deck couldn't start its background video page. Close other decks on this PC and "
                      "reopen this one.")
            return
        self.bg.pending, self.bg_preview, self.bg_mine = source, None, False
        webbrowser.open(self.bg.page_url())
        self.pending_row.pack(fill="x", padx=12, pady=(6, 0), before=self.extras)
        self.say("Control the video in your browser. It switches when you click Use as background or Switch.", 10)

    def hide_pending(self):
        self.pending_row.pack_forget()

    def switch_background(self):
        """The deck's Switch button: put the previewed video in the background, from where the preview is."""
        src = self.bg.pending
        if not src:
            return
        state = self.bg_preview or {"kind": src["kind"], "id": src.get("id"), "url": src.get("url"),
                                    "title": src.get("title", ""), "time": src.get("start", 0)}
        state = dict(state, seek=(state.get("seek") or 0) + 1)
        self.call(lambda b: b.set_bg_video(state), then=lambda _: self.went_live())

    def went_live(self):
        self.bg_mine = True
        self.hide_pending()
        self.say("Background video is live. Your browser tab controls it.", 8)

    # Called by the local server (bgcontrol.py), from its own thread.
    def live_state(self):
        return self.backend.live_bg() if ADMIN and isinstance(self.backend, control.Local) else None

    def control(self, state, action):
        if action == "preview":
            self.bg_preview = state
            return ""
        if self.backend is None:
            raise DeckError("The deck isn't connected yet.")
        if action == "go_live":
            self.backend.set_bg_video(state)
            self.root.after(0, self.went_live)
            return "Live"
        if action == "update":
            if self.bg_mine:
                self.backend.set_bg_video(state)
            return ""
        self.backend.set_bg_video(None)                     # stop
        self.bg_mine = False
        self.root.after(0, self.say, "Background video stopped")
        return "Stopped"

    # --- Video link --------------------------------------------------------
    def play_link(self):
        self.call(lambda b: b.video_settings(), then=self.link_box)

    def play_video(self, vid=None, start=0, title=None):
        """Play a video in the Video + Cams box, or stop it when vid is None."""
        self.call(lambda b: b.play_video(vid, start, title),
                  then=lambda _: self.say("Playing in Video + Cams" if vid else "Video stopped"))

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
            for b in self.buttons.values():
                b.config(bg=KEY, fg=INK)
            return
        if not ADMIN:
            you = state.get("you")
            self.me = f"Cam - {you}" if you else None
            self.root.title(f"Deck · {you}" if you else "Deck · guest")
            if self.selected is None:
                self.selected = self.me
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
        if ADMIN:
            self.full_var.set(full)
        elif full != self.built_full:
            self.guest_controls(full)
        if state["scenes"] != self.scenes or (not ADMIN and full != self.built_full):
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
        for name, b in self.buttons.items():
            lit = name == self.current
            b.config(bg=LIT if lit else KEY, fg=LIT_INK if lit else INK,
                     disabledforeground=LIT_INK if lit else INK_DIM)
        self.rec.config(text="Stop recording" if self.recording else "Record",
                        bg=REC if self.recording else KEY, fg="#FFFFFF" if self.recording else INK)

    def guest_controls(self, full):
        """Guest deck: show or hide the admin's controls when full control is turned on or off."""
        if full:
            self.controls.pack(fill="x", after=self.reset_button.master)
            self.root.geometry(f"{self.root.winfo_width()}x800")
            self.reset_button.config(text="Reset camera")
            if self.built_full is not None:
                self.say("The admin gave you full control")
        else:
            self.controls.pack_forget()
            self.root.geometry(f"{self.root.winfo_width()}x560")
            self.reset_button.config(text="Reset my camera")
            self.selected = self.me
            if self.built_full:
                self.say("Full control turned off: you can move your own camera")
        self.set_control_hotkeys(full)

    def rebuild(self, scenes):
        self.scenes = scenes
        for w in self.grid.winfo_children():
            w.destroy()
        for hk in self.hotkeys:
            keyboard.remove_hotkey(hk)
        self.hotkeys, self.buttons = [], {}
        live = self.can_control()
        for i, name in enumerate(scenes, start=1):
            label = f"{name}    {cfg.HOTKEY_PREFIX}{i}" if i <= 9 and live else name
            b = self.key(self.grid, label, lambda n=name: self.switch(n))
            b.config(state="normal" if live else "disabled", cursor="hand2" if live else "arrow")
            b.pack(fill="both", expand=True, pady=2, ipady=2)
            self.buttons[name] = b
            if i <= 9 and live:
                self.hotkeys.append(keyboard.add_hotkey(
                    f"{cfg.HOTKEY_PREFIX}{i}", lambda n=name: self.root.after(0, self.switch, n)))


def welcome(root):
    """First launch: one question, then config.py is written and the deck opens."""
    root.title("Podcast Deck")
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.geometry("420x330")
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
        Deck(root)

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
        problem = tk.Label(frame, text="", bg=BG, fg=REC, font=STATUS_FONT, anchor="w", wraplength=370,
                           justify="left")
        problem.pack(fill="x")

        def go(_e=None):
            text = invite.get().strip()
            if not text.startswith(link.PREFIX):
                problem.config(text="That doesn't look like an invite. It starts with podcast-deck://")
                return
            done(ADMIN=False, INVITE=text)
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
        Deck(root)
    root.mainloop()
