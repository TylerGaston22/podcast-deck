# Notes

How the deck works when hosts join from different places. Setup steps are in the README under
[Hosts joining online](README.md#hosts-joining-online).

## The big picture

- **One PC runs OBS and records: the admin.** Everything on screen and in the recording is put
  together there.
- **Everyone else runs the deck on their own PC: guests.** Guests don't need OBS.
- **Only the admin's deck touches OBS.** Guests' decks send it requests ("move my camera here"), and
  it checks each one before doing anything. Guests never get OBS or its password.
- **Decks only talk over Tailscale**, a private link between your PCs. Nothing is opened to the
  internet, and the deck has no way to do that.
- **Cameras come in separately.** People in the room use webcams, picked automatically. People
  joining online click **Start my camera**: their browser sends their camera and mic through VDO.Ninja,
  and the admin's deck puts it in their `Cam - …` source by itself (after the recording, if one is
  running, so nothing changes mid-episode).

## Who is who

- **Admin:** `ADMIN = True` in `config.py`. `ME` is optional (your camera, selected first on the map).
- **Guest:** `ADMIN = False` and `INVITE = "…"`, the invite the admin sent them. The first-launch
  window writes both, so nobody edits `config.py` by hand.
- **Display names are up to each guest.** They type one when joining and can change it in Settings →
  You. It's what shows on their camera; the invite still decides which camera is theirs.
- **Invites say who you are.** The admin makes one per camera name in **Settings…**, so the invite for
  Host 2 can only ever act as Host 2. **New** replaces an invite and **Remove** cuts that person off.
- **Camera names aren't people.** Two people sharing one camera in the same room share one name, like
  `"Couch"`, and can use the same invite.

## What each deck can do

| | Admin | Guest | Guest with full control |
|---|---|---|---|
| Move and resize their own camera | Yes | Yes | Yes |
| Move anyone's camera | Yes | No | Yes |
| Switch layouts (buttons, hotkeys, mouse) | Yes | No, buttons greyed out | Yes |
| Record | Yes | No | Yes |
| Background ▾ and `ctrl+alt+b` | Yes | No | Yes, from the admin's saved pictures |
| Play link… | Yes | No | Yes |
| Paste link (background picture or video) | Yes | No | Yes, links only (no files from their PC) |
| Add new background pictures | Yes | No | No |
| Invite guests, turn full control on or off | Yes | No | No |

**Full control** is the "Guests get full control" switch on the admin's deck. It's off by default.
Guests' decks notice it within about two seconds, with no restart.

## Moving cameras

- The deck shows a small map of the screen with the current layout. Your camera is the bright box.
  Drag it to move it; drag the small square in its corner to resize it. OBS follows along live.
- **Moves are for this session only, and per layout.** Moving yourself in Gameplay + Cams doesn't change
  Just Us, and the next session starts from the defaults again.
- **Defaults change only in Settings:** Save camera spots as default, or Reset cameras to default.
- **Reset camera** puts one camera back on its default spot.
- **Name tags** sit in each cam's corner and move with it. Settings turns them on or off for everyone.

## Backgrounds and layouts

Each layout that shows a background has a default background and optional extras, set in Settings →
Backgrounds (Add picture… uploads your own; it's saved in the `backgrounds` folder). Switching to a layout
puts up its default, however the switch happened. Anything changed during a session after that (another
picture, moving cams) stays until you switch layouts or the session ends, and never changes the defaults.

## Safety

- **The admin's deck only listens on its Tailscale address.** If Tailscale isn't running, it doesn't
  accept guests at all. It never listens on the home network or the internet.
- **Guests' decks only connect to Tailscale addresses**, and only when Tailscale is running on their PC.
- **Every request needs a valid invite**, and the admin's deck checks what that guest is allowed to do.
  Guests can only use the deck's own actions, never OBS directly. Video links must be YouTube videos,
  and backgrounds must be pictures already saved on the admin's PC.
- **Tailscale encrypts everything** between the PCs.
- **The OBS password never leaves the admin's PC**, and the deck only ever controls the OBS on its own PC.
- **VDO.Ninja IDs work like keys** to watch a camera, so keep them long and private.
- **The background video page is on this PC only.** The deck serves it at `localhost:4461`, never on the
  network. Changing anything needs a secret token that only the deck and the page it opened know, so no
  website can change your background.
- **Pasted links are checked.** Pictures and videos must be `https`, pictures must really be pictures and
  at most 25 MB, and YouTube links must be real video IDs.

## Where things are kept

- **In the admin's OBS** (its profile's "persistent data"): default camera spots saved in Settings,
  each layout's own spots (written by `build_scenes.py`), the name tag switch, each layout's backgrounds,
  and the full-control switch.
- **On the admin's PC, next to the deck:** `guests.json` (the invites), `remote_cams.json` (guests'
  VDO.Ninja IDs), and `backgrounds/` (the pictures). All git-ignored.
- **OBS's password** stays in OBS's own settings. The admin's deck reads it from there.

## Status

Tested on one PC with two decks talking to each other for real, but with OBS and Tailscale faked in the
test scripts. Not yet tried with real OBS, real Tailscale, or VDO.Ninja. The checks for that are in
`TODO.md` under "Test with hosts online".
