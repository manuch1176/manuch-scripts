#!/usr/bin/env python3
"""
YouTube Subscription Auditor
Fetches all subscribed channels, their last upload date, and average videos/year.
Outputs a sortable HTML report + CSV.

Requirements:
    pip install google-api-python-client google-auth-oauthlib pandas

Author:  Manuel Wenger

License: MIT (see LICENSE file or https://opensource.org/licenses/MIT)

DISCLAIMER: This software is provided "as is", without warranty of any kind.
Use at your own risk. The author accepts no liability for any damage or data
loss caused by the use of this script.
"""

import os
import json
import math
import argparse
import datetime
from pathlib import Path

import pandas as pd
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
TOKEN_FILE = Path("token.json")
SECRETS_FILE = Path("client_secrets.json")
CACHE_FILE = Path("channel_cache.json")
CACHE_MAX_AGE_DAYS = 3  # re-fetch channels older than this

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_credentials() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not SECRETS_FILE.exists():
                raise FileNotFoundError(
                    f"'{SECRETS_FILE}' not found.\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def build_service():
    creds = get_credentials()
    return build("youtube", "v3", credentials=creds)

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, default=str)


def cache_is_fresh(entry: dict) -> bool:
    fetched_at = entry.get("fetched_at")
    if not fetched_at:
        return False
    age = datetime.datetime.now() - datetime.datetime.fromisoformat(fetched_at)
    return age.days < CACHE_MAX_AGE_DAYS

# ---------------------------------------------------------------------------
# API fetching
# ---------------------------------------------------------------------------

def fetch_subscriptions(service) -> list[dict]:
    """Return list of {channel_id, channel_title}."""
    print("Fetching subscriptions…")
    subs = []
    page_token = None
    while True:
        resp = service.subscriptions().list(
            part="snippet",
            mine=True,
            maxResults=50,
            pageToken=page_token,
            order="alphabetical",
        ).execute()
        for item in resp.get("items", []):
            subs.append({
                "channel_id": item["snippet"]["resourceId"]["channelId"],
                "channel_title": item["snippet"]["title"],
                "channel_thumbnail": item["snippet"].get("thumbnails", {}).get("default", {}).get("url", ""),
            })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        print(f"  … {len(subs)} subscriptions fetched so far")
    print(f"Total subscriptions: {len(subs)}")
    return subs


def fetch_channel_details(service, channel_ids: list[str]) -> dict:
    """
    Batch-fetch channel stats + uploads playlist ID.
    Returns {channel_id: {uploads_playlist_id, published_at, video_count}}
    """
    result = {}
    # API allows up to 50 IDs per call
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        resp = service.channels().list(
            part="contentDetails,statistics,snippet",
            id=",".join(batch),
        ).execute()
        for item in resp.get("items", []):
            cid = item["id"]
            result[cid] = {
                "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
                "published_at": item["snippet"]["publishedAt"],
                "video_count": int(item["statistics"].get("videoCount", 0)),
            }
    return result


def fetch_latest_video(service, uploads_playlist_id: str) -> dict | None:
    """Return {video_id, title, published_at} of the most recent upload, or None."""
    try:
        resp = service.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=1,
        ).execute()
        items = resp.get("items", [])
        if not items:
            return None
        snippet = items[0]["snippet"]
        return {
            "video_id": snippet["resourceId"]["videoId"],
            "video_title": snippet["title"],
            "last_upload_at": snippet["publishedAt"],
        }
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Data enrichment
# ---------------------------------------------------------------------------

