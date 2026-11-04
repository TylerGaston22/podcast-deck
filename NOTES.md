# Notes

How the deck works when hosts are in different places. Setup steps are in `SETUP.md`.

## The big picture

- **Everyone is equal.** There's no admin. Each person picks what their PC does:
  - **Record my own show:** this PC has OBS. Your deck controls your own OBS, shows everyone's cameras in
    your layouts, and you record or stream your own version.
  - **Camera only:** no OBS needed. You just send your camera (and mic) to the group.
  Switch any time: Settings → Group (recording deck) or Settings (camera-only window).
- **Nobody controls anyone else's OBS.** Decks never talk to each other at all. Each deck only ever
  touches the OBS on its own PC.
- **Cameras travel through VDO.Ninja.** **Start my camera** opens a browser tab that sends your camera
  and mic. Everyone recording shows it in their own OBS, in a `Cam - <name>` source.
- **No Tailscale, no open ports.** Nothing can reach anyone's PC from outside.

## The group

- **A group is a code plus everyone's names**, shared as one link (Invite / Join → Copy link). The same
  link works for everyone, and it walks new people through the download and joining.
- **Each person's camera ID comes from the group code and their name**, so every deck works out
  everyone's camera on its own, with nothing to send around.
- **Names have to match.** Join with the name the others know you by. If you join with a name the link
  doesn't have yet, you're added and the updated link is copied: send it to everyone so their decks add you.
- **Adding someone** (Invite / Join → Add) adds them to your show and the group, and copies the updated
  link to send around. Tick "They're here with me" for someone sharing this PC's webcam instead.
- **Taking someone off** (click their name at the top) only changes your own show.
- **Who's on, at the top:** a square per person, green while their camera is showing in your OBS. The
  camera-only window can't see the others' cameras, so only yours goes green once you've started it.

## Your own camera when you record

- **On your own** (no one else in the group), your camera is a webcam on this PC, picked automatically.
- **In a group with others**, your camera reaches your OBS the same way as everyone else's, through
  VDO.Ninja, so click **Start my camera** too. That's because a webcam usually can't be used by OBS and the
  browser at the same time, and the browser is what sends you to the others.

## Moving cameras

- The deck shows a small map of the screen with the current layout. Drag a camera to move it; drag the
  small square in its corner to resize it. OBS follows along live.
- **Moves are for this session only, and per layout.** The next session starts from the defaults again.
- **Defaults change only in Settings:** Save camera spots as default, or Reset cameras to default.
- **Name tags** sit in each cam's corner and move with it. Settings turns them on or off.

## Backgrounds and layouts

Each layout that shows a background has a default background and optional extras, set in Settings →
Backgrounds (Add picture… uploads your own; it's saved in the `backgrounds` folder). Switching to a layout
puts up its default, however the switch happened. Picking a picture from Background ▾ makes it that
layout's default.

## Safety

- **Keep the group link within the group.** Anyone with it can watch the group's cameras. If a link gets
  out, Invite / Join → **New link…** makes a new one; the old one stops working.
- **Group links never reach a server.** The group rides after the `#` in the join page's address, which
  browsers don't send anywhere.
- **Clicking a group link always asks first** before joining.
- **The background video page is on this PC only.** The deck serves it at `localhost:4461`, never on the
  network. Changing anything needs a secret token that only the deck and the page it opened know, so no
  website can change your background.
- **Pasted links are checked.** Pictures and videos must be `https`, pictures must really be pictures and
  at most 25 MB, and YouTube links must be real video IDs.
- **The OBS password never leaves your PC.** The deck reads it from OBS's own settings.

## Where things are kept

- **In your OBS** (its profile's "persistent data"): default camera spots, each layout's own spots, the
  name tag switch, and each layout's backgrounds.
- **In `config.py`, next to the deck:** your name, whether this PC records, the group code and names, and
  who's on your show. Git-ignored.
- **`backgrounds/`**, next to the deck: your pictures.

## Status

The group model is tested with OBS faked in test scripts. Not yet tried with real OBS and VDO.Ninja
across PCs. The checks are in `TODO.md` under "Test with hosts online".
