import json
from typing import Any

from fastapi import Depends, HTTPException, Request
from supabase import create_client

from src.settings import settings

_admin_client: Any = None


def get_admin_client():
    """Supabase client with service-role key. Lazily instantiated."""
    global _admin_client
    if _admin_client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase service-role client not configured")
        _admin_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _admin_client


def _read_supabase_token(request: Request) -> str | None:
    """Reassemble the access token from @supabase/ssr cookies.

    Cookie is named `sb-<project-ref>-auth-token`, sometimes chunked
    into `.0` / `.1`. Value is a JSON blob with an `access_token` field.
    """
    auth_cookies = {
        name: value
        for name, value in request.cookies.items()
        if name.startswith("sb-") and "auth-token" in name
    }
    if not auth_cookies:
        return None

    bases: dict[str, dict[int, str]] = {}
    singles: dict[str, str] = {}
    for name, value in auth_cookies.items():
        if "." in name and name.rsplit(".", 1)[-1].isdigit():
            base, idx = name.rsplit(".", 1)
            bases.setdefault(base, {})[int(idx)] = value
        else:
            singles[name] = value

    candidates: list[str] = []
    for base, parts in bases.items():
        candidates.append("".join(parts[i] for i in sorted(parts)))
    candidates.extend(singles.values())

    for raw in candidates:
        # Newer @supabase/ssr prefixes the value with `base64-` and stores the
        # JSON blob base64-encoded. Older versions store the JSON directly.
        if raw.startswith("base64-"):
            import base64
            payload = raw[len("base64-"):]
            # Accept both URL-safe and standard base64; pad as needed.
            padded = payload + "=" * (-len(payload) % 4)
            try:
                decoded_bytes = base64.urlsafe_b64decode(padded)
            except Exception:
                try:
                    decoded_bytes = base64.b64decode(padded)
                except Exception:
                    continue
            try:
                raw = decoded_bytes.decode("utf-8")
            except UnicodeDecodeError:
                continue
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            continue
        token = decoded.get("access_token")
        if token:
            return token
    return None


async def get_current_user(request: Request) -> dict:
    """Resolve JWT → profiles row. 401 if missing/invalid, 403 if no profile."""
    token = _read_supabase_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = get_admin_client()
    try:
        user_resp = client.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    auth_user = user_resp.user
    result = (
        client.table("profiles").select("*")
        .eq("id", auth_user.id).single().execute()
    )
    if not result.data:
        raise HTTPException(status_code=403, detail="No profile for this user")
    return result.data


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Raise 403 if the current user isn't an admin."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def is_bootstrap_admin(user: dict) -> bool:
    """True if this user's email matches the configured bootstrap admin.

    Used to gate cross-admin operations (e.g., resetting another admin's
    password). Comparison is case-insensitive.
    """
    bootstrap_email = (settings.bootstrap_admin_email or "").lower()
    if not bootstrap_email:
        return False
    return (user.get("email") or "").lower() == bootstrap_email
