# Setup

Exact steps, in order.

- **Part A:** the PC that runs OBS and records (the admin). Once.
- **Part B:** every recording session.
- **Part C:** someone joining online (a guest). Once per guest.
- **Part D:** every session, for a guest.

---

## Part A: admin, first time

1. Install **OBS Studio** from https://obsproject.com, open it once, then close it.
2. Go to https://tylergaston22.github.io/podcast-deck/ and click **Download for Windows**.
3. Open **PodcastDeck-Setup.exe**. If Windows says it protected your PC, click **More info** → **Run
   anyway**. It installs the deck, puts **Podcast Deck** on your desktop, and opens it. It updates itself
   from then on.
   (Developers: you can instead clone the repo and run **Install.bat**; that copy updates with git.)
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
3. In the deck, click **Invite / Join** at the top right, type the guest's name, and click **Invite**. Their
   camera goes into every layout, and their **invite link** is copied. Paste the Tailscale share link from
   step 2 into the box below it to include it, then send the link to them privately. (Already in the
   group? Click their name at the top → **Copy invite link**.)

### Guest
Open the invite link the admin sent you. It walks you through it:
1. **Get Tailscale** and sign in with your own free account, then **Accept the host's share** (or open the
   share link the admin sent separately).
2. **Download for Windows**, and open **PodcastDeck-Setup.exe** (More info → Run anyway, if Windows asks).
3. **Join the show**: the deck opens with your invite. Type the name to show on your camera, and click
   **Join**.

Got a new invite later? Click **Join the show** on its page again, or paste it with **Invite / Join** at
the top right of the deck. Change your name in **Settings…** → **You**.

---

## Part D: every session (guest)

1. Make sure **Tailscale** is running.
2. Double-click **Podcast Deck** on your desktop.
3. Click **Start my camera**, and allow the camera and mic in the browser tab that opens.

Drag your camera on the screen map to move it. Drag the small square in its corner to resize it.
