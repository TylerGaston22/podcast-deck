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
- [Hosts joining online](#hosts-joining-online)
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

- [x] `build_scenes.py` creates all inputs once in a hidden library scene, then builds seven layouts that
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
- [x] Background menu on the deck: pick a saved picture, add a new one, or go back to the plain color,
      with no OBS menus. `ctrl+alt+b` steps through the saved pictures.
- [x] Play link box on the deck: paste a YouTube link and it plays in the Video + Cams layout, with its
      sound recorded. Videos that can't be embedded get a clear message instead of a blank box.
- [x] Hosts in different places: everyone's in one group, and each person records their own show or just
      sends their camera. Cameras come in through VDO.Ninja; nobody controls anyone else's OBS.
- [x] `Podcast Deck.bat` launches the deck with no console window, so it works as a desktop shortcut.
- [x] The desktop shortcut updates the deck from GitHub each time it opens (when cloned with git), and
      installs any new add-ons.
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
| **Just Us** | Everyone the same size, split evenly across the background picture | Discussion, intros, outros |
| **Gameplay Only** | Game, nothing else | Cinematics, moments that need the whole screen |
| **Be Right Back** | Background picture with "Be right back" | Breaks between episodes |
| **Video + Cams** | A YouTube video large on the right, cams stacked down the left, a dark border (or your background) around them | Trailers and clips without a browser window on screen |

The background picture comes from the deck's **Background** menu. Until one is picked, these layouts use
a plain dark color. The video comes from the deck's **Play link…** box. The Video + Cams box size and
position are `VIDEO_X`, `VIDEO_Y`, `VIDEO_W`, and `VIDEO_H` in `config.py`, and the cams always go on
the side with more room so they never cover the video.

The Discord voice overlay, if configured, sits on top of every "+ Cams" layout and Just Us.

Adding a layout means adding one entry to the `LAYOUTS` dict at the top of `build_scenes.py`. Each entry
is a list of `(source, x, y, width, height)` boxes, bottom to top. Sources are scaled to fit their box
while keeping their aspect ratio.

## Requirements

- Windows 10 or 11
- [OBS Studio](https://obsproject.com) 28 or newer (WebSocket server built in)
- [Python](https://www.python.org/downloads/) 3.11 or newer. `Install.bat` installs it if it's missing.
  Not needed if you use the `.exe`.
- Python packages, all in `requirements.txt`:
  - `obsws-python`: talks to OBS
  - `keyboard`: global hotkeys
  - `mouse`: mouse side buttons
- Optional: a Discord server for the StreamKit voice overlay

## Setup

Click-by-click steps for everyone, including people in other places, are in [SETUP.md](SETUP.md). In
short, on the PC that runs OBS:

1. Install [OBS](https://obsproject.com), open it once, and close it.
2. Download this project and double-click **Install.bat**. It installs Python if needed, the add-ons,
   and a desktop shortcut, then opens the deck.
3. Click **I'm recording**, type everyone's name, and click **Start**.
4. Open OBS. The deck connects by itself, builds the layouts, and picks your webcam.

There's no password to copy: the deck reads OBS's own, and turns on OBS's remote control if it's off.
Webcams and the browser window for Browser + Cams can be changed any time in **Settings…**.

Optional: in the Just Us scene in OBS, right-click each cam → Transform → Edit Transform → tick **Crop to
Bounding Box** so the cams fill their panels instead of letterboxing.

## Every session

1. Open OBS.
2. Double-click **Podcast Deck** on your desktop. If the deck folder was cloned with git, the shortcut
   gets the newest version first; offline, or with files edited in the folder, it just opens as it is.
3. Pick a layout and click **Record**.

## Controls

All three work at the same time, and all of them work while a game has focus.

| Action | Mouse (deck window) | Keyboard | Mouse side buttons (default) |
|---|---|---|---|
| Switch to layout 1–9 | Click the layout | `ctrl+alt+1` … `ctrl+alt+9` | — |
| Next layout | — | — | Back button |
| Start / stop recording | Click Record | `ctrl+alt+r` | Forward button |
| Next background picture | — | `ctrl+alt+b` | — (can be set to `"next background"`) |
| Open or close a layout's panel | ＋ / − on the layout | — | — |
| Pick or add a background | Background ▾ (in the panel) | — | — |
| Paste a picture or video for the background | Paste link (in the panel) | — | — |
| Play a YouTube link | Play link… (in the Video + Cams panel) | — | — |

Hotkey numbers follow the order of the layouts in the deck (drag a row to change it), and each layout's
**+** panel shows its hotkey. Change any of them, including Record and Next background, in **Settings… →
Hotkeys**: click **Change…** and press the keys you want, **Clear** to turn one off, or **Default** to go back.
They're saved on this PC only. The currently active layout is highlighted, and the Record button turns red
while recording.

**Each layout's panel:** click **+** on a layout to open its panel, and **−** to close it. The live
layout's panel opens by itself when you switch to it, and only one is open at a time. Opening the panel
of a layout that isn't live switches to it first, since everything in the panel changes what's showing.
The panel shows the background and any video that's on, then **Background ▾**, **Paste link**, **Play
link…** (only on layouts with a video box, like Video + Cams), and **Save layout**.

**Background ▾** lists every saved picture; click one to switch to it, even mid-recording. The picture
you pick also becomes that layout's default, so switching away and back keeps it. **Add picture…** opens a file picker and copies the picture into the `backgrounds` folder, so it keeps
working if the original moves and stays in the menu from then on. **Plain color** turns the picture
off, and **Open backgrounds folder** lets you add or delete pictures by hand. OBS remembers the
current picture between sessions.

**Paste link** opens a small box for the background. Paste a picture file path, a picture link
(`https://….png` or `.jpg`), a YouTube link, or a direct video link (`https://….mp4`). Pictures switch
right away and are saved with your other backgrounds. Videos open a control page in your browser instead:
play, pause, mute, change the volume, and seek there while nothing changes in the show. When it's ready,
click **Use as background** on that page (or the small **Switch** button that appears in the panel). From
then on, the same page controls the background video live, sound included, and **Stop background video**
takes it away. Picking a picture from Background ▾ also replaces a background video.

The top line of the panel shows what's on: the background (a picture name, or ▶ and the video's
title) and the video in Video + Cams. The screen map shows the same.

**Play link…** opens a small box. Paste a YouTube link (normal, `youtu.be`, Shorts, or live; a `t=`
start time is kept) and press Enter. A link already on the clipboard is pasted in for you. The video
plays in the Video + Cams box with its sound recorded, and a control page opens in your browser: play,
pause, mute, volume, seek, and **Stop video**, which clears the box. The **Restart the video when I
switch away** option decides what happens when you leave Video + Cams: off, the video keeps playing
silently and picks up wherever it has got to; on, it starts over each time you come back.

**Closing the deck stops both videos** (the Video + Cams one and a background video). If the deck isn't
running, OBS's video boxes clear themselves within a few seconds.

**The screen map** under the layout buttons shows where each camera sits in the current layout. Drag a
camera to move it, or drag the small square in its corner to resize it. OBS follows along live, and the
move only affects that layout and only lasts for this session: every session starts from the default
spots. **Reset camera** puts the selected camera back on its default spot. Click a camera to select it.

**The window:** a header with the **OBS** status pill (green when connected, orange when not) and a red
**REC** pill with the running time while recording; **who's on** (below); the **LAYOUTS** list, each
with its **+** panel; the **SCREEN** map; **Record**; and a status bar at the bottom for messages.

**Who's on:** under the header, a small square and name for everyone on your show and in your group,
green while their camera is showing in your OBS. Click a name to take them off your show (their own deck
isn't affected).

**Invite / Join** (on the right of that row): the **group link** to send everyone (**Copy link**, or
**New link…** if one got out), **Add someone** (tick "They're here with me" for someone sharing this PC's
webcam), and **Join a group** by pasting someone's group link. See [Hosts in different places](#hosts-in-different-places).

**Layouts** are color-coded by kind: blue for game, green for talking, magenta for video, yellow for
breaks, gray for your own scenes. The live one has an accent bar. Tabs above the list (**General**, plus
tabs you add with **＋ Tab**) keep them sorted; right-click a tab to rename or delete it. Drag a row up or
down to reorder; the hotkeys and the mouse's next-layout button follow that order, whatever tab is
showing.

**Cameras fit themselves:** each camera's box takes the camera's own shape inside its spot (a 4:3 webcam
gets a 4:3 box), so OBS shows no gaps beside it. If a camera changes shape, its boxes are refitted.

**Save layout** (in the layout's panel) saves the live layout exactly as it is now as its
default: every source's position and size (moved on the map or in OBS), the cameras' spots, and the
background picture showing. New sessions and Repair layouts start from it.

**Each layout's menu** (hover and click **⋯**, or right-click the row): **Save layout as it is
now**, **Rename…** (renames
OBS's scene too), **Start on this layout** (the deck switches to it when it opens), **Default
background**, **Tab**, **Color** (or Automatic, by kind), **Reset cameras here**, and **Delete layout…**.
Repair layouts won't bring back a layout you deleted on purpose; **Bring back deleted layouts** (Settings
→ Cameras) will.

**Settings…** has these tabs:
- **Cameras**: webcams, the browser window, **Show names on cams** (a name tag in each cam's corner that
  moves with it), **Save camera spots as default** / **Reset cameras to default**, **Repair layouts**, and
  **Bring back deleted layouts**.
- **Backgrounds**: every layout that shows a background, each with a **Default** background and ticked
  extras. Switching to a layout puts up its default; picking another lasts until you switch layouts or the
  session ends. **Add picture…** saves a picture of your own and adds it to that layout. On a layout with
  extras, Background ▾ lists them first (★ marks the default) and `ctrl+alt+b` steps through just those.
- **Group**: switch this PC to camera only, and Invite / Join.
- **Hotkeys**: change any hotkey.
- **Help**: setup steps (including turning on OBS's remote control by hand), every session, layouts, fixes
  for common problems, the version, and how the group works.
- **Look**: four color schemes (Stream Launcher, Electric blue, Violet, Teal + orange). It changes right
  away and is remembered on this PC; the browser control pages follow it.

## Hosts in different places

Everyone on the show is in one **group**, and each person picks what their PC does:

- **Record my own show:** the PC has OBS. Your deck controls your own OBS and puts everyone's camera in
  your layouts; you record or stream your own version, arranged however you like.
- **Camera only:** no OBS needed. A small window with **Start my camera**.

Nobody controls anyone else's OBS: decks never connect to each other. Exact steps are in
[SETUP.md](SETUP.md). How it works, and why it's safe, is in [NOTES.md](NOTES.md).

- **One link for everyone.** Invite / Join → **Copy link**. It opens a page that walks people through
  the download, then **Join the show** opens their deck with the group. They type their name and pick
  Record or Camera only.
- **Cameras** travel through VDO.Ninja. **Start my camera** opens a browser tab that sends your camera and
  mic; everyone recording shows it in their own OBS. Each camera's ID comes from the group code and the
  person's name, so names have to match what the others typed.
- **New people:** Invite / Join → **Add**, then send the updated link to everyone (it's copied for you).
  Someone who joins under a name the link doesn't have gets the updated link to send around.
- **When you record in a group,** your own camera comes through VDO.Ninja too, so click Start my camera.
  (A webcam usually can't be used by OBS and the browser at once.) On your own, it's a webcam on your PC.
- **People in the same room sharing one camera** share one name.
- **Switch roles** any time: Settings → Group (recording deck), or Settings (camera-only window).

## Configuration reference

Everything lives in `C:\Users\<you>\source\repos\podcast-deck\config.py`, copied from `config.example.py`.

| Setting | Default | What it does |
|---|---|---|
| `OBS_HOST` | `"localhost"` | Always `"localhost"`: the deck only controls the OBS on its own PC |
| `OBS_PORT` | `4455` | OBS WebSocket port |
| `OBS_PASSWORD` | `""` | Leave empty: the deck reads OBS's own password |
| `CANVAS_W`, `CANVAS_H` | `1920, 1080` | Only a fallback: layouts follow OBS's real canvas (1080p, 4K, …). Sizes in `config.py` are for 1920×1080 and scale with it |
| `CAMS` | three names | One cam per person, left to right. Changing this re-flows every layout |
| `DISCORD_STREAMKIT_URL` | `""` | Voice widget URL from https://streamkit.discord.com/overlay. Empty to skip |
| `SMALL_CAM_W`, `SMALL_CAM_H` | `320, 180` | Size of each cam in the corner layouts |
| `MARGIN` | `24` | Gap between cams and from the screen edges |
| `HOTKEY_PREFIX` | `"ctrl+alt+"` | Layout hotkeys are this plus a number |
| `RECORD_HOTKEY` | `"ctrl+alt+r"` | Start/stop recording |
| `BACKGROUND_HOTKEY` | `"ctrl+alt+b"` | Next picture in the `backgrounds` folder |
| `LAYOUT_HOTKEYS` | `{}` | Your own hotkey per layout, by name (`""` for none). Set in Settings → Hotkeys |
| `VIDEO_X`, `VIDEO_Y` | `432, 135` | Top-left corner of the video box in Video + Cams |
| `VIDEO_W`, `VIDEO_H` | `1440, 810` | Size of the video box. Leave room beside it for the cams |
| `RECORD` | `True` | `True`: this PC records its own show with OBS. `False`: camera only |
| `ME` | `""` | Your name in the group (and your cam's name) |
| `GROUP` | `""` | The group's code, from its link. Anyone with it can see the group's cameras |
| `GROUP_PEOPLE` | `[]` | Everyone in the group, by name. Their cams come through VDO.Ninja |
| `REMOTE_CAMS` | `{}` | Only for adding a VDO.Ninja camera by hand |
| `THEME` | `"Stream Launcher"` | The deck's color scheme, picked in Settings → Look |
| `MOUSE_BUTTONS` | back → next, forward → record | Keys: `"x"` (back), `"x2"` (forward), `"middle"`. Values: a scene name, `"next"`, `"record"`, or `"next background"`. `{}` turns it off |

After changing anything except the hotkeys and mouse buttons, run `build_scenes.py` again. Hotkey and
mouse changes only need the deck restarted.

**Appearance:** `C:\Users\<you>\source\repos\podcast-deck\theme.py` holds the deck window's colors and fonts.

## Project structure

```
podcast-deck/
├── build_scenes.py     Creates the sources and layout scenes in OBS from config.py
├── deck.py             The control window: buttons, hotkeys, mouse buttons
├── media.py            Background pictures and YouTube link handling for the deck
├── positions.py        Camera spots, layout settings, and backgrounds, kept in OBS
├── control.py          What the deck can do with this PC's OBS
├── link.py             The group: group links, everyone's camera IDs, VDO.Ninja links
├── obsconfig.py        Reads OBS's own remote-control settings, so nobody copies the password
├── configfile.py       Writes config.py from the first-launch window and Settings
├── Install.bat         One-click setup: Python, add-ons, desktop shortcut
├── SETUP.md            Exact setup steps, click by click
├── NOTES.md            How hosts joining online works
├── TODO.md             Work still to do, including the roadmap
├── player.html         The page OBS shows in the Video + Cams box
├── bgcontrol.py        Background videos: the deck's page server, on this PC only
├── bg_control.html     The browser page for previewing and controlling a background video
├── bg_player.html      OBS's Background Video source: shows bg_frame.html when there's a video
├── bg_frame.html       The background video player, served by the deck from localhost
├── backgrounds/        Pictures added from the deck (git-ignored)
├── config.example.py   Template config. Copy to config.py (git-ignored)
├── theme.py            Deck window colors and fonts
├── requirements.txt    Python dependencies
├── Podcast Deck.bat    Updates the deck (git pull), then launches it with no console. Desktop shortcut target
├── build_exe.bat       Builds the app (and installer) locally, like GitHub's release build
├── version.py          The app's version; GitHub fills it in for each release
├── updater.py          The installed app's self-update from GitHub Releases
├── installer/          Inno Setup script for PodcastDeck-Setup.exe
├── docs/               Download page and group (join) page, served by GitHub Pages
├── .github/workflows/  release.yml: builds and publishes the installer
├── .gitignore          Keeps config.py, build output, and caches out of git
├── LICENSE             MIT
└── README.md           This file
```

## Sharing it without Python

**Download page:** https://tylergaston22.github.io/podcast-deck/ (from `docs/`, on GitHub Pages). Its
**Download for Windows** button always gets the newest `PodcastDeck-Setup.exe`:
https://github.com/TylerGaston22/podcast-deck/releases/latest/download/PodcastDeck-Setup.exe

- **The installer** needs no Python, git, or admin rights. It installs to
  `C:\Users\<you>\AppData\Local\Programs\Podcast Deck`, adds desktop and Start menu shortcuts, and lets
  `podcast-deck://` group links open the deck.
- **Updates:** the installed deck checks for a newer release each time it opens and installs it by itself
  (never mid-recording). `config.py` and backgrounds are kept.
- **Group links:** Invite / Join gives you one link to `docs/join.html` for everyone. That page walks them
  through the download, and its **Join the show** button opens their deck with the group. The group rides
  after the `#`, so it never reaches any server.
- **Releases** are built by GitHub (`.github/workflows/release.yml`) on Windows whenever the deck's code
  changes on `main`, numbered 1.0.1, 1.0.2, and so on. Run it by hand from the Actions tab if needed.
- **Building it yourself:** `build_exe.bat` makes the same app in `dist\PodcastDeck\` (plus the installer
  if Inno Setup is installed).

A source folder cloned with git still works as before, and updates through `Podcast Deck.bat`.

## Troubleshooting

**"OBS not reachable"**
OBS isn't open, the WebSocket server is off, or the password in `config.py` doesn't match. Check
Tools → WebSocket Server Settings in OBS. The deck retries every two seconds, so it connects on its
own once OBS is ready.

**"No config.py yet"**
Open the deck from the desktop shortcut. The first-launch window writes `config.py` for you.

**Hotkeys don't work in a specific game**
If the game runs as administrator, Windows blocks hotkeys from programs that aren't. Run the deck as
administrator too (right-click the shortcut → Run as administrator). Also check the game doesn't use
the same key combo, and change the clashing hotkey in Settings → Hotkeys if it does.

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

**"Something the deck made is missing in OBS" / deleted a source by accident**
Click **Settings…** → **Cameras** → **Repair layouts**. It puts back every source and layout the deck
made and rebuilds the layouts. Your own scenes, and the settings of sources that still exist, are left
alone. A deleted webcam source is set up again, webcam included.

**A pasted background video doesn't show in OBS**
The deck has to be open, since OBS gets the background video from it. If you set up OBS before
background videos existed, click **Settings…** → **Cameras** → **Repair layouts** once to add the Background Video
source.

**"This video can't be played here"**
The video's owner has turned off playing it outside YouTube, or it's private, deleted, or
age-restricted. Open it in a browser and use Browser + Cams instead.

**Someone's camera doesn't show up in my OBS**
They need to click **Start my camera** and allow the camera in the browser tab, and keep it open. Their
name has to match the one in your group (the row at the top): if they joined under another spelling, take
the extra name off and ask them to rejoin with the link. A new person also needs your deck to know them:
Invite / Join → Add, or paste the updated group link they sent.

**My own camera is black after joining a group**
In a group, your camera reaches your OBS through VDO.Ninja like everyone's. Click **Start my camera**
and allow the camera. Close other apps using the webcam first.

**Re-running `build_scenes.py` reset my layout tweaks**
It rebuilds the seven layouts from config every time, and cameras go back to their default spots
(including ones saved in Settings). For other changes, edit `LAYOUTS` in `build_scenes.py`, or build your
own scenes in OBS under different names. Those are never touched and still show up on the deck.

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

Planned features, in priority order, live in [TODO.md](TODO.md) along with the rest of the work
still to do.

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

**Changes**

- Deck window colors in `theme.py` now match the stream launcher's palette.

**Background pictures and video links**

- Background menu and `ctrl+alt+b` hotkey for changing the background picture from the deck.
- Play link box that plays a pasted YouTube link in the new Video + Cams layout, with recorded sound.
- New Video + Cams layout, with the video box size and position in `config.py`.
- Just Us and Be Right Back now show the background picture.

**Hosts joining online**

- Admin and guest decks: only the admin's deck touches OBS. Guests' decks send it requests over
  Tailscale with a personal invite, and it checks each one. Guests never get the OBS password.
- Screen map on the deck for dragging and resizing cameras. Moves last for the session; defaults are
  saved from Settings. Reset button returns a camera to its default spot.
- Admin switch that gives guests full control: layouts, recording, background, video links, and
  every camera.
- `REMOTE_CAMS` for bringing in remote cameras with VDO.Ninja.

**Name tags and defaults**

- Name tags on cams, shown or hidden from Settings.
- Camera moves last for the session only; Settings saves or resets the default spots.
- Each layout can have a default background and extra ones, set in Settings → Backgrounds, with your
  own uploaded pictures. Switching to a layout puts up its default.
- Settings is split into tabs: Cameras, Backgrounds, Guests, Help.
- Guests choose the name shown on their camera, and can change it in Settings → You.
- Video + Cams now has the video on the right and the cams stacked down the left.

**From the first real OBS test**

- Layouts follow OBS's real canvas size, so a 4K canvas no longer gets half-size layouts in one corner.
- Webcams are set to their sharpest 16:9 resolution (up to 1080p), so they fill their box.
- The deck keeps trying to pick a webcam for the first 30 seconds, since OBS can be slow to list them.
- Settings → Cameras: one row per camera, with the name shown on it and its webcam.
- Dragging on the screen map snaps to corners, edges, and center lines (hold Shift to move freely).

**A deck that looks like an app**

- Header with status pills (OBS connected, REC with timer), section labels, and a status bar.
- Four color schemes in Settings → Look, starting from the stream launcher's own palette.
- Layouts color-coded by kind, sorted into tabs you make, each with a menu: rename, start on it, default
  background, tab, color, reset cameras, delete. Bring back deleted layouts in Settings.
- The empty Video + Cams box shows a card ("Video coming up", or a picture), set in Settings → Backgrounds.
- ＋ New layout (empty, or a copy of another) and Save layout (every source, plus the background picture).
- Drag layouts to reorder them; camera boxes fit each camera's real shape.

**Everyone records their own show**

- No more admin and guests. Everyone's in one group, and each person picks **Record my own show** (with
  OBS) or **Camera only**. Nobody controls anyone else's OBS, and Tailscale isn't needed.
- One group link for everyone (Invite / Join → Copy link); its page walks people through the download.
- Cameras come through VDO.Ninja, with IDs worked out from the group and each person's name.
- Who's on: green while someone's camera is showing in your OBS.

**Updates itself**

- The desktop shortcut gets the newest version from GitHub each time it opens (when the folder was
  cloned with git), and installs any new add-ons first.

**Hotkeys in the panel, and your own hotkeys**

- Layout rows no longer show their hotkey; it's in each layout's **+** panel.
- Settings → Hotkeys: change, clear, or reset the hotkey for any layout, Record, and Next background.

**Layout panels and who's in**

- Each layout has a **+** panel with Background ▾, Paste link, Play link… (layouts with a video box only),
  and Save layout. The live layout's panel opens by itself; **−** closes it. The MEDIA section is gone.
- A picture picked from Background ▾ on the admin's deck becomes that layout's default.
- Who's in: a green or gray square and name for everyone in the group, under the header.
- Invite / Join on the right of that row: invite someone (their code is copied), or paste a code to join a
  group. Click a name to copy, renew, or remove.

**Browser-controlled Video + Cams video, and Repair**

- Play link… opens a browser control page for the Video + Cams video: play, pause, mute, volume, seek,
  stop.
- Closing the deck stops both videos; OBS's video boxes clear when the deck isn't running.
- Settings → Cameras → Repair layouts puts back anything deleted in OBS.

**Background videos and what's on**

- Paste link: pictures (files or links) become the background right away; videos open a browser control
  page, and switch only when you click Use as background (or Switch on the deck).
- The browser page controls the background video live: play, pause, mute, volume, and seek.
- "Now:" line and screen map labels show the background and the Video + Cams video.

**Easier setup**

- `Install.bat`: one double-click installs Python if needed, the add-ons, and the desktop shortcut.
- First-launch window: "I'm recording" or "I'm joining" writes `config.py`, so nobody edits it by hand.
- The deck reads OBS's password from OBS itself, and turns on OBS's remote control if it's off.
- Layouts are built automatically the first time, and webcams are picked automatically.
- Settings window: webcams, browser window, Repair layouts, guest invites, and How it works.
- Start my camera: guests send their camera with one click, and the admin's deck adds it by itself.

## License

MIT. See [LICENSE](LICENSE).
