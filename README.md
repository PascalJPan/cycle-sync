# Cycle Sync

Syncs menstrual cycle phases to a dedicated Google Calendar sub-calendar with color-coded all-day events.

| Phase | Calendar Color |
|-------|---------------|
| Period | Red (Tomato) |
| Follicular | Green (Sage) |
| Ovulation | Purple (Grape) |
| Luteal | Yellow (Banana) |

---

## Prerequisites

- **macOS** (setup script uses Homebrew)
- **[Homebrew](https://brew.sh)** — install with:
  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

---

## Google Calendar API Setup

You need a `credentials.json` file from Google Cloud Console. This is a one-time setup.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. In the sidebar, go to **APIs & Services → Library**
4. Search for **Google Calendar API** and click **Enable**
5. Go to **APIs & Services → Credentials**
6. Click **+ CREATE CREDENTIALS → OAuth client ID**
7. If prompted, configure the **OAuth consent screen**:
   - Choose **External** user type
   - Fill in the app name (e.g. "Cycle Sync") and your email
   - On the **Scopes** page, add `https://www.googleapis.com/auth/calendar`
   - On the **Test users** page, add your Gmail address
   - Save and go back to Credentials
8. Click **+ CREATE CREDENTIALS → OAuth client ID** again
9. Application type: **Desktop app**
10. Name it anything (e.g. "Cycle Sync Desktop")
11. Click **Create**, then **Download JSON**
12. Rename the downloaded file to `credentials.json`

---

## Install

```bash
git clone https://github.com/PascalJPan/cycle-sync.git
cd cycle-sync
chmod +x setup.sh
./setup.sh
```

`setup.sh` installs Python 3.12 + Tkinter via Homebrew, creates a virtual environment, and installs dependencies.

After setup, move your `credentials.json` into the `cycle-sync` folder.

---

## Launch

```bash
venv/bin/python3 gui.py
```

On first launch, click **Authenticate** — a browser window will open for Google login. After that, use the GUI to add period start dates and sync to your calendar.

---

## Create a macOS App Shortcut (Optional)

1. Open **Automator** (search in Spotlight)
2. Choose **Application**
3. Add a **Run Shell Script** action
4. Set shell to `/bin/bash` and paste:
   ```bash
   cd /path/to/cycle-sync
   venv/bin/python3 gui.py
   ```
   Replace `/path/to/cycle-sync` with the actual folder path.
5. **File → Save** as "Cycle Tracker" to your Applications folder
6. To set a custom icon: right-click the saved app → **Get Info** → drag `Icon.png` onto the icon in the top-left corner

---

## CLI Reference

```bash
# Authenticate with Google Calendar
venv/bin/python3 cycle_sync.py auth

# Sync from a period start date
venv/bin/python3 cycle_sync.py sync --start-date 2025-01-15

# Re-sync from last known date
venv/bin/python3 cycle_sync.py sync

# Full resync (wipe & recreate all events from history)
venv/bin/python3 cycle_sync.py resync

# Remove a wrong date from history
venv/bin/python3 cycle_sync.py remove --date 2025-01-15

# Clear all future events
venv/bin/python3 cycle_sync.py clear

# View cycle length stats
venv/bin/python3 cycle_sync.py stats
```

---

## Config (`config.json`)

| Key | Default | Description |
|-----|---------|-------------|
| `cycle_length_days` | 28 | Fallback cycle length if no history exists |
| `period_length_days` | 5 | Period duration in days |
| `months_ahead` | 2 | How many months to predict ahead |

After 2+ syncs, the cycle length is automatically calculated as the **median** of your past cycles.
