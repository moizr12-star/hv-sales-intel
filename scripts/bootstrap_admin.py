"""Manually seed the initial admin. Run when the startup hook didn't catch it.

Usage:
    BOOTSTRAP_ADMIN_EMAIL=... BOOTSTRAP_ADMIN_PASSWORD=... python scripts/bootstrap_admin.py
"""
import asyncio

from api.index import bootstrap_admin_on_startup


if __name__ == "__main__":
    asyncio.run(bootstrap_admin_on_startup())
