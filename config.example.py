"""Edit this file, then run build_scenes.py once. Everything else reads from here."""

# OBS → Tools → WebSocket Server Settings. Enable server, copy the password here.
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = "CHANGE_ME"

# Output canvas (match Settings → Video → Base Resolution).
CANVAS_W, CANVAS_H = 1920, 1080

# One cam per person, in the order they appear left → right.
# Each becomes a "Cam - <name>" source. Pick the actual device in OBS afterwards
# (double-click the source). People sharing one camera in the same room share
# one name here, e.g. "Couch".
CAMS = ["Host 1", "Host 2", "Host 3"]

# People joining online: their VDO.Ninja view link, by cam name. They open
# https://vdo.ninja/?push=<their id> in their browser; this shows that camera.
# Only needed on the PC that runs OBS. Run build_scenes.py again after changing it.
REMOTE_CAMS = {
    # "Host 2": "https://vdo.ninja/?view=<their id>",
}

# Who is using this deck. On the PC that runs OBS and records, keep ADMIN = True;
# ME is optional there (your cam name, so the screen map selects it first).
# On a guest's PC, set ADMIN = False and paste the invite the admin sent you into
# INVITE. Guests don't need OBS or its password. See "Hosts joining online" in the README.
ADMIN = True
ME = ""
INVITE = ""
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
