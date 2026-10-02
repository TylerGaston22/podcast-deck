# Podcast Deck

Layout switcher for a gaming/movie podcast recorded in OBS. OBS does the compositing
and recording; this adds the "press a button, switch layout" part: a small always-on-top
window, global hotkeys, and optional mouse side buttons that all work while a game has focus.

## Layouts

`build_scenes.py` creates these in OBS from `config.py`:

| Layout            | What's on screen                                        |
|-------------------|---------------------------------------------------------|
| Gameplay + Cams   | Game full screen, everyone small in the bottom-right    |
| Browser + Cams    | A browser window (YouTube, etc.) with cams bottom-right |
| Desktop + Cams    | Whole monitor with cams bottom-right                    |
| Just Us           | Everyone equal size, split across the screen            |
| Gameplay Only     | Game, nothing else                                      |
| Be Right Back     | Plain backdrop with "Be right back"                     |

## Setup (once)

1. Install [OBS](https://obsproject.com) 28 or newer. In OBS: Tools → WebSocket Server Settings → Enable, set a password.
2. Install [Python](https://www.python.org/downloads/) 3.11+ (tick "Add to PATH").
3. Clone or download this repo to `C:\podcast-deck`.
4. Copy `C:\podcast-deck\config.example.py` to `C:\podcast-deck\config.py`. Set `OBS_PASSWORD`, the `CAMS` names, and optionally the Discord StreamKit URL.
5. Install dependencies:

       py -m pip install -r C:\podcast-deck\requirements.txt

6. With OBS open, build the layouts:

       py C:\podcast-deck\build_scenes.py

7. In OBS, double-click each **Cam - …** source and pick the webcam; double-click **Browser Window** and pick the browser.
   Optional: on the Just Us scene, right-click a cam → Edit Transform → tick **Crop to Bounding Box** so cams fill their panels.

## Every session

Double-click `Podcast Deck.bat` (or run `py C:\podcast-deck\deck.py`). A small window appears and stays on top.

Desktop shortcut: right-click `C:\podcast-deck\Podcast Deck.bat` → Send to → Desktop (create shortcut). Rename it, and pick an icon under Properties → Change Icon if you like.

Three ways to switch, all usable mid-game:

- Mouse: click a layout in the window.
- Keyboard: ctrl+alt+1…6 for layouts, ctrl+alt+r for record.
- Mouse side buttons: by default back cycles to the next layout and forward toggles recording. Change or disable in `MOUSE_BUTTONS` in `config.py`.

## Standalone .exe (optional)

Run `C:\podcast-deck\build_exe.bat`. It produces `dist\PodcastDeck.exe`; share it with a `config.py` alongside and the other person doesn't need Python.

## Customizing

- `config.py` — OBS connection, people, cam size, hotkeys, mouse buttons.
- `theme.py` — the deck window's colors and font.
- `build_scenes.py` — the `LAYOUTS` dict at the top. Add a scene there, rerun, and it appears on the deck. Any scene you make by hand in OBS shows up too.

## Notes

- Re-running `build_scenes.py` rebuilds the six layouts; it never touches your sources or other scenes.
- If someone's video comes through a Discord call instead of a local webcam, replace their `Cam - …` source with a Window Capture of Discord, or use Discord StreamKit's video widget as a browser source.
- Hotkeys are global, so pick a prefix none of your games use (ctrl+alt+ is usually safe).
- `config.py` is git-ignored because it holds your OBS password.
