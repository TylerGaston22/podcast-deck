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
  - [ ] Play link…: a pasted YouTube link plays in the Video + Cams box, with sound in the recording.
  - [ ] Paste link with a picture link: it downloads and becomes the background.
  - [ ] Paste link with a YouTube link: the browser page opens, nothing changes in OBS until Use as
        background (or Switch), then it plays in the background. Pause, mute, volume, and seek on the
        page change it in OBS, with sound in the recording. Stop takes it away.
  - [ ] "Now:" line and the screen map show the right background and video titles.
  - [ ] A link to a video that blocks embedding shows the "can't be played here" message.
  - [ ] Restart option off: leaving and returning to Video + Cams picks up mid-video. On: it starts over.
  - [ ] Video + Cams: cams sit beside the video box without covering it.
  - [ ] Screen map: dragging a camera moves it in OBS, the corner square resizes it, and Reset camera
        puts it back. Its name tag moves with it.
  - [ ] Closing and reopening the deck: cameras start on their default spots again.
  - [ ] Settings: Save camera spots as default, then reopen the deck: they start there. Reset cameras
        to default works. Show names on cams hides and shows the tags.
  - [ ] Settings → Backgrounds: give Just Us a default and an extra (one uploaded with Add picture…).
        Switching to Just Us puts up the default; Background ▾ lists Just Us's first; ctrl+alt+b flips
        between them.
- [ ] Record a short test clip and watch it back: layouts swap cleanly and cams are positioned well.
- [ ] Fix whatever breaks, and note anything surprising in the README's Troubleshooting section.

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
      until the admin ticks "Guests get full control". Then they all work.
- [ ] Unticking it takes the controls away again within a couple of seconds.
- [ ] Settings… → Guests → Remove: the guest's deck stops working right away.
- [ ] Two people dragging at the same time don't undo each other's moves.
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
      re-running setup.

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
