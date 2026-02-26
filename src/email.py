from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

# Load templates once at import time
_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _load_template(name: str, **kwargs: str) -> str:
    """Load an HTML template and substitute placeholders."""
    path = _TEMPLATE_DIR / name
    if not path.exists():
        logger.warning("Email template %s not found, using plain text fallback", name)
        return kwargs.get("fallback", "")
    content = path.read_text()
    for key, value in kwargs.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an email via SMTP. Returns True on success, False on failure.

    If SMTP is not configured, logs the email content instead (dev mode).
    """
    if not settings.smtp_host:
        logger.info(
            "Email (dev mode, no SMTP configured):\n  To: %s\n  Subject: %s\n  Body: %s",
            to, subject, html_body[:200],
        )
        return True

    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["From"] = settings.from_email
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


async def send_verification_email(to: str, token: str) -> bool:
    """Send email verification link."""
    verify_url = f"{settings.base_url}/verify-email?token={token}"
    html = _load_template(
        "verify_email.html",
        verify_url=verify_url,
        fallback=f"Verify your email: {verify_url}",
    )
    return await send_email(to, "Verify your AgentGraph email", html)


async def send_password_reset_email(to: str, token: str) -> bool:
    """Send password reset link."""
    reset_url = f"{settings.base_url}/reset-password?token={token}"
    html = _load_template(
        "reset_password.html",
        reset_url=reset_url,
        fallback=f"Reset your password: {reset_url}",
    )
    return await send_email(to, "Reset your AgentGraph password", html)


async def send_welcome_email(to: str, display_name: str) -> bool:
    """Send welcome email after verification."""
    html = _load_template(
        "welcome.html",
        display_name=display_name,
        app_url=settings.base_url,
        fallback=f"Welcome to AgentGraph, {display_name}!",
    )
    return await send_email(to, "Welcome to AgentGraph!", html)
