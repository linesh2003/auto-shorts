"""One-time OAuth setup for the YouTube uploader (run on YOUR computer).

  pip install requests
  python scripts/make_token.py

You need a Google Cloud OAuth Client ID of type "Desktop app" first —
the README walks you through it step by step. The script:

  1. opens your browser to Google's consent screen
  2. catches the redirect on http://localhost:8765
  3. prints the YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN
     you paste into GitHub Secrets
"""
import http.server
import json
import os
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests

PORT = 8765
REDIRECT_URI = f"http://localhost:{PORT}"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

captured_code = {"code": None}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        captured_code["code"] = (query.get("code") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        ok = "<h2>✅ Got the code — you can close this tab and check the terminal.</h2>"
        bad = "<h2>❌ No code received. Check the terminal.</h2>"
        self.wfile.write((ok if captured_code["code"] else bad).encode())
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    def log_message(self, *args):  # silence request logging
        pass


def main():
    client_id = os.environ.get("YT_CLIENT_ID") or input("Client ID: ").strip()
    client_secret = os.environ.get("YT_CLIENT_SECRET") or input("Client secret: ").strip()

    url = (
        f"{AUTH_URL}?client_id={urllib.parse.quote(client_id)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&response_type=code&scope={urllib.parse.quote(SCOPE)}"
        f"&access_type=offline&prompt=consent"
    )
    print("\nOpening browser for Google login…\n"
          f"(if nothing opens, paste this into your browser:\n{url}\n)")

    global httpd
    httpd = http.server.HTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    webbrowser.open(url)
    httpd.serve_forever()

    if not captured_code["code"]:
        raise SystemExit("no authorization code captured — try again")

    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": captured_code["code"],
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise SystemExit(f"token exchange failed: {r.text}")
    tokens = r.json()
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise SystemExit(
            "no refresh_token returned — revoke the app at "
            "https://myaccount.google.com/permissions and run again "
            "(prompt=consent forces a refresh token, but Google only sends it on first consent)"
        )

    out = Path("token_youtube.json")
    out.write_text(json.dumps(tokens, indent=2))
    print("\n================ PASTE THESE AS GITHUB SECRETS ================")
    print(f"YT_CLIENT_ID      = {client_id}")
    print(f"YT_CLIENT_SECRET  = {client_secret}")
    print(f"YT_REFRESH_TOKEN  = {refresh}")
    print("===============================================================")
    print(f"(also saved locally to {out} — it is gitignored, keep it private)")


if __name__ == "__main__":
    main()
