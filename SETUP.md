# Setup

Exact steps, in order. Paths use `C:\Users\<you>\...`; replace `<you>` with your Windows user name.

- **Part A:** the admin's PC (runs OBS and records). Once.
- **Part B:** every recording session.
- **Part C:** a guest joining online. Once per guest.
- **Part D:** every session, for a guest.

---

## Part A: admin PC, first time

### A1. Install the programs
1. Install **OBS Studio** from https://obsproject.com (version 28 or newer).
2. Install **Python** from https://www.python.org/downloads. On the first installer screen, tick
   **Add python.exe to PATH**, then click **Install Now**.
3. Get this project: on GitHub, click **Code** → **Download ZIP**, then extract it to
   `C:\Users\<you>\source\repos\podcast-deck`.
4. Press the **Windows key**, type `cmd`, press **Enter**. In the black window, paste this and press
   **Enter**:
   ```
   py -m pip install -r C:\Users\<you>\source\repos\podcast-deck\requirements.txt
   ```
5. Wait until it finishes, then close the window.

### A2. Get the OBS password
1. Open **OBS**.
2. Click **Tools** → **WebSocket Server Settings**.
3. Tick **Enable WebSocket server**. Leave the port at **4455**.
4. Click **Show Connect Info**, then click **Copy** next to **Server Password**.
5. Click **OK** twice.

### A3. Fill in config.py
1. Open File Explorer and go to `C:\Users\<you>\source\repos\podcast-deck`.
2. Right-click **config.example.py** → **Copy**, then right-click an empty spot → **Paste**.
3. Rename the copy to **config.py**.
4. Right-click **config.py** → **Open with** → **Notepad**.
5. On the `OBS_PASSWORD` line, replace `CHANGE_ME` with the password you copied (keep the quotes).
6. On the `CAMS` line, put one name per camera, left to right, for example
   `["Host 1", "Host 2", "Host 3"]`. Real names are fine here; this file is never uploaded.
7. Click **File** → **Save**, then close Notepad.

### A4. Build the layouts
1. Make sure **OBS is open**.
2. Press the **Windows key**, type `cmd`, press **Enter**.
3. Paste this and press **Enter**:
   ```
   py C:\Users\<you>\source\repos\podcast-deck\build_scenes.py
   ```
4. Each source and layout is listed as it's made. It ends with **Done**.
5. Close the window. OBS now has the layouts in its **Scenes** list.

### A5. Pick the webcams and browser window in OBS
1. In OBS, click **Just Us** in the **Scenes** list.
2. In the **Sources** list, double-click **Cam - Host 1** (your first camera name).
3. In **Device**, pick that person's webcam. Click **OK**.
4. Repeat for each **Cam - …** source that's a webcam in the room. (Remote cameras come in Part C.)
5. Click **Browser + Cams** in **Scenes**, double-click **Browser Window** in **Sources**, pick your
   browser in **Window**, and click **OK**.

### A6. Make a desktop shortcut
1. In File Explorer, go to `C:\Users\<you>\source\repos\podcast-deck`.
2. Right-click **Podcast Deck.bat** → **Show more options** → **Send to** → **Desktop (create shortcut)**.

---

## Part B: every session (admin)

1. Open **OBS**.
2. Double-click **Podcast Deck** on your desktop. The deck window opens and stays on top.
3. Click a layout to start on.
4. Click **Record** (or press `ctrl+alt+r`).
5. Switch layouts with the buttons, `ctrl+alt+1` … `ctrl+alt+9`, or the mouse back button.
6. Click **Stop recording** when you're done. The file is in OBS's recordings folder (in OBS:
   **Settings** → **Output** → **Recording Path**).

---

## Part C: a guest joining online, first time

The admin does C1–C3 and C6. The guest does C4, C5, and C7.

### C1. Admin: install Tailscale
1. Install **Tailscale** from https://tailscale.com/download and sign in.
2. Leave it running (its icon is in the taskbar corner).

### C2. Admin: share your PC with the guest
1. Open https://login.tailscale.com/admin/machines.
2. Click the **⋯** menu next to your PC → **Share**.
3. Click the **Copy invite link** tab, then **Copy share link**.
4. Send the link to the guest.

### C3. Admin: make the guest's invite
1. Open OBS, then the deck.
2. Click **Guests…** in the deck.
3. Click **Copy invite** next to the guest's name.
4. Send the invite to the guest privately (a direct message, not a public channel).

### C4. Guest: install Tailscale and accept the share
1. Install **Tailscale** from https://tailscale.com/download and sign in. Use your own account
   (free); you only get access to the admin's one shared PC.
2. Open the share link the admin sent and accept it.

### C5. Guest: send your camera with VDO.Ninja
1. Make up a long, hard-to-guess ID, for example `h2-q8v1z7r4m3`. Use the same one every session.
2. In your browser, open `https://vdo.ninja/?push=` followed by your ID, for example
   `https://vdo.ninja/?push=h2-q8v1z7r4m3`.
3. Allow the camera and microphone, then click **Start**.
4. Send your ID to the admin privately.

### C6. Admin: add the guest's camera
1. Open `config.py` in Notepad (right-click → **Open with** → **Notepad**).
2. In `REMOTE_CAMS`, add a line with their camera name and ID:
   ```python
   REMOTE_CAMS = {
       "Host 2": "https://vdo.ninja/?view=h2-q8v1z7r4m3",
   }
   ```
3. Click **File** → **Save**.
4. With OBS open, run `build_scenes.py` again (Part A4, steps 2–5).

### C7. Guest: set up the deck
1. Install **Python** and get this project (Part A1, steps 2–5). You don't need OBS.
2. In `C:\Users\<you>\source\repos\podcast-deck`, copy **config.example.py** and rename the copy to
   **config.py** (Part A3, steps 1–3).
3. Open **config.py** in Notepad and change these two lines:
   ```python
   ADMIN = False
   INVITE = "podcast-deck://…"     # paste the invite the admin sent you
   ```
4. Click **File** → **Save**.
5. Make a desktop shortcut (Part A6).

---

## Part D: every session (guest)

1. Make sure **Tailscale** is running.
2. Open your **VDO.Ninja** link (Part C5, step 2) and click **Start**.
3. Double-click **Podcast Deck** on your desktop. The title bar shows your name once it connects.
4. Drag your camera on the screen map to move it. Drag the small square in its corner to resize it.

If the admin turns on **Guests get full control**, the layout buttons, **Record**, **Background ▾**,
and **Play link…** appear on your deck too.
