import asyncio

import httpx

from src.settings import settings


_cached_access_token: str | None = None
_cached_instance_url: str | None = None
_lock = asyncio.Lock()


def is_configured() -> bool:
    """True if all 5 required SF_* env vars are non-empty."""
    return bool(
        settings.sf_client_id
        and settings.sf_client_secret
        and settings.sf_username
        and settings.sf_password
        and settings.sf_security_token
    )


def invalidate_token() -> None:
    """Clear the in-process cache. Call on 401 before retrying."""
    global _cached_access_token, _cached_instance_url
    _cached_access_token = None
    _cached_instance_url = None


async def get_access_token() -> tuple[str, str]:
    """Return (access_token, instance_url). Cached until invalidated.

    Exchanges username+password+security_token via Salesforce OAuth 2.0
    username-password flow. SF does not return expires_in for this flow,
    so we cache indefinitely and rely on callers to invalidate on 401.
    """
    global _cached_access_token, _cached_instance_url

    if _cached_access_token and _cached_instance_url:
        return _cached_access_token, _cached_instance_url

    if not is_configured():
        raise RuntimeError("Salesforce not configured")

    async with _lock:
        if _cached_access_token and _cached_instance_url:
            return _cached_access_token, _cached_instance_url

        url = f"{settings.sf_login_url}/services/oauth2/token"
        data = {
            "grant_type": "password",
            "client_id": settings.sf_client_id,
            "client_secret": settings.sf_client_secret,
            "username": settings.sf_username,
            "password": settings.sf_password + settings.sf_security_token,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
        payload = resp.json()

        _cached_access_token = payload["access_token"]
        _cached_instance_url = payload["instance_url"]
        return _cached_access_token, _cached_instance_url
