# TODO

Everything still left to do, in rough order. Check items off as they're done and move finished work
into the README's Changelog.

## Test against real OBS

Nothing has been run against real OBS yet. Do this before building anything new.

- [x] Install dependencies.
- [x] Open the deck: the first-launch window appears. Click I'm recording, enter names, Start.
- [x] Open OBS: the deck connects with OBS's own password and builds all seven layouts by itself.
      (Found and fixed: layouts were sized for 1080p on a 4K canvas.)
- [x] Settings… shows the webcam, and picking it works. Renaming a camera updates its tag.
      (Found and fixed: the webcam wasn't picked on first build, and was in 4:3.)
- [ ] Your webcam is picked automatically on a fresh setup, within 30 seconds of the deck connecting.
- [x] Record from the deck: the button turns red, and the file plays back with the camera and background.
- [ ] Launch `Podcast Deck.bat` and check:
  - [ ] The window opens with no console and stays on top.
  - [ ] Colors look right: blue for the active layout, red for recording.
  - [ ] Clicking a layout switches the OBS scene.
  - [ ] `ctrl+alt+1`–`7` switch layouts, including while a full-screen game has focus.
  - [ ] `ctrl+alt+r` starts and stops recording.
  - [ ] Mouse back button cycles layouts; forward button toggles recording.
  - [ ] Closing and reopening OBS: the deck reconnects on its own.
  - [ ] Background ▾ → Add picture…: the picture shows behind Just Us, Video + Cams, and Be Right
        Back, and is still there after restarting OBS.
  - [ ] `ctrl+alt+b` steps through saved pictures, including while a game has focus.
  - [x] Play link…: a pasted YouTube link plays in the Video + Cams box. (It loads fine as a local file.)
  - [ ] Play link… opens the browser control page; pause, mute, seek, and Stop video change OBS.
  - [ ] Closing the deck stops both videos.
  - [ ] Delete a source in OBS, then Settings → Cameras → Repair layouts: it comes back.
  - [ ] Paste link with a picture link: it downloads and becomes the background.
  - [ ] Paste link with a YouTube link: the browser page opens, nothing changes in OBS until Use as
        background (or Switch), then it plays in the background. Pause, mute, volume, and seek on the
        page change it in OBS, with sound in the recording. Stop takes it away.
  - [ ] The layout panel's top line and the screen map show the right background and video titles.
  - [ ] A link to a video that blocks embedding shows the "can't be played here" message.
  - [ ] Restart option off: leaving and returning to Video + Cams picks up mid-video. On: it starts over.
  - [ ] Video + Cams: cams sit beside the video box without covering it.
  - [ ] Screen map: dragging a camera moves it in OBS, the corner square resizes it, and Reset camera
        puts it back. Its name tag moves with it.
  - [ ] Closing and reopening the deck: cameras start on their default spots again.
  - [ ] Settings: Save camera spots as default, then reopen the deck: they start there. Reset cameras
        to default works. Show names on cams hides and shows the tags.
  - [ ] New look: OBS and REC pills, color-coded layout rows, Settings → Look switches schemes live.
  - [ ] A layout's ⋯ menu: rename, start on it, default background, tab, color, reset cameras, delete;
        Bring back deleted layouts. Tabs: ＋ makes one, right-click renames or deletes.
  - [ ] Empty Video + Cams box shows the card from Settings → Backgrounds (text or picture).
  - [ ] Drag a layout row to reorder; hotkeys follow. Camera boxes fit the webcam's shape.
  - [ ] ＋ New layout (empty and copy) lands in the current tab. Save layout keeps every source and the
        background picture through a deck restart and Repair layouts.
  - [ ] Settings → Backgrounds: give Just Us a default and an extra (one uploaded with Add picture…).
        Switching to Just Us puts up the default; Background ▾ lists Just Us's first; ctrl+alt+b flips
        between them.
  - [ ] Layout panels: switching layouts opens the live one's panel by itself; − closes it; + on another
        layout switches to it and opens its panel. Play link… shows only on Video + Cams.
  - [ ] Picking a picture from Background ▾ in a panel: switch away and back, and it's still there.
  - [ ] Paste link with a video: Video ready / Switch shows in the panel and works.
  - [ ] Who's in: your name shows with a green square under the header.
  - [x] Layout rows show no hotkey; the + panel shows it.
  - [ ] Settings → Hotkeys: Change… a layout's hotkey
        and press new keys (pressing them doesn't also switch layout), Clear, Default, and Record /
        Next background. A hotkey already in use is refused. They still work after reopening the deck.
  - [x] The desktop shortcut updates the deck: with a new commit on GitHub, opening it brings in the new
        version.
  - [ ] The desktop shortcut still opens the deck when offline, and a changed requirements.txt installs
        the new add-ons.
  - [ ] Invite / Join → Invite someone in the room (box unticked): their camera shows up in every layout.
        Invite someone joining: their code is copied. While recording, the layouts wait until it stops.
  - [ ] Invite / Join → Join their group (admin) and Start my own group (guest): the deck reopens in the
        other role.
  - [ ] Click a name at the top: Copy invite, New invite, Remove from the group (camera leaves the
        layouts).
- [ ] Record a short test clip and watch it back: layouts swap cleanly and cams are positioned well.
- [ ] Fix whatever breaks, and note anything surprising in the README's Troubleshooting section.

## Test on a fresh PC

Checks that the deck works for a new person, not just on the PC it was built on. Use a laptop or any
Windows PC that has never run the deck.

- [ ] Install OBS from obsproject.com, open it once, close it.
- [ ] Clone the repo (or Code → Download ZIP) into `C:\Users\<you>\source\repos\podcast-deck` and run
      Install.bat: Python and add-ons install, the desktop shortcut appears, the deck opens.
- [ ] I'm recording → names → Start, then open OBS: the deck turns on OBS's remote control by itself
      (fresh OBS, no password set), connects, and builds all seven layouts.
- [ ] Layouts fit the canvas on a 1080p screen (the desktop was 4K).
- [ ] A different webcam is picked automatically and shows in 16:9.
- [ ] Without the backgrounds folder or config.py: the deck still starts, and Background shows a clear
      "no pictures yet" state instead of an error.
- [ ] Run the rest of "Test against real OBS" above and note anything that differs from the desktop.

## Automated tests

A pretend OBS saved in the repo so anyone (including Claude in the cloud) can check the deck without
OBS. It catches broken layouts and buttons early, but doesn't replace testing in real OBS.

- [ ] Add a mock OBS (a small fake obs-websocket server) under `tests/`.
- [ ] Tests that `build_scenes.py` builds all seven layouts with sources inside the canvas, at 1080p and 4K.
- [ ] Tests that layout switching, Record, Background, Play link, Repair layouts, and Bring back deleted
      layouts send the right requests.
- [ ] Tests for guest permissions: a guest can only move their own camera, and layout control follows
      "Guests get full control".
- [ ] One command to run them all (`py -m pytest`), and a note in the README.
- [ ] Run them on GitHub on every push (GitHub Actions, Windows runner).

## Test with hosts online

Needs at least one other person on another PC.

- [ ] Install Tailscale on both PCs and share the admin PC with the guest.
- [ ] Guest runs Install.bat on a fresh PC with no Python: it installs Python and opens the deck.
- [ ] Admin: Settings… → Guests → Copy invite, send it. Guest clicks I'm joining → Join. It connects and the
      title bar shows their name.
- [ ] Guest's display name (typed when joining) shows on their name tag and on both screen maps.
      Changing it in Settings → You updates it.
- [ ] Guest clicks Start my camera: VDO.Ninja opens, and their camera shows up in the show (after the
      recording, if one is running).
- [ ] Guest drags and resizes their camera; it moves in OBS within a moment. They can't grab anyone
      else's.
- [ ] The guest's layout buttons are greyed out, and Record, Background, and Play link are hidden,
      until the admin ticks "Guests get full control" (Settings → Guests). Then they all work.
- [ ] Unticking it takes the controls away again within a couple of seconds.
- [ ] Settings… → Guests → Remove: the guest's deck stops working right away.
- [ ] Two people dragging at the same time don't undo each other's moves.
- [ ] Who's in: the guest's square turns green on both decks when their deck connects, and gray about 10
      seconds after they close it.
- [ ] Note in the README how laggy it feels over the internet, and anything else surprising.

## Try with the real setup

- [ ] Discord StreamKit voice overlay: get the widget URL, put it in `config.py`, rerun
      `build_scenes.py`, and check that the icons light up when people talk.
- [ ] Decide how remote hosts' video comes in. VDO.Ninja is built in now (`REMOTE_CAMS`); try it
      against Discord call window capture and update the README with whichever works better.
- [ ] Just Us layout: turn on Crop to Bounding Box for each cam and check that they fill their panels.
- [ ] Use the deck during an actual game to make sure the hotkeys don't clash with game controls.

## Roadmap

Planned features, in priority order. The first two remove the most editing.

- [ ] **Per-episode recording split.** One hotkey that stops and immediately restarts recording, so
      each of the 3–4 episodes in a session is its own file.
- [ ] **Episode markers.** A hotkey that writes a timestamp and label to a text file while recording,
      giving exact cut points for anything that does need trimming.
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
- [ ] **Settings window, the rest.** Settings… covers webcams, the browser window, layouts, and
      guests. Still in `config.py`: hotkeys, mouse buttons, sizes, and the Discord overlay.
- [ ] **Auto-updating app (later).** Ship the deck as an installed app that updates itself, so when a
      new version is released, everyone using it gets the update without re-downloading or
      re-running setup. (Started: the desktop shortcut runs `git pull` each time it opens, for folders
      cloned with git. Still to do: updates for ZIP downloads, e.g. Install.bat turning the folder into a
      git clone, or the deck downloading the newest version itself.)

## Layout templates

- [ ] Get the planned layout templates and rebuild `LAYOUTS` in `build_scenes.py` to match. The
      current seven are a starting point.

## Sharing with the other hosts

- [ ] Have another host test the deck on their own PC once it works on the main one.
- [ ] Add hosts as collaborators on GitHub (repo → Settings → Collaborators) if they need the code.
- [ ] Or build the standalone exe with `build_exe.bat` and send `PodcastDeck.exe` plus a `config.py`.
- [ ] Have someone follow the README from scratch on a fresh PC to make sure the setup steps work.

## Docs

- [ ] Rewrite the README's Development workflow section: it still describes editing in a GitHub
      Codespace, but work now happens locally in the Claude desktop app.
