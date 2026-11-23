"""YouTube upload via the Data API (resumable upload, raw REST — no heavy SDK).

Requires secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
Create them once with scripts/make_token.py (see README).
"""
import os
from pathlib import Path

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"


class UploadError(Exception):
    pass


def _creds() -> tuple[str, str, str]:
    cid = os.environ.get("YT_CLIENT_ID", "")
    secret = os.environ.get("YT_CLIENT_SECRET", "")
    refresh = os.environ.get("YT_REFRESH_TOKEN", "")
    if not (cid and secret and refresh):
        raise UploadError(
            "YouTube secrets missing — set YT_CLIENT_ID, YT_CLIENT_SECRET, "
            "YT_REFRESH_TOKEN (see README step 4)."
        )
    return cid, secret, refresh


def refresh_access_token() -> str:
    cid, secret, refresh = _creds()
    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": cid,
            "client_secret": secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise UploadError(f"token refresh failed ({r.status_code}): {r.text[:300]}")
    return r.json()["access_token"]


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "20",
    privacy: str = "public",
    made_for_kids: bool = False,
) -> str:
    """Upload one video. Returns the new YouTube video id."""
    size = video_path.stat().st_size
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    token = refresh_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Upload-Content-Length": str(size),
        "X-Upload-Content-Type": "video/mp4",
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        json=metadata,
        headers=headers,
        timeout=120,
    )
    if r.status_code == 401:  # token expired mid-flight — one retry with fresh token
        headers["Authorization"] = f"Bearer {refresh_access_token()}"
        r = requests.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            json=metadata,
            headers=headers,
            timeout=120,
        )
    if r.status_code != 200:
        raise UploadError(f"upload init failed ({r.status_code}): {r.text[:300]}")

    session_url = r.headers["Location"]
    with open(video_path, "rb") as fh:
        up = requests.put(
            session_url,
            data=fh,
            headers={"Content-Length": str(size), "Content-Type": "video/mp4"},
            timeout=3600,
        )
    if up.status_code not in (200, 201):
        raise UploadError(f"upload failed ({up.status_code}): {up.text[:300]}")

    video_id = up.json().get("id", "")
    if not video_id:
        raise UploadError(f"upload returned no id: {up.text[:300]}")
    return video_id
