import asyncio
import time

import httpx

from src.settings import settings


_cached_token: str | None = None
_cached_expires_at: float = 0.0
_lock = asyncio.Lock()


async def get_access_token() -> str:
    """Return a fresh Microsoft Graph access token. Cached across calls.

    Exchanges the refresh token when no valid token is cached or when the
    cached token expires in < 60 seconds.
    """
    global _cached_token, _cached_expires_at

    if _cached_token and time.time() < _cached_expires_at - 60:
        return _cached_token

    if not (
        settings.ms_tenant_id
        and settings.ms_client_id
        and settings.ms_client_secret
        and settings.ms_refresh_token
    ):
        raise RuntimeError("Microsoft Graph not configured")

    async with _lock:
        if _cached_token and time.time() < _cached_expires_at - 60:
            return _cached_token

        url = f"https://login.microsoftonline.com/{settings.ms_tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": settings.ms_client_id,
            "client_secret": settings.ms_client_secret,
            "refresh_token": settings.ms_refresh_token,
            "grant_type": "refresh_token",
            "scope": "Mail.Send Mail.Read offline_access",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
        payload = resp.json()

        _cached_token = payload["access_token"]
        _cached_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return _cached_token