def enrich_channel(service, sub: dict, channel_details: dict, cache: dict) -> dict:
    cid = sub["channel_id"]

    # Use cache if fresh
    if cid in cache and cache_is_fresh(cache[cid]):
        return cache[cid]

    details = channel_details.get(cid, {})
    latest = fetch_latest_video(service, details.get("uploads_playlist_id", ""))

    # Calculate avg videos / year
    published_at_str = details.get("published_at", "")
    video_count = details.get("video_count", 0)
    avg_per_year = None
    channel_age_years = None
    if published_at_str:
        created = datetime.datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        channel_age_years = (now - created).days / 365.25
        if channel_age_years > 0:
            avg_per_year = round(video_count / channel_age_years, 1)

    last_upload_at = None
    days_since_upload = None
    if latest and latest.get("last_upload_at"):
        last_upload_at = latest["last_upload_at"]
        last_dt = datetime.datetime.fromisoformat(last_upload_at.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        days_since_upload = (now - last_dt).days

    entry = {
        "channel_id": cid,
        "channel_title": sub["channel_title"],
        "channel_thumbnail": sub.get("channel_thumbnail", ""),
        "channel_url": f"https://www.youtube.com/channel/{cid}",
        "video_count": video_count,
        "avg_videos_per_year": avg_per_year,
        "channel_age_years": round(channel_age_years, 1) if channel_age_years else None,
        "last_upload_at": last_upload_at,
        "days_since_last_upload": days_since_upload,
        "last_video_title": latest["video_title"] if latest else None,
        "last_video_url": f"https://youtu.be/{latest['video_id']}" if latest else None,
        "fetched_at": datetime.datetime.now().isoformat(),
    }

    cache[cid] = entry
    return entry

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def days_to_label(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{math.floor(days/30)}mo ago"
    return f"{round(days/365, 1)}y ago"


def build_dataframe(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Sort by days_since_last_upload descending (most inactive first)
    df = df.sort_values("days_since_last_upload", ascending=False, na_position="first")
    return df


def export_csv(df: pd.DataFrame, path: str = "yt_audit.csv"):
    cols = [
        "channel_title", "last_upload_at", "days_since_last_upload",
        "avg_videos_per_year", "video_count", "channel_age_years",
        "last_video_title", "channel_url",
    ]
    df[cols].to_csv(path, index=False)
    print(f"CSV saved → {path}")


def export_html(df: pd.DataFrame, path: str = "yt_audit.html"):
    now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    rows_html = ""
    for _, r in df.iterrows():
        days = r.get("days_since_last_upload")
        avg = r.get("avg_videos_per_year")

        # Row highlight classes
        row_class = ""
        if isinstance(days, float) and not math.isnan(days):
            days = int(days)
            if days > 730:
                row_class = "inactive-high"
            elif days > 365:
                row_class = "inactive-med"

        # Avg badge colour
        avg_str = "—"
        avg_class = "badge-gray"
        if avg is not None and not (isinstance(avg, float) and math.isnan(avg)):
            avg_str = str(avg)
            if avg < 1:
                avg_class = "badge-red"
            elif avg < 6:
                avg_class = "badge-amber"
            else:
                avg_class = "badge-green"

        thumb = r.get("channel_thumbnail", "")
        thumb_html = f'<img src="{thumb}" width="24" height="24" style="border-radius:50%;vertical-align:middle;margin-right:6px">' if thumb else ""
        ch_url = r.get("channel_url", "#")
        title = r.get("channel_title", "")

        last_video_title = r.get("last_video_title")
        if not isinstance(last_video_title, str):
            last_video_title = None
        last_video_url = r.get("last_video_url")
        if not isinstance(last_video_url, str):
            last_video_url = None
        if last_video_url and last_video_title:
            truncated = last_video_title[:55] + ("…" if len(last_video_title) > 55 else "")
            video_link = f'<a href="{last_video_url}" target="_blank" title="{last_video_title}">{truncated}</a>'
        else:
            video_link = "—"

        rows_html += f"""
        <tr class="{row_class}" data-days="{days if isinstance(days, int) else 99999}" data-avg="{avg if avg else 0}">
          <td>{thumb_html}<a href="{ch_url}" target="_blank">{title}</a></td>
          <td>{days_to_label(days if isinstance(days, int) else None)}</td>
          <td><span class="badge {avg_class}">{avg_str} / yr</span></td>
          <td>{r.get("video_count", "—")}</td>
          <td>{video_link}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Subscription Audit</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f5f5f7; color: #1d1d1f; padding: 24px; }}
  h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 4px; }}
  .meta {{ color: #6e6e73; font-size: 13px; margin-bottom: 20px; }}
  .filters {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }}
  .filters label {{ font-size: 13px; color: #6e6e73; }}
  .filters select, .filters input {{ padding: 6px 10px; border-radius: 8px; border: 1px solid #d2d2d7;
     font-size: 13px; background: #fff; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
  .stat-card {{ background: #fff; border-radius: 12px; padding: 14px 20px; min-width: 130px;
               box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .stat-card .num {{ font-size: 26px; font-weight: 600; }}
  .stat-card .lbl {{ font-size: 12px; color: #6e6e73; margin-top: 2px; }}
  .stat-card.red .num {{ color: #c0392b; }}
  .stat-card.amber .num {{ color: #c47c00; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 12px; overflow: hidden;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); font-size: 14px; }}
  th {{ background: #f5f5f7; padding: 10px 14px; text-align: left;
        font-weight: 500; font-size: 12px; color: #6e6e73; cursor: pointer;
        user-select: none; white-space: nowrap; }}
  th:hover {{ background: #e8e8ed; }}
  th::after {{ content: " ↕"; opacity: .4; }}
  th.asc::after {{ content: " ↑"; opacity: 1; }}
  th.desc::after {{ content: " ↓"; opacity: 1; }}
  td {{ padding: 10px 14px; border-top: 1px solid #f0f0f5; vertical-align: middle; }}
  td a {{ color: #0071e3; text-decoration: none; }}
  td a:hover {{ text-decoration: underline; }}
  tr.inactive-high td:first-child {{ border-left: 3px solid #c0392b; }}
  tr.inactive-med td:first-child {{ border-left: 3px solid #e67e22; }}
  tr:hover td {{ background: #f9f9fb; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 20px;
            font-size: 12px; font-weight: 500; }}
  .badge-red {{ background: #fde8e8; color: #9b1c1c; }}
  .badge-amber {{ background: #fef3c7; color: #92400e; }}
  .badge-green {{ background: #d1fae5; color: #065f46; }}
  .badge-gray {{ background: #f3f4f6; color: #6b7280; }}
  .legend {{ font-size: 12px; color: #6e6e73; margin-top: 12px; display: flex; gap: 16px; }}
  .legend span {{ display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 2px; }}
  #no-results {{ display: none; padding: 32px; text-align: center; color: #6e6e73; }}
</style>
</head>
<body>
<h1>YouTube Subscription Audit</h1>
<div class="meta">Generated {now_str} &nbsp;·&nbsp; {len(df)} channels</div>

<div class="stats" id="stats-cards">
  <!-- filled by JS -->
</div>

<div class="filters">
  <label>Show channels inactive for more than:
    <select id="filter-days">
      <option value="0">all channels</option>
      <option value="180">6 months</option>
      <option value="365" selected>1 year</option>
      <option value="730">2 years</option>
      <option value="1095">3 years</option>
    </select>
  </label>
  <label>Max avg videos/year:
    <select id="filter-avg">
      <option value="999">any</option>
      <option value="1">less than 1</option>
      <option value="3">less than 3</option>
      <option value="6">less than 6</option>
    </select>
  </label>
  <label>Search: <input type="text" id="filter-search" placeholder="channel name…" style="width:180px"></label>
</div>

<table id="main-table">
  <thead>
    <tr>
      <th data-col="0">Channel</th>
      <th data-col="1">Last upload</th>
      <th data-col="2">Avg / year</th>
      <th data-col="3">Total videos</th>
      <th data-col="4">Last video</th>
    </tr>
  </thead>
  <tbody id="tbody">
    {rows_html}
  </tbody>
</table>
<div id="no-results">No channels match the current filters.</div>

<div class="legend">
  <span><span class="dot" style="background:#c0392b"></span> Inactive &gt; 2 years</span>
  <span><span class="dot" style="background:#e67e22"></span> Inactive 1–2 years</span>
</div>

<script>
const tbody = document.getElementById('tbody');
const rows = Array.from(tbody.querySelectorAll('tr'));

function applyFilters() {{
  const minDays = parseInt(document.getElementById('filter-days').value);
  const maxAvg  = parseFloat(document.getElementById('filter-avg').value);
  const search  = document.getElementById('filter-search').value.toLowerCase();
  let visible = 0;
  rows.forEach(r => {{
    const days = parseFloat(r.dataset.days);
    const avg  = parseFloat(r.dataset.avg);
    const name = r.cells[0].textContent.toLowerCase();
    const show = days >= minDays && avg <= maxAvg && name.includes(search);
    r.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('no-results').style.display = visible ? 'none' : 'block';
  updateStats();
}}

function updateStats() {{
  const visible = rows.filter(r => r.style.display !== 'none');
  const total = visible.length;
  const dead  = visible.filter(r => parseFloat(r.dataset.days) > 730).length;
  const slow  = visible.filter(r => parseFloat(r.dataset.avg) < 1).length;
  document.getElementById('stats-cards').innerHTML = `
    <div class="stat-card"><div class="num">${{total}}</div><div class="lbl">channels shown</div></div>
    <div class="stat-card red"><div class="num">${{dead}}</div><div class="lbl">silent &gt; 2 years</div></div>
    <div class="stat-card amber"><div class="num">${{slow}}</div><div class="lbl">less than 1 video/yr</div></div>
  `;
}}

['filter-days','filter-avg','filter-search'].forEach(id =>
  document.getElementById(id).addEventListener('input', applyFilters));

// Sorting
let sortCol = 1, sortAsc = true;
document.querySelectorAll('th[data-col]').forEach(th => {{
  th.addEventListener('click', () => {{
    const col = parseInt(th.dataset.col);
    if (sortCol === col) sortAsc = !sortAsc; else {{ sortCol = col; sortAsc = true; }}
    document.querySelectorAll('th').forEach(t => t.classList.remove('asc','desc'));
    th.classList.add(sortAsc ? 'asc' : 'desc');
    const sorted = [...rows].sort((a, b) => {{
      const av = a.cells[col].textContent.trim();
      const bv = b.cells[col].textContent.trim();
      const an = parseFloat(av), bn = parseFloat(bv);
      const cmp = isNaN(an) || isNaN(bn) ? av.localeCompare(bv) : an - bn;
      return sortAsc ? cmp : -cmp;
    }});
    sorted.forEach(r => tbody.appendChild(r));
  }});
}});

applyFilters();
</script>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML report saved → {path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Audit your YouTube subscriptions for inactivity.")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cache and re-fetch everything")
    parser.add_argument("--output-dir", default=".", help="Directory for output files")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    service = build_service()
    cache = {} if args.no_cache else load_cache()

    # 1. Get all subscriptions
    subs = fetch_subscriptions(service)

    # 2. Batch-fetch channel details for those not (freshly) cached
    uncached_ids = [s["channel_id"] for s in subs
                    if s["channel_id"] not in cache or not cache_is_fresh(cache[s["channel_id"]])]
    print(f"Fetching details for {len(uncached_ids)} channels (others from cache)…")
    channel_details = fetch_channel_details(service, uncached_ids) if uncached_ids else {}

    # 3. Enrich each subscription
    rows = []
    for i, sub in enumerate(subs):
        entry = enrich_channel(service, sub, channel_details, cache)
        rows.append(entry)
        if (i + 1) % 20 == 0:
            print(f"  Processed {i+1}/{len(subs)}…")
            save_cache(cache)  # periodic save

    save_cache(cache)
    print("Cache saved.")

    # 4. Build DataFrame and export
    df = build_dataframe(rows)
    export_csv(df, str(out / "yt_audit.csv"))
    export_html(df, str(out / "yt_audit.html"))

    # 5. Print quick summary
    print("\n--- Quick summary (most inactive channels) ---")
    cols = ["channel_title", "days_since_last_upload", "avg_videos_per_year"]
    top = df[cols].head(15)
    print(top.to_string(index=False))
    print(f"\nOpen yt_audit.html in your browser for the full interactive report.")


if __name__ == "__main__":
    main()
