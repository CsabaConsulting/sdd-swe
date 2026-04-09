"""Email alerts via IMAP polling implementation."""

import asyncio
import imaplib
import email
import smtplib
from email.mime.text import MIMEText
from email.header import decode_header
from typing import Optional
from src.db.store import AegisStore
from src.config.loader import AegisConfig
from src.cli.commands import execute_command


def _parse_message_id(msg: email.message.Message) -> Optional[str]:
    """Extract Message-ID header for idempotency tracking."""
    msg_id = msg.get("Message-ID")
    if msg_id:
        return msg_id.strip("<>")
    return None


def _parse_subject(msg: email.message.Message) -> str:
    """Parse subject line from email message."""
    subject = msg.get("Subject", "")
    if not subject:
        return ""

    # Decode if encoded
    decoded_parts = decode_header(subject)
    subject_parts = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            subject_parts.append(part.decode(charset or "utf-8"))
        else:
            subject_parts.append(part)

    return "".join(subject_parts).strip()


def _get_body(msg: email.message.Message) -> str:
    """Extract text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
                except:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except:
            pass
    return ""


def _parse_command_from_subject(subject: str) -> Optional[str]:
    """Extract command from email subject line.

    Looks for patterns like:
    - "Aegis: /approve skill-name"
    - "Aegis Alert: /halt task-id"
    - "/command args"
    """
    if not subject:
        return None

    # Look for slash commands in subject
    import re
    match = re.search(r'/(\w+)\s*(.*)', subject, re.IGNORECASE)
    if match:
        cmd = match.group(1)
        args = match.group(2).strip()
        return f"/{cmd} {args}".strip()

    return None


async def poll_email_commands(store: AegisStore, config: AegisConfig) -> None:
    """Poll IMAP inbox for command replies.

    Connects to IMAP, checks for unread messages, parses commands from
    subject lines, executes them idempotently.

    Args:
        store: Database store for command logging
        config: Application config with IMAP credentials
    """
    try:
        # Connect to IMAP
        loop = asyncio.get_event_loop()
        client = await loop.run_in_executor(
            None,
            lambda: _connect_imap(config)
        )

        if not client:
            return

        # Search for unread messages
        status, messages = await loop.run_in_executor(
            None,
            lambda: client.search(None, "UNSEEN")
        )

        if status != "OK" or not messages[0]:
            client.logout()
            return

        for msg_id in messages[0].split():
            await _process_email_message(msg_id, client, store, config)

        client.logout()

    except Exception as e:
        print(f"IMAP polling error: {e}")


def _connect_imap(config: AegisConfig) -> Optional[imaplib.IMAP4_SSL]:
    """Connect and login to IMAP server (sync, runs in executor)."""
    try:
        client = imaplib.IMAP4_SSL(config.imap_host)
        client.login(config.imap_user, config.imap_pass)
        client.select("INBOX")
        return client
    except Exception as e:
        print(f"IMAP connection error: {e}")
        return None


async def _process_email_message(msg_id: bytes, client, store: AegisStore, config: AegisConfig) -> None:
    """Process a single email message."""
    loop = asyncio.get_event_loop()

    # Fetch message
    status, msg_data = await loop.run_in_executor(
        None,
        lambda: client.fetch(msg_id, "(RFC822)")
    )

    if status != "OK":
        return

    # Parse message
    msg = email.message_from_bytes(msg_data[0][1])

    # Extract message ID for idempotency
    message_id = _parse_message_id(msg)
    if not message_id:
        return

    # Check if already processed
    if await store.command_exists(message_id):
        return

    # Parse subject for command
    subject = _parse_subject(msg)
    command = _parse_command_from_subject(subject)

    if not command:
        # Mark as read anyway
        await loop.run_in_executor(
            None,
            lambda: client.store(msg_id, "+FLAGS", "\\Seen")
        )
        return

    # Execute command (stub store for now — would pass real store)
    # For autonomous mode, commands are logged but not executed inline
    result = f"Email command received: {command}"

    # Log to command_log
    await store.log_command(command, source="email", email_message_id=message_id, result=result)

    # Mark as read
    await loop.run_in_executor(
        None,
        lambda: client.store(msg_id, "+FLAGS", "\\Seen")
    )

    print(f"Processed email command: {command}")


async def send_alert(config: AegisConfig, subject: str, body: str, to_addr: str = None) -> None:
    """Send email alert via SMTP.

    Uses same credentials as IMAP (Gmail app password works for SMTP).

    Args:
        config: Application config
        subject: Email subject
        body: Email body text
        to_addr: Recipient (defaults to IMAP user)
    """
    to_addr = to_addr or config.imap_user

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.imap_user
    msg["To"] = to_addr

    try:
        # Determine SMTP server from IMAP host
        smtp_host = config.imap_host.replace("imap.", "smtp.")
        server = smtplib.SMTP_SSL(smtp_host, 465)
        server.login(config.imap_user, config.imap_pass)
        server.sendmail(config.imap_user, [to_addr], msg.as_string())
        server.quit()
        print(f"Alert sent: {subject}")
    except Exception as e:
        print(f"SMTP error: {e}")
