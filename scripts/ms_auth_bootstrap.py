"""One-time Microsoft Graph OAuth consent flow.

Exchanges an authorization code for a refresh token. Run once per
environment; copy the printed refresh token into MS_REFRESH_TOKEN in .env.

Usage:
    MS_TENANT_ID=... MS_CLIENT_ID=... MS_CLIENT_SECRET=... \
        python scripts/ms_auth_bootstrap.py
"""
import os
import sys
import webbrowser
from urllib.parse import urlencode

import httpx


SCOPES = "Mail.Send Mail.Read offline_access"
REDIRECT_URI = "http://localhost:8910/callback"


def main() -> None:
    tenant_id = os.environ.get("MS_TENANT_ID")
    client_id = os.environ.get("MS_CLIENT_ID")
    client_secret = os.environ.get("MS_CLIENT_SECRET")
    if not (tenant_id and client_id and client_secret):
        print("MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET required.", file=sys.stderr)
        sys.exit(1)

    authorize = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?"
        + urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "response_mode": "query",
            "scope": SCOPES,
        })
    )

    print(f"\n1) Register a local redirect at {REDIRECT_URI} in Azure AD.")
    print("2) Opening browser for consent. Sign in as the shared sender account.")
    print(f"\nAuthorize URL:\n{authorize}\n")
    webbrowser.open(authorize)

    code = input("After consent, paste the `code` query param from the redirect URL: ").strip()

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = httpx.post(token_url, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "scope": SCOPES,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        print(f"No refresh_token in response: {data}", file=sys.stderr)
        sys.exit(1)

    print("\n=== SUCCESS ===")
    print("Copy this into .env as MS_REFRESH_TOKEN:\n")
    print(refresh_token)


if __name__ == "__main__":
    main()
