# YouTube Subscription Auditor

A local Python script that connects to your YouTube account, fetches all your subscribed channels, and generates an interactive HTML report showing:

- When each channel last posted a video
- Average number of videos per year
- Total video count

The goal is to quickly identify inactive or dormant channels so you can clean up your subscriptions.

---

## Requirements

- Python 3.11 or newer
- A Google account with YouTube subscriptions
- A free Google Cloud project (instructions below)

---

## Installation

### 1. Download the yt_audit.py script

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install google-api-python-client google-auth-oauthlib pandas
```

---

## Google Cloud setup

This is a one-time setup. The script uses the YouTube Data API v3, which requires OAuth 2.0 credentials from a Google Cloud project.

### Step 1 — Create a Google Cloud project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click the project dropdown at the top → **New Project**
3. Give it a name (e.g. `yt-auditor`) and click **Create**

### Step 2 — Enable the YouTube Data API v3

1. In the left menu, go to **APIs & Services → Library**
2. Search for **YouTube Data API v3**
3. Click on it and press **Enable**

### Step 3 — Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Select **External** as the user type → **Create**
3. Fill in the required fields:
   - App name: anything you like (e.g. `YT Auditor`)
   - User support email: your email address
   - Developer contact email: your email address
4. Click **Save and Continue** through the remaining steps (Scopes and Test users)
5. On the **Test users** step, click **Add users** and add your own Google account email
6. Click **Save and Continue** → **Back to Dashboard**

> The app stays in "Testing" mode, which is fine for personal use. You never need to publish it.

### Step 4 — Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name: anything (e.g. `yt-auditor-desktop`)
5. Click **Create**
6. In the dialog that appears, click **Download JSON**
7. Save the downloaded file as **`client_secrets.json`** in the same folder as `yt_audit.py`

---

## Usage

### Basic run

```bash
python yt_audit.py
```

On the first run, a browser window will open asking you to log in with your Google account and grant read-only access to your YouTube data. After that, credentials are saved to `token.json` and all subsequent runs are fully automatic.

### Options

```
--no-cache       Ignore cache and re-fetch all channels from the API
--output-dir     Directory to write output files (default: current directory)
```

Example:

```bash
python yt_audit.py --output-dir ~/Desktop/yt-report
```

### Force a full refresh

```bash
python yt_audit.py --no-cache
```

---

## Output files

| File | Description |
|---|---|
| `yt_audit.html` | Interactive report — open in any browser |
| `yt_audit.csv` | Raw data — open in Numbers, Excel, or similar |
| `channel_cache.json` | API response cache (auto-managed, do not edit) |
| `token.json` | OAuth token (auto-managed, do not share or commit) |

> **Important:** Do not commit `token.json` or `client_secrets.json` to version control. Both files are listed in `.gitignore`.

---

## The HTML report

Open `yt_audit.html` in any browser. No internet connection required — it is fully self-contained.

**Filters:**
- *Show channels inactive for more than* — filter by inactivity threshold (6 months / 1 year / 2 years / 3 years). Defaults to 1 year.
- *Max avg videos/year* — filter by upload frequency
- *Search* — filter by channel name

**Sorting:** Click any column header to sort.

**Color coding:**

| Indicator | Meaning |
|---|---|
| Red left border | No uploads in over 2 years |
| Orange left border | No uploads in 1–2 years |
| Red badge | Less than 1 video per year on average |
| Amber badge | 1–6 videos per year on average |
| Green badge | More than 6 videos per year on average |

---

## API quota

The YouTube Data API v3 provides a free daily quota of **10,000 units** per Google Cloud project. This script uses roughly 3–4 units per channel. For 500 subscriptions, that is approximately 1,500–2,000 units per full run — well within the free limit.

Results are cached locally for **3 days**. Re-running the script within that window skips all API calls and regenerates the report from cache instantly.

---

## Privacy

All data stays on your machine. The script only requests the `youtube.readonly` OAuth scope, meaning it can read your subscription and channel data but cannot modify anything on your account.

---

## Revoking access

To revoke the script's access to your Google account at any time:

1. Go to [https://myaccount.google.com/permissions](https://myaccount.google.com/permissions)
2. Find the app and click **Remove access**

You can also simply delete `token.json` to force a fresh login on the next run.

---

## Disclaimer

This software is provided "as is", without warranty of any kind. Use at your own risk.
The author accepts no liability for any damage or data loss caused by the use of this script.

## License

[MIT](LICENSE) © Manuel Wenger
