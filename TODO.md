# TODO

Everything still left to do, in rough order. Check items off as they're done and move finished work
into the README's Changelog.

## Test against real OBS

Nothing has been run against real OBS yet. Do this before building anything new.

- [ ] Open OBS → Tools → WebSocket Server Settings → enable it and set a password.
- [ ] Create `config.py` from `config.example.py` and fill in the OBS password and cam names (real
      names only ever go in `config.py`, which is git-ignored).
- [ ] Install dependencies:
      `py -m pip install -r C:\Users\<you>\source\repos\podcast-deck\requirements.txt`
- [ ] Run `py C:\Users\<you>\source\repos\podcast-deck\build_scenes.py` and confirm all six layouts
      appear in OBS without errors.
- [ ] In OBS, point each `Cam - …` source at a real webcam and `Browser Window` at the browser.
- [ ] Launch `Podcast Deck.bat` and check:
  - [ ] The window opens with no console and stays on top.
  - [ ] Colors look right: blue for the active layout, red for recording.
  - [ ] Clicking a layout switches the OBS scene.
  - [ ] `ctrl+alt+1`–`6` switch layouts, including while a full-screen game has focus.
  - [ ] `ctrl+alt+r` starts and stops recording.
  - [ ] Mouse back button cycles layouts; forward button toggles recording.
  - [ ] Closing and reopening OBS: the deck reconnects on its own.
- [ ] Record a short test clip and watch it back: layouts swap cleanly and cams are positioned well.
- [ ] Fix whatever breaks, and note anything surprising in the README's Troubleshooting section.

## Try with the real setup

- [ ] Discord StreamKit voice overlay: get the widget URL, put it in `config.py`, rerun
      `build_scenes.py`, and check that the icons light up when people talk.
- [ ] Decide how remote hosts' video comes in (local webcams vs. Discord call window capture) and
      update the cam sources and README to match.
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
- [ ] **Settings window.** Edit config from the deck instead of a Python file.
- [ ] **Auto-updating app (later).** Ship the deck as an installed app that updates itself, so when a
      new version is released, everyone using it gets the update without re-downloading or
      re-running setup.

## Layout templates

- [ ] Get the planned layout templates and rebuild `LAYOUTS` in `build_scenes.py` to match. The
      current six are a starting point.

## Sharing with the other hosts

- [ ] Have another host test the deck on their own PC once it works on the main one.
- [ ] Add hosts as collaborators on GitHub (repo → Settings → Collaborators) if they need the code.
- [ ] Or build the standalone exe with `build_exe.bat` and send `PodcastDeck.exe` plus a `config.py`.
- [ ] Have someone follow the README from scratch on a fresh PC to make sure the setup steps work.

## Docs

- [ ] Rewrite the README's Development workflow section: it still describes editing in a GitHub
      Codespace, but work now happens locally in the Claude desktop app.
