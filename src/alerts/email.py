"""Email alerts via IMAP polling (stub implementation)."""

import asyncio
from src.db.store import AegisStore


async def poll_email_commands(store: AegisStore, poll_interval: int = 60) -> None:
    """Poll IMAP inbox for command replies (stub).

    In production: connects to IMAP, parses subjects, executes commands.
    For hackathon: stub that does nothing.

    Args:
        store: Database store for command logging
        poll_interval: Seconds between polls
    """
    # Stub: not implemented for hackathon
    print(f"Email polling stub — would poll every {poll_interval}s")


async def send_alert(subject: str, body: str) -> None:
    """Send email alert (stub).

    For hackathon: just logs the alert.
    """
    print(f"EMAIL ALERT: {subject}")
    print(f"  {body[:100]}...")
