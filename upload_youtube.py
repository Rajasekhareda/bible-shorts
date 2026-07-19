#!/usr/bin/env python3
"""
upload_youtube.py
------------------
Uploads today's rendered short (output/<date>.mp4 + matching .meta.json)
to YouTube as a public video tagged #Shorts.

Required environment variables (set as GitHub Actions secrets):
  YT_CLIENT_ID
  YT_CLIENT_SECRET
  YT_REFRESH_TOKEN

Exits non-zero on any failure so the workflow shows a clear red X and
(with GitHub's default notification settings) emails you.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def get_credentials() -> Credentials:
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")
    missing = [n for n, v in [
        ("YT_CLIENT_ID", client_id),
        ("YT_CLIENT_SECRET", client_secret),
        ("YT_REFRESH_TOKEN", refresh_token),
    ] if not v]
    if missing:
        fail(f"Missing required secrets/env vars: {', '.join(missing)}")

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )


def find_today_files():
    today_str = date.today().isoformat()
    video_path = OUTPUT_DIR / f"{today_str}.mp4"
    meta_path = OUTPUT_DIR / f"{today_str}.meta.json"
    if not video_path.exists():
        fail(f"No video found at {video_path}. Did generate_video.py run first?")
    if not meta_path.exists():
        fail(f"No metadata found at {meta_path}.")
    return video_path, meta_path


def upload(video_path: Path, meta: dict) -> str:
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta.get("tags", []),
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

    try:
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload progress: {int(status.progress() * 100)}%")
    except HttpError as e:
        fail(f"YouTube API upload failed: {e}")

    video_id = response["id"]
    print(f"Uploaded: https://youtube.com/shorts/{video_id}")
    return video_id


def main():
    video_path, meta_path = find_today_files()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    upload(video_path, meta)


if __name__ == "__main__":
    main()
