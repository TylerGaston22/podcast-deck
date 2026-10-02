"""Desktop stream deck for OBS.

A small always-on-top window with one button per layout and a Record button,
plus global hotkeys (ctrl+alt+1..9 for layouts, ctrl+alt+r for record) and
optional mouse side buttons, all of which work while a game has focus. Buttons are read live from OBS, so any scene you
add later shows up automatically.

    py C:\\podcast-deck\\deck.py
"""
import threading
import tkinter as tk

import keyboard
import mouse
import obsws_python as obs

from theme import BG, KEY, KEY_HOVER, INK, INK_DIM, LIT, LIT_INK, REC, FONT, STATUS_FONT

try:
    import config as cfg
except ModuleNotFoundError:
    import os, sys
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(f"No config.py yet. Copy {here}\\config.example.py to {here}\\config.py and fill in your OBS password.")

HIDDEN = {"_Sources (don't delete)"}


class Deck:
    def __init__(self, root):
        self.root = root
        self.cl = None
        self.lock = threading.Lock()
        self.scenes, self.current, self.recording = [], None, False
        self.buttons = {}
        self.hotkeys = []

        root.title("Deck")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.geometry("300x420")
        root.minsize(220, 200)

        self.status = tk.Label(root, text="Connecting to OBS…", bg=BG, fg=INK_DIM, font=STATUS_FONT,
                               anchor="w", justify="left", wraplength=280)
        self.status.pack(fill="x", padx=12, pady=(12, 6))
        self.grid = tk.Frame(root, bg=BG)
        self.grid.pack(fill="both", expand=True, padx=12)
        self.rec = self.key(root, "Record", self.toggle_record)
        self.rec.pack(fill="x", padx=12, pady=12, ipady=8)

        keyboard.add_hotkey(cfg.RECORD_HOTKEY, lambda: root.after(0, self.toggle_record))
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

    def call(self, fn):
        """Run an OBS request on a worker thread, then refresh the UI."""
        def work():
            with self.lock:
                try:
                    cl = self.connect()
                    fn(cl)
                    scenes = [s["sceneName"] for s in reversed(cl.get_scene_list().scenes)]
                    state = ([s for s in scenes if s not in HIDDEN],
                             cl.get_current_program_scene().current_program_scene_name,
                             cl.get_record_status().output_active, None)
                except Exception as e:  # noqa: BLE001
                    self.cl = None
                    state = ([], None, False, str(e))
            self.root.after(0, self.render, *state)
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        self.call(lambda cl: None)
        self.root.after(2000, self.poll)

    def switch(self, name):
        self.call(lambda cl: cl.set_current_program_scene(name))

    def toggle_record(self):
        self.call(lambda cl: cl.toggle_record())

    # --- UI ----------------------------------------------------------------
    def key(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, font=FONT, bg=KEY, fg=INK, activebackground=KEY_HOVER,
                      activeforeground=INK, relief="flat", bd=0, cursor="hand2", anchor="w", padx=14)
        return b

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
