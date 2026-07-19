#!/usr/bin/env python3
"""
get_refresh_token.py
---------------------
RUN THIS ONCE, ON YOUR OWN COMPUTER (not in GitHub Actions).

It opens a browser, asks you to log into the Google account that owns your
YouTube channel, and prints a refresh token. Save that refresh token (plus
your client id/secret) as GitHub repo secrets - the automated workflow uses
them to upload videos without you ever logging in again.

Prerequisites:
  pip install google-auth-oauthlib google-auth
  A "client_secret.json" downloaded from Google Cloud Console
  (APIs & Services > Credentials > OAuth client ID > Desktop app > Download JSON)
  placed next to this script.
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n\n=== SAVE THESE AS GITHUB SECRETS ===")
    print(f"YT_CLIENT_ID={creds.client_id}")
    print(f"YT_CLIENT_SECRET={creds.client_secret}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    print("=====================================\n")

if __name__ == "__main__":
    main()
