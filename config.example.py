"""The deck's settings. The deck writes this file itself on first launch; edit it for anything else."""

# The deck only ever controls the OBS on its own PC. Leave OBS_PASSWORD empty: the
# deck reads OBS's password from OBS's own settings, so nobody has to copy it.
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = ""

# Output canvas (match Settings → Video → Base Resolution).
CANVAS_W, CANVAS_H = 1920, 1080

# One cam per person, in the order they appear left → right.
# Each becomes a "Cam - <name>" source. Webcams are picked automatically, or in the
# deck's Settings. People sharing one camera in the same room share one name, e.g. "Couch".
CAMS = ["Host 1", "Host 2", "Host 3"]

# People joining online send their camera from their deck (Start my camera), and it's
# added by itself. Only for adding a VDO.Ninja camera by hand, on the PC that runs OBS:
REMOTE_CAMS = {
    # "Host 2": "https://vdo.ninja/?view=<their id>",
}

# Who is using this deck. The first-launch window fills these in.
# Admin (the PC that runs OBS and records): ADMIN = True. ME is optional (your cam
# name, so the screen map selects it first).
# Guest: ADMIN = False and INVITE = the invite the admin sent. Guests don't need OBS.
ADMIN = True
ME = ""
INVITE = ""
CAMERA_ID = ""     # guest: your private VDO.Ninja ID, made by Start my camera
DECK_PORT = 4460   # admin: where guests' decks connect, over Tailscale only

# Discord StreamKit "Voice Widget" URL — shows everyone's Discord icon and lights
# it up when they talk. Get it at https://streamkit.discord.com/overlay (pick your
# server + voice channel). Leave empty to skip that layer.
DISCORD_STREAMKIT_URL = ""

# Small-cam size for the "gameplay with us in the corner" layouts.
SMALL_CAM_W, SMALL_CAM_H = 320, 180
MARGIN = 24

# Video + Cams layout: the box the video plays in (left edge, top edge, width, height).
# The cams stack in a column on whichever side has more room, so leave space beside it.
VIDEO_X, VIDEO_Y = 48, 162
VIDEO_W, VIDEO_H = 1344, 756

# Global hotkeys for deck.py — work even while a game is full screen.
# Scene N (in OBS order) = HOTKEY_PREFIX + N, e.g. ctrl+alt+1 ... ctrl+alt+9.
HOTKEY_PREFIX = "ctrl+alt+"
RECORD_HOTKEY = "ctrl+alt+r"
BACKGROUND_HOTKEY = "ctrl+alt+b"   # next picture in the backgrounds folder

# Optional: side buttons on the mouse. "x" = back button, "x2" = forward button,
# "middle" = scroll-wheel click. Map each to a scene name, or "record" to toggle
# recording, "next" to cycle through the layouts, or "next background" to cycle
# through the background pictures. Leave empty to ignore the mouse.
MOUSE_BUTTONS = {
    "x": "next",
    "x2": "record",
}
