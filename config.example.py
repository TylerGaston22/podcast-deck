"""The deck's settings. The deck writes this file itself on first launch; edit it for anything else."""

# The deck only ever controls the OBS on its own PC. Leave OBS_PASSWORD empty: the
# deck reads OBS's password from OBS's own settings, so nobody has to copy it.
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = ""

# Layouts follow OBS's own canvas (Settings → Video → Base Resolution), 1080p or 4K alike.
# The sizes below (cams, margins, the video box) are for 1920x1080 and scale with it.
CANVAS_W, CANVAS_H = 1920, 1080

# Who's on your show, in the order their cams appear left → right. Each becomes a "Cam - <name>"
# source. People on this PC use a webcam (picked automatically, or in the deck's Settings); people
# sharing one camera in the same room share one name, e.g. "Couch". People in the group (below) show up
# through VDO.Ninja instead.
CAMS = ["Host 1", "Host 2", "Host 3"]

# This PC. The first-launch window fills these in.
# RECORD = True: this PC has OBS; you run your own show and record or stream it.
# RECORD = False: camera only; you just send your camera to the group. No OBS needed.
RECORD = True
ME = ""            # your name in the group (and your cam's name)

# The group: everyone sending their camera to each other. Each person runs their own show (or just sends
# a camera); nobody controls anyone else's OBS. Invite / Join in the deck makes and shares these.
GROUP = ""         # the group's code, from its link. Anyone with it can see the group's cameras
GROUP_PEOPLE = []  # everyone in the group, by name

# Only for adding a VDO.Ninja camera by hand: "Host 2": "https://vdo.ninja/?view=<their id>"
REMOTE_CAMS = {}

THEME = "Stream Launcher"   # the deck's colors; pick in Settings → Look

# Discord StreamKit "Voice Widget" URL — shows everyone's Discord icon and lights
# it up when they talk. Get it at https://streamkit.discord.com/overlay (pick your
# server + voice channel). Leave empty to skip that layer.
DISCORD_STREAMKIT_URL = ""

# Small-cam size for the "gameplay with us in the corner" layouts.
SMALL_CAM_W, SMALL_CAM_H = 320, 180
MARGIN = 24

# Video + Cams layout: the box the video plays in (left edge, top edge, width, height).
# The cams stack in a column on whichever side has more room, so leave space beside it.
# The default puts the video on the right and the cams down the left.
VIDEO_X, VIDEO_Y = 432, 135
VIDEO_W, VIDEO_H = 1440, 810

# Global hotkeys for deck.py — work even while a game is full screen.
# Layout N (in the deck's order) = HOTKEY_PREFIX + N, e.g. ctrl+alt+1 ... ctrl+alt+9.
HOTKEY_PREFIX = "ctrl+alt+"
RECORD_HOTKEY = "ctrl+alt+r"
BACKGROUND_HOTKEY = "ctrl+alt+b"   # next picture in the backgrounds folder
# Your own hotkey for a layout, by name ("" for none). Easiest to set in the deck: Settings → Hotkeys.
LAYOUT_HOTKEYS = {}

# Optional: side buttons on the mouse. "x" = back button, "x2" = forward button,
# "middle" = scroll-wheel click. Map each to a scene name, or "record" to toggle
# recording, "next" to cycle through the layouts, or "next background" to cycle
# through the background pictures. Leave empty to ignore the mouse.
MOUSE_BUTTONS = {
    "x": "next",
    "x2": "record",
}
