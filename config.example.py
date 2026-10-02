"""Edit this file, then run build_scenes.py once. Everything else reads from here."""

# OBS → Tools → WebSocket Server Settings. Enable server, copy the password here.
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = "CHANGE_ME"

# Output canvas (match Settings → Video → Base Resolution).
CANVAS_W, CANVAS_H = 1920, 1080

# One cam per person, in the order they appear left → right.
# Each becomes a "Cam - <name>" source. Pick the actual device in OBS afterwards
# (double-click the source). If someone's video comes through a Discord call
# instead of a local webcam, swap that source for a Window Capture of Discord.
CAMS = ["Host 1", "Host 2", "Host 3"]

# Discord StreamKit "Voice Widget" URL — shows everyone's Discord icon and lights
# it up when they talk. Get it at https://streamkit.discord.com/overlay (pick your
# server + voice channel). Leave empty to skip that layer.
DISCORD_STREAMKIT_URL = ""

# Small-cam size for the "gameplay with us in the corner" layouts.
SMALL_CAM_W, SMALL_CAM_H = 320, 180
MARGIN = 24

# Global hotkeys for deck.py — work even while a game is full screen.
# Scene N (in OBS order) = HOTKEY_PREFIX + N, e.g. ctrl+alt+1 ... ctrl+alt+9.
HOTKEY_PREFIX = "ctrl+alt+"
RECORD_HOTKEY = "ctrl+alt+r"

# Optional: side buttons on the mouse. "x" = back button, "x2" = forward button,
# "middle" = scroll-wheel click. Map each to a scene name, or "record" to toggle
# recording, or "next" to cycle through the layouts. Leave empty to ignore the mouse.
MOUSE_BUTTONS = {
    "x": "next",
    "x2": "record",
}
