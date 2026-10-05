"""Desktop stream deck for OBS.

A small always-on-top window with one button per layout and a Record button,
plus global hotkeys (ctrl+alt+1..9 for layouts, ctrl+alt+r for record) and
optional mouse side buttons, all of which work while a game has focus. Buttons are read live from OBS, so any scene you
add later shows up automatically. The Background menu and Play link box change the
background picture and the Video + Cams video without opening OBS.

    py C:\\Users\\<you>\\source\\repos\\podcast-deck\\deck.py
"""
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import keyboard
import mouse
import obsws_python as obs
from obsws_python.error import OBSSDKRequestError

import media
from theme import BG, KEY, KEY_HOVER, INK, INK_DIM, LIT, LIT_INK, REC, FONT, STATUS_FONT

try:
    import config as cfg
except ModuleNotFoundError:
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(f"No config.py yet. Copy {here}\\config.example.py to {here}\\config.py and fill in your OBS password.")

HIDDEN = {"_Sources (don't delete)"}
BACKGROUND_HOTKEY = getattr(cfg, "BACKGROUND_HOTKEY", "ctrl+alt+b")
NOT_BUILT = "OBS doesn't have the new sources yet. Run build_scenes.py again to add them."


class Deck:
    def __init__(self, root):
        self.root = root
        self.cl = None
        self.lock = threading.Lock()
        self.scenes, self.current, self.recording = [], None, False
        self.buttons = {}
        self.hotkeys = []
        self.notice, self.notice_until = "", 0.0

        root.title("Deck")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.geometry("300x500")
        root.minsize(220, 240)

        self.status = tk.Label(root, text="Connecting to OBS…", bg=BG, fg=INK_DIM, font=STATUS_FONT,
                               anchor="w", justify="left", wraplength=280)
        self.status.pack(fill="x", padx=12, pady=(12, 6))
        self.grid = tk.Frame(root, bg=BG)
        self.grid.pack(fill="both", expand=True, padx=12)
        extras = tk.Frame(root, bg=BG)
        extras.pack(fill="x", padx=12, pady=(12, 0))
        self.bg_button = self.key(extras, "Background ▾", self.background_menu)
        self.bg_button.pack(side="left", fill="x", expand=True, padx=(0, 3), ipady=6)
        self.key(extras, "Play link…", self.play_link).pack(side="left", fill="x", expand=True, padx=(3, 0), ipady=6)
        self.rec = self.key(root, "Record", self.toggle_record)
        self.rec.pack(fill="x", padx=12, pady=12, ipady=8)

        keyboard.add_hotkey(cfg.RECORD_HOTKEY, lambda: root.after(0, self.toggle_record))
        keyboard.add_hotkey(BACKGROUND_HOTKEY, lambda: root.after(0, self.next_background))
        if cfg.MOUSE_BUTTONS:
            mouse.hook(self.on_mouse)
        self.poll()

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
        i = self.scenes.index(self.current) if self.current in self.scenes else -1
        self.switch(self.scenes[(i + 1) % len(self.scenes)])

    # --- OBS ---------------------------------------------------------------
    def connect(self):
        if self.cl is None:
            self.cl = obs.ReqClient(host=cfg.OBS_HOST, port=cfg.OBS_PORT, password=cfg.OBS_PASSWORD, timeout=3)
        return self.cl

    def call(self, fn, then=None, quiet=False):
        """Run an OBS request on a worker thread, then refresh the UI.

        `then` gets fn's result on the UI thread. If OBS refuses the request, the reason is shown
        in a popup, or in the status line when `quiet` (hotkeys, so a game doesn't lose focus).
        """
        def work():
            result, problem = None, None
            with self.lock:
                try:
                    cl = self.connect()
                    try:
                        result = fn(cl)
                    except OBSSDKRequestError as e:
                        problem = NOT_BUILT if e.code == 600 else str(e)   # 600: no source by that name
                    scenes = [s["sceneName"] for s in reversed(cl.get_scene_list().scenes)]
                    state = ([s for s in scenes if s not in HIDDEN],
                             cl.get_current_program_scene().current_program_scene_name,
                             cl.get_record_status().output_active, None)
                except Exception as e:  # noqa: BLE001
                    self.cl = None
                    state = ([], None, False, str(e))
            self.root.after(0, self.render, *state)
            if problem:
                self.root.after(0, self.tell, problem, quiet)
            elif then and state[3] is None:
                self.root.after(0, then, result)
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        self.call(lambda cl: None)
        self.root.after(2000, self.poll)

    def switch(self, name):
        self.call(lambda cl: cl.set_current_program_scene(name))

    def toggle_record(self):
        self.call(lambda cl: cl.toggle_record())

    # --- Background --------------------------------------------------------
    def background_menu(self):
        """Pop up the saved pictures, plus Add picture…, Plain color, and Open folder."""
        def show(current):
            current = os.path.normcase(current or "")
            m = tk.Menu(self.root, tearoff=0, bg=KEY, fg=INK, activebackground=LIT, activeforeground=LIT_INK,
                        font=STATUS_FONT, bd=0)
            for pic in media.list_backgrounds():
                tick = "✓  " if os.path.normcase(pic) == current else "     "
                m.add_command(label=tick + os.path.basename(pic), command=lambda p=pic: self.set_background(p))
            if m.index("end") is not None:
                m.add_separator()
            m.add_command(label="Add picture…", command=self.add_background)
            m.add_command(label=("✓  " if not current else "     ") + "Plain color",
                          command=lambda: self.set_background(""))
            m.add_command(label="Open backgrounds folder", command=self.open_backgrounds)
            b = self.bg_button
            m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        self.call(lambda cl: cl.get_input_settings("Background").input_settings.get("file", ""), then=show)

    def set_background(self, path):
        name = os.path.splitext(os.path.basename(path))[0] if path else "plain color"
        self.call(lambda cl: cl.set_input_settings("Background", {"file": path}, True),
                  then=lambda _: self.say(f"Background: {name}"))

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
        def step(cl):
            nxt = media.next_background(cl.get_input_settings("Background").input_settings.get("file", ""))
            if nxt:
                cl.set_input_settings("Background", {"file": nxt}, True)
            return nxt
        self.call(step, quiet=True, then=lambda nxt: self.say(
            f"Background: {os.path.splitext(os.path.basename(nxt))[0]}" if nxt
            else "No saved backgrounds yet. Use Background ▾ → Add picture… first."))

    # --- Video link --------------------------------------------------------
    def play_link(self):
        self.call(lambda cl: cl.get_input_settings("Video Panel").input_settings, then=self.link_box)

    def link_box(self, settings):
        """The paste box: YouTube link in, video playing in Video + Cams out."""
        folder = os.path.dirname(settings.get("local_file") or "") or media.APP_DIR
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
                       command=lambda: self.call(lambda cl: cl.set_input_settings(
                           "Video Panel", {"shutdown": restart.get()}, True))).pack(fill="x", pady=(6, 0))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", pady=(12, 0))

        # A copied YouTube link is the usual case, so start with it already pasted.
        try:
            clip = self.root.clipboard_get()
            if media.parse_youtube(clip):
                entry.insert(0, clip.strip())
        except tk.TclError:
            pass

        def load(vid=None, start=0):
            try:
                media.write_now_playing(folder, vid, start)
            except OSError as e:
                note.config(text=f"Couldn't update the video box. ({e})", fg=REC)
                return
            self.call(lambda cl: cl.press_input_properties_button("Video Panel", "refreshnocache"),
                      then=lambda _: self.say("Playing in Video + Cams" if vid else "Video stopped"))
            win.destroy()

        def play(_event=None):
            found = media.parse_youtube(entry.get())
            if not found:
                note.config(text="That doesn't look like a YouTube link.", fg=REC)
                return
            note.config(text="Checking the video…", fg=INK_DIM)
            def check():
                problem = media.embed_problem(found[0])
                def done():
                    if not win.winfo_exists():
                        return
                    if problem:
                        note.config(text=problem, fg=REC)
                    else:
                        load(*found)
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

    def say(self, text, seconds=4):
        """Show a short message in the status line, without stealing focus."""
        self.notice, self.notice_until = text, time.monotonic() + seconds
        self.status.config(text=text)

    def tell(self, text, quiet=False):
        if quiet:
            self.say(text, seconds=8)
        else:
            messagebox.showwarning("Podcast Deck", text, parent=self.root)

    def render(self, scenes, current, recording, error):
        if error:
            self.status.config(text="OBS not reachable. Open OBS and enable the WebSocket server; "
                                    "this window reconnects on its own.")
            for b in self.buttons.values():
                b.config(bg=KEY, fg=INK)
            return
        if scenes != self.scenes:
            self.rebuild(scenes)
        self.current, self.recording = current, recording
        rec_txt = f"Recording ({cfg.RECORD_HOTKEY})" if recording else "Not recording"
        if time.monotonic() >= self.notice_until:
            self.status.config(text=f"{current}  ·  {rec_txt}")
        for name, b in self.buttons.items():
            lit = name == current
            b.config(bg=LIT if lit else KEY, fg=LIT_INK if lit else INK)
        self.rec.config(text="Stop recording" if recording else "Record",
                        bg=REC if recording else KEY, fg="#FFFFFF" if recording else INK)

    def rebuild(self, scenes):
        self.scenes = scenes
        for w in self.grid.winfo_children():
            w.destroy()
        for hk in self.hotkeys:
            keyboard.remove_hotkey(hk)
        self.hotkeys, self.buttons = [], {}
        for i, name in enumerate(scenes, start=1):
            label = f"{name}    {cfg.HOTKEY_PREFIX}{i}" if i <= 9 else name
            b = self.key(self.grid, label, lambda n=name: self.switch(n))
            b.pack(fill="both", expand=True, pady=3, ipady=6)
            self.buttons[name] = b
            if i <= 9:
                self.hotkeys.append(keyboard.add_hotkey(
                    f"{cfg.HOTKEY_PREFIX}{i}", lambda n=name: self.root.after(0, self.switch, n)))


if __name__ == "__main__":
    root = tk.Tk()
    Deck(root)
    root.mainloop()
