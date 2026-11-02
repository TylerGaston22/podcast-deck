# Setup

Exact steps, in order.

- **Part A:** the PC that runs OBS and records (the admin). Once.
- **Part B:** every recording session.
- **Part C:** someone joining online (a guest). Once per guest.
- **Part D:** every session, for a guest.

---

## Part A: admin, first time

1. Install **OBS Studio** from https://obsproject.com, open it once, then close it.
2. Get the deck, for example into `C:\Users\<you>\source\repos\podcast-deck`:
   - **Best:** clone it with git (`git clone https://github.com/TylerGaston22/podcast-deck`). Then the
     desktop shortcut updates the deck by itself every time you open it.
   - **Or:** on GitHub, click **Code** → **Download ZIP** and extract it. To update, download it again and
     extract it over the old folder (your settings and pictures are kept).
3. In that folder, double-click **Install.bat**. It installs Python if needed, the deck's add-ons, and
   a **Podcast Deck** shortcut on your desktop, then opens the deck.
4. In the deck, click **I'm recording (this PC runs OBS)**.
5. Type everyone's name, separated by commas, and click **Start**.
6. Open **OBS**. The deck connects by itself, sets up all the layouts in OBS, and picks your webcam.

To change a webcam or pick the browser window for Browser + Cams: **Settings…** in the deck.

---

## Part B: every session (admin)

1. Open **OBS**.
2. Double-click **Podcast Deck** on your desktop. If the deck was cloned with git, it gets the newest
   version first (a second or two; if you're offline it just opens).
3. Click **Record**.

---

## Part C: a guest joining online, first time

### Admin, once per guest
1. Install **Tailscale** from https://tailscale.com/download and sign in. (First guest only.)
2. Open https://login.tailscale.com/admin/machines, click the **⋯** menu next to your PC → **Share** →
   **Copy invite link** tab → **Copy share link**, and send the link to the guest.
3. In the deck: **Settings…** → **Guests** → **Copy invite** next to the guest's name, and send it to them privately.

### Guest
1. Install **Tailscale** from https://tailscale.com/download and sign in with your own free account.
2. Open the share link the admin sent and accept it.
3. On GitHub, click **Code** → **Download ZIP**, extract it anywhere, and double-click **Install.bat**.
4. Copy the invite the admin sent you. In the deck, click **I'm joining from somewhere else**. The
   invite is already pasted. Type the name to show on your camera, and click **Join**. (Change it later
   in **Settings…** → **You**.)

---

## Part D: every session (guest)

1. Make sure **Tailscale** is running.
2. Double-click **Podcast Deck** on your desktop.
3. Click **Start my camera**, and allow the camera and mic in the browser tab that opens.

Drag your camera on the screen map to move it. Drag the small square in its corner to resize it.
