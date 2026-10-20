"""Colors and fonts for the deck window and its browser pages. Four color schemes; Settings → Look picks one.

"Stream Launcher" is the stream launcher project's own palette (src/renderer/src/styles.css). Every scheme
has the same tokens, so the deck just asks for BG, LIT, OK, and so on.
"""
SCHEMES = {
    "Stream Launcher": {                      # the launcher's grays and blue, on a blacker background
        "BG": "#050608", "PANEL": "#08090C", "NAV": "#13171D", "KEY": "#1B212A", "KEY_HOVER": "#232A35",
        "LINE": "#1D232C", "INK": "#E6EBF1", "INK_DIM": "#A4AFBE", "MUTED": "#6C7888",
        "LIT": "#7CC4FF", "LIT_INK": "#06121E", "REC": "#FF3D4F",
        "OK": "#46D39A", "WARN": "#F2C14E", "BAD": "#FF8B3D",
    },
    "Electric blue": {
        "BG": "#070B1A", "PANEL": "#0B1126", "NAV": "#101934", "KEY": "#16224A", "KEY_HOVER": "#203066",
        "LINE": "#1E2A52", "INK": "#F5F8FF", "INK_DIM": "#9FB3E0", "MUTED": "#6D7FAA",
        "LIT": "#2F8CFF", "LIT_INK": "#FFFFFF", "REC": "#FF2E4D",
        "OK": "#3EE0A0", "WARN": "#FFD04A", "BAD": "#FF8A3D",
    },
    "Violet": {
        "BG": "#0C0818", "PANEL": "#120C24", "NAV": "#1A1233", "KEY": "#241A45", "KEY_HOVER": "#33255F",
        "LINE": "#2C2152", "INK": "#F7F4FF", "INK_DIM": "#B3A6DA", "MUTED": "#7D70A8",
        "LIT": "#8B5CFF", "LIT_INK": "#FFFFFF", "REC": "#FF2E63",
        "OK": "#4BE0A8", "WARN": "#FFCF5C", "BAD": "#FF8F4D",
    },
    "Teal + orange": {
        "BG": "#0A1214", "PANEL": "#0D181B", "NAV": "#112024", "KEY": "#14282C", "KEY_HOVER": "#1C3A40",
        "LINE": "#1C3236", "INK": "#F2FBFA", "INK_DIM": "#93BDB8", "MUTED": "#5F8783",
        "LIT": "#18D2B5", "LIT_INK": "#04201C", "REC": "#FF6A2E",
        "OK": "#5EE08A", "WARN": "#FFD25E", "BAD": "#FF8F5C",
    },
}
DEFAULT = "Stream Launcher"

# Layout rows are color-coded by what they show, like the stream launcher's status colors.
CATEGORY_COLORS = {"game": "#4DA3FF", "talk": "OK", "video": "#D06BFF", "break": "WARN", "other": "MUTED"}

FONT = ("Segoe UI", 12, "bold")
ROW_FONT = ("Segoe UI", 11, "bold")            # layout rows
STATUS_FONT = ("Segoe UI", 10)
LABEL_FONT = ("Segoe UI", 8, "bold")           # small uppercase section labels
BRAND_FONT = ("Segoe UI", 10, "bold")
HINT_FONT = ("Consolas", 9)                    # hotkey hints

name = DEFAULT
BG = PANEL = NAV = KEY = KEY_HOVER = LINE = INK = INK_DIM = MUTED = LIT = LIT_INK = REC = OK = WARN = BAD = ""


def use(scheme):
    """Switch to a color scheme by name (unknown names fall back to the default)."""
    global name
    name = scheme if scheme in SCHEMES else DEFAULT
    globals().update(SCHEMES[name])


def tokens():
    return {k: v for k, v in globals().items() if k in SCHEMES[DEFAULT]} | {"FONT": FONT, "STATUS_FONT": STATUS_FONT}


def category_color(kind):
    value = CATEGORY_COLORS.get(kind, "MUTED")
    return value if value.startswith("#") else SCHEMES[name][value]


def css():
    """The scheme as CSS variables, for the browser control pages."""
    t = SCHEMES[name]
    return {"--bg": t["BG"], "--panel": t["NAV"], "--raised": t["KEY"], "--hover": t["KEY_HOVER"], "--text": t["INK"],
            "--dim": t["INK_DIM"], "--accent": t["LIT"], "--accent-ink": t["LIT_INK"], "--live": t["REC"]}


use(DEFAULT)
