# Podcast Deck

A layout switcher for recording a multi-person gaming, movie, and TV podcast in OBS, built so the
episode comes out of the recording already "edited". Press a button, click the mouse, or hit a hotkey
and the recording swaps between gameplay with everyone's cams in the corner, everyone split across
the screen, a browser tab or YouTube clip with cams, and so on. What OBS records is the finished
episode.

It works like a stream deck tailored to one show: no extra hardware, built on top of OBS instead of
replacing it.

---

## Contents

- [Why this exists](#why-this-exists)
- [Goals](#goals)
- [How it works](#how-it-works)
- [What's built so far](#whats-built-so-far)
- [Layouts](#layouts)
- [Requirements](#requirements)
- [Setup](#setup)
- [Every session](#every-session)
- [Controls](#controls)
- [Configuration reference](#configuration-reference)
- [Project structure](#project-structure)
- [Sharing it without Python](#sharing-it-without-python)
- [Troubleshooting](#troubleshooting)
- [Design decisions](#design-decisions)
- [Roadmap](#roadmap)
- [Development workflow](#development-workflow)
- [Changelog](#changelog)
- [License](#license)

---

## Why this exists

This started as a question from a friend: three of us want to start a podcast about games, movies, and
TV shows. Could there be a template where our cams or Discord icons sit on top of the gameplay
automatically, so we record one screen and skip editing it together afterwards? And could one button
switch to a layout that's just the three of us split across the screen, or just a browser tab or
YouTube?

The plan for the show:

- A 3–4 hour sit-down each weekend, recording 3–4 episodes back to back.
- Upload those episodes through the following week.
- Cover games, movies, and TV, so the layout needs change from segment to segment: gameplay,
  trailers and clips, discussion, breaks.
- Spend as little time editing as possible. Editing everything by hand is the work this tool is
  meant to remove.

OBS can already do all of the compositing, but it isn't intuitive, and switching scenes by hand in the
middle of a conversation is clumsy. This project sets OBS up once from a config file and puts the
switching behind controls you can use without leaving the game.

## Goals

**Primary**

1. **Record finished episodes.** Whatever is on screen during recording is what gets uploaded. Layout
   changes happen live, not in an editor.
2. **One action to switch layouts.** A click, a key combo, or a mouse side button, all usable while a
   game has focus.
3. **Repeatable setup.** The layouts are defined in code and rebuilt with one command, so they're
   identical every session and easy to tweak.
4. **Shareable.** Anyone can clone the repo, fill in a config file, and have the same setup. A
   standalone `.exe` covers people who don't want to install Python.

**Secondary**

- Feel like a small custom stream deck rather than a general-purpose tool.
- Stay on top of OBS instead of replacing it, so OBS's recording quality, encoders, and audio
  handling all keep working as normal.
- Keep the code small and readable so it's easy to extend.

**Non-goals (for now)**

- Replacing OBS or writing a custom video compositor.
- Live streaming features (chat, alerts, overlays tied to a platform). It's for recording first.
- macOS or Linux support. The target is Windows desktops.

## How it works

```
 config.py ──► build_scenes.py ──(obs-websocket)──► OBS scenes ("layouts")
                                                        ▲
 mouse click / hotkey / side button ──► deck.py ──(obs-websocket)─┘
                                                        │
                                                        ▼
                                                 OBS recording
```

- **OBS** does the video work: capturing the game, cams, browser, and Discord overlay; compositing
  them; recording to disk.
- **obs-websocket** (built into OBS 28 and newer) lets other programs control OBS. Both scripts talk to
  it through the [`obsws-python`](https://pypi.org/project/obsws-python/) library.
- **`build_scenes.py`** reads `config.py` and creates every source and layout scene in OBS. Run it once,
  and again whenever you change the config.
- **`deck.py`** is the control window. It reads the scene list live from OBS, shows a button for each,
  highlights the current one, and switches scenes or toggles recording when you click, press a hotkey,
  or press a mouse side button.

## What's built so far

- [x] `build_scenes.py` creates all inputs once in a hidden library scene, then builds six layouts that
      reference them. Safe to re-run: it rebuilds only the layouts it owns and never touches your
      sources or other scenes.
- [x] Cam positions are calculated from the number of people in `CAMS`, so adding or removing a person
      re-flows every layout automatically.
- [x] Optional Discord StreamKit voice overlay: everyone's Discord icon, lighting up when they talk,
      layered over the cam layouts.
- [x] `deck.py` desktop control window: always on top, one button per layout, current layout lit,
      record button that turns red while recording, live status line, auto-reconnect if OBS restarts.
- [x] Global keyboard hotkeys: `ctrl+alt+1` … `ctrl+alt+9` for layouts, `ctrl+alt+r` for record. They
      work while a full-screen game has focus.
- [x] Mouse side-button bindings: by default, back cycles to the next layout and forward toggles
      recording. Configurable or disableable.
- [x] Any scene added by hand in OBS shows up on the deck automatically with the next free hotkey.
- [x] `Podcast Deck.bat` launches the deck with no console window, so it works as a desktop shortcut.
- [x] `build_exe.bat` packages the deck into a single `PodcastDeck.exe` with PyInstaller.
- [x] Colors and fonts pulled into `theme.py` so the look can be changed in one place.
- [x] Clear error messages when OBS isn't running, the WebSocket server is off, or `config.py` is
      missing.
- [x] Git repo with `.gitignore` (keeps `config.py` and its OBS password out of version control), MIT
      license, and this README.

## Layouts

`build_scenes.py` creates these on a 1920×1080 canvas by default:

| Layout | What's on screen | Typical use |
|---|---|---|
| **Gameplay + Cams** | Game full screen, everyone small in a row at the bottom right | Playing and talking |
| **Browser + Cams** | A browser window full screen, cams bottom right | Trailers, YouTube clips, articles, reviews |
| **Desktop + Cams** | The whole monitor, cams bottom right | Anything that isn't a single window |
| **Just Us** | Everyone the same size, split evenly across the screen | Discussion, intros, outros |
| **Gameplay Only** | Game, nothing else | Cinematics, moments that need the whole screen |
| **Be Right Back** | Plain backdrop with "Be right back" | Breaks between episodes |

The Discord voice overlay, if configured, sits on top of every "+ Cams" layout and Just Us.

Adding a layout means adding one entry to the `LAYOUTS` dict at the top of `build_scenes.py`. Each entry
is a list of `(source, x, y, width, height)` boxes, bottom to top. Sources are scaled to fit their box
while keeping their aspect ratio.

## Requirements

- Windows 10 or 11
- [OBS Studio](https://obsproject.com) 28 or newer (WebSocket server built in)
- [Python](https://www.python.org/downloads/) 3.11 or newer, with "Add to PATH" ticked during install.
  Not needed if you use the `.exe`.
- Python packages, all in `requirements.txt`:
  - `obsws-python`: talks to OBS
  - `keyboard`: global hotkeys
  - `mouse`: mouse side buttons
- Optional: a Discord server for the StreamKit voice overlay

## Setup

Do this once per computer. In the paths below, `<you>` is your Windows username.

1. **Turn on OBS's WebSocket server.** In OBS: Tools → WebSocket Server Settings → tick Enable WebSocket
   server → set a password → OK. Leave the port at 4455.

2. **Get the code.**

   ```
   git clone https://github.com/TylerGaston22/podcast-deck.git C:\Users\<you>\source\repos\podcast-deck
   ```

   Or download the ZIP from GitHub and extract it to `C:\Users\<you>\source\repos\podcast-deck`.

3. **Create your config.**

   ```
   copy C:\Users\<you>\source\repos\podcast-deck\config.example.py C:\Users\<you>\source\repos\podcast-deck\config.py
   ```

   Open `C:\Users\<you>\source\repos\podcast-deck\config.py` and set at least `OBS_PASSWORD` and the `CAMS` names. See the
   [configuration reference](#configuration-reference) for everything else.

4. **Install the Python packages.**

   ```
   py -m pip install -r C:\Users\<you>\source\repos\podcast-deck\requirements.txt
   ```

5. **Build the layouts.** With OBS open:

   ```
   py C:\Users\<you>\source\repos\podcast-deck\build_scenes.py
   ```

   You'll see each source and layout listed as it's created.

6. **Point the sources at your devices.** In OBS:
   - Double-click each **Cam - …** source and pick that person's webcam.
   - Double-click **Browser Window** and pick the browser window.
   - **Game** is set to capture any full-screen game automatically.
   - Optional: in the Just Us scene, right-click each cam → Transform → Edit Transform → tick
     **Crop to Bounding Box** so the cams fill their panels instead of letterboxing.

7. **Make a desktop shortcut.** Right-click `C:\Users\<you>\source\repos\podcast-deck\Podcast Deck.bat` → Send to → Desktop
   (create shortcut). Rename it if you like, and change its icon under Properties → Change Icon.

## Every session

1. Open OBS.
2. Double-click the **Podcast Deck** shortcut, or run:

   ```
   py C:\Users\<you>\source\repos\podcast-deck\deck.py
   ```

3. A small window appears and stays on top of everything. Pick your starting layout, press Record, and
   go.

## Controls

All three work at the same time, and all of them work while a game has focus.

| Action | Mouse (deck window) | Keyboard | Mouse side buttons (default) |
|---|---|---|---|
| Switch to layout 1–9 | Click the layout | `ctrl+alt+1` … `ctrl+alt+9` | — |
| Next layout | — | — | Back button |
| Start / stop recording | Click Record | `ctrl+alt+r` | Forward button |

Hotkey numbers follow the order of the scenes in OBS, and each button in the deck window shows its
hotkey. The currently active layout is highlighted, and the Record button turns red while recording.

## Configuration reference

Everything lives in `C:\Users\<you>\source\repos\podcast-deck\config.py`, copied from `config.example.py`.

| Setting | Default | What it does |
|---|---|---|
| `OBS_HOST` | `"localhost"` | Where OBS is running |
| `OBS_PORT` | `4455` | OBS WebSocket port |
| `OBS_PASSWORD` | `"CHANGE_ME"` | OBS WebSocket password |
| `CANVAS_W`, `CANVAS_H` | `1920, 1080` | Must match OBS Settings → Video → Base Resolution |
| `CAMS` | three names | One cam per person, left to right. Changing this re-flows every layout |
| `DISCORD_STREAMKIT_URL` | `""` | Voice widget URL from https://streamkit.discord.com/overlay. Empty to skip |
| `SMALL_CAM_W`, `SMALL_CAM_H` | `320, 180` | Size of each cam in the corner layouts |
| `MARGIN` | `24` | Gap between cams and from the screen edges |
| `HOTKEY_PREFIX` | `"ctrl+alt+"` | Layout hotkeys are this plus a number |
| `RECORD_HOTKEY` | `"ctrl+alt+r"` | Start/stop recording |
| `MOUSE_BUTTONS` | back → next, forward → record | Keys: `"x"` (back), `"x2"` (forward), `"middle"`. Values: a scene name, `"next"`, or `"record"`. `{}` turns it off |

After changing anything except the hotkeys and mouse buttons, run `build_scenes.py` again. Hotkey and
mouse changes only need the deck restarted.

**Appearance:** `C:\Users\<you>\source\repos\podcast-deck\theme.py` holds the deck window's colors and fonts.

## Project structure

```
podcast-deck/
├── build_scenes.py     Creates the sources and layout scenes in OBS from config.py
├── deck.py             The control window: buttons, hotkeys, mouse buttons
├── config.example.py   Template config. Copy to config.py (git-ignored)
├── theme.py            Deck window colors and fonts
├── requirements.txt    Python dependencies
├── Podcast Deck.bat    Launches the deck with no console. Target for the desktop shortcut
├── build_exe.bat       Builds dist\PodcastDeck.exe with PyInstaller
├── .gitignore          Keeps config.py, build output, and caches out of git
├── LICENSE             MIT
└── README.md           This file
```

## Sharing it without Python

```
C:\Users\<you>\source\repos\podcast-deck\build_exe.bat
```

This installs PyInstaller and produces `C:\Users\<you>\source\repos\podcast-deck\dist\PodcastDeck.exe`. Give someone the `.exe`
with a filled-in `config.py` in the same folder and they can run the deck without Python. They still
need OBS, and someone still needs to run `build_scenes.py` once on their machine (or set up the scenes
by hand).

## Troubleshooting

**"OBS not reachable"**
OBS isn't open, the WebSocket server is off, or the password in `config.py` doesn't match. Check
Tools → WebSocket Server Settings in OBS. The deck retries every two seconds, so it connects on its
own once OBS is ready.

**"No config.py yet"**
Copy `C:\Users\<you>\source\repos\podcast-deck\config.example.py` to `C:\Users\<you>\source\repos\podcast-deck\config.py` and fill it in.

**Hotkeys don't work in a specific game**
If the game runs as administrator, Windows blocks hotkeys from programs that aren't. Run the deck as
administrator too (right-click the shortcut → Run as administrator). Also check the game doesn't use
the same key combo, and change `HOTKEY_PREFIX` if it does.

**Mouse side buttons do nothing**
Some mouse software (Logitech G Hub, Razer Synapse, and so on) remaps the side buttons. Set them back to
"Back" and "Forward" in that software, or bind them to the keyboard hotkeys there instead.

**Game shows as black**
Game Capture can't hook some games, often ones with anti-cheat. Switch the Game source to Window Capture
or use Desktop + Cams.

**Cams look letterboxed in Just Us**
Turn on Crop to Bounding Box for each cam (Setup step 6).

**Someone's video comes through a Discord call, not a local webcam**
Replace their `Cam - …` source with a Window Capture of the Discord call window, or use Discord
StreamKit's video widget as a Browser source.

**Re-running `build_scenes.py` reset my layout tweaks**
It rebuilds the six layouts from config every time. Make permanent changes in `LAYOUTS` in
`build_scenes.py`, or build your own scenes in OBS under different names. Those are never touched and
still show up on the deck.

## Design decisions

- **OBS does the video, this project does the control.** Writing a compositor would take weeks and be
  worse than OBS. Driving OBS over its WebSocket API got a working version in a day.
- **Sources live once, in a library scene.** Every layout references the same inputs, so a webcam is
  opened once and switching layouts is instant.
- **Layouts are generated from config, not hand-placed.** Positions are calculated from the canvas size
  and the number of people, so the layouts stay consistent and adapt automatically.
- **Desktop window instead of a phone web panel.** An early version served a control page to a phone or
  iPad. It changed to a desktop window with global hotkeys and mouse buttons because those keep
  everything on one machine and work mid-game.
- **The deck reads scenes live.** It doesn't keep its own list, so anything made in OBS appears on the
  deck without code changes.
- **Secrets stay out of git.** `config.py` is ignored; `config.example.py` is the template.

## Roadmap

Roughly in priority order. The first two remove the most editing.

- [ ] **Split recording per episode.** One hotkey that stops and immediately restarts recording, so
      each of the 3–4 episodes in a session is its own file.
- [ ] **Episode markers.** A hotkey that writes a timestamp and label to a text file while recording,
      giving exact cut points for anything that does need trimming.
- [ ] **Match the stream launcher's color scheme.** Update `theme.py` to share the palette from the
      stream launcher project.
- [ ] **"Now showing" overlay.** Briefly shows the layout name in OBS when it changes, so swaps are easy
      to spot when reviewing a recording.
- [ ] **Automatic audio ducking.** Lower game audio when switching to Browser + Cams so clips and
      trailers are clear, and restore it on the way back.
- [ ] **Layout preview.** A `--preview` option on `build_scenes.py` that draws all layouts to a PNG,
      so cam sizes and positions can be tuned without opening OBS.
- [ ] **Per-show layout sets.** Separate presets for game, movie, and TV episodes, switched from the
      deck.
- [ ] **Discord video as cam sources.** First-class support for people who join over a Discord call
      instead of a local webcam.
- [ ] **Episode intro and outro scenes.** Title cards with the episode name, set before recording.
- [ ] **Settings window.** Edit config from the deck instead of a Python file.

Ideas welcome: open an issue.

## Development workflow

- **Code lives here on GitHub** and is edited in a GitHub Codespace, with Claude Code in VS Code for
  edits, commits, and pushes.
- **The codespace can't run the deck.** It's Linux with no OBS, keyboard, or mouse to hook. Edit and
  commit there; test on a Windows PC with OBS:

  ```
  git -C C:\Users\<you>\source\repos\podcast-deck pull
  py C:\Users\<you>\source\repos\podcast-deck\build_scenes.py
  py C:\Users\<you>\source\repos\podcast-deck\deck.py
  ```

- **Never commit `config.py`.** It holds the OBS password and is in `.gitignore`.
- Keep changes small, and update this README whenever behavior or setup changes.

## Changelog

**Initial release**

- OBS layout builder with six layouts and optional Discord voice overlay
- Desktop deck window with live scene list, record toggle, and status
- Global hotkeys and mouse side-button bindings
- No-console launcher and standalone `.exe` build script
- Theme file, example config, `.gitignore`, MIT license

**Fixes**

- Mouse back-button key corrected from `"x1"` to `"x"` (the name the `mouse` library actually uses).
  The forward button, `"x2"`, was already right.

## License

MIT. See [LICENSE](LICENSE).
