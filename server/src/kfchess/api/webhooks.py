"""Resend webhook endpoint for inbound email forwarding.

Receives Resend's email.received webhook events, retrieves the full email
content via the Resend API, and forwards it to a configured email address.
"""

import asyncio
import html as html_lib
import json
import logging
from functools import partial
from typing import Any

import resend
from fastapi import APIRouter, Depends, HTTPException, Request

from kfchess.auth.email import _send_email_async
from kfchess.auth.rate_limit import create_rate_limit_dependency
from kfchess.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

webhook_rate_limit = create_rate_limit_dependency("30/minute", "webhook")


def _get_received_email_sync(api_key: str, email_id: str) -> dict[str, Any]:
    """Retrieve inbound email content from Resend API (synchronous).

    Called from thread pool to avoid blocking the event loop.
    """
    resend.api_key = api_key
    return dict(resend.Emails.Receiving.get(email_id))


def _build_forward_from(sender: str, email_from: str) -> str:
    """Build a 'from' address that shows the original sender.

    Since Resend requires using a verified domain, we put the original
    sender's address in the display name so it's visible in email clients.
    """
    # Strip any existing display name formatting from email_from
    # e.g. "Name <addr>" -> just use addr
    if "<" in email_from:
        email_from = email_from.split("<")[1].rstrip(">").strip()
    return f"{sender} via kfchess <{email_from}>"


def _build_body_html(html_body: str, text_body: str) -> str:
    """Build HTML body from the original email content."""
    if html_body:
        return html_body
    return f"<pre>{html_lib.escape(text_body)}</pre>"


@router.post("/resend", dependencies=[Depends(webhook_rate_limit)])
async def resend_inbound_webhook(request: Request) -> dict[str, str]:
    """Receive Resend inbound email webhook and forward to configured address."""
    settings = get_settings()

    if not settings.inbound_email_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    # Read raw body for signature verification
    payload = await request.body()
    payload_str = payload.decode("utf-8")

    # Verify webhook signature
    try:
        resend.Webhooks.verify(
            {
                "payload": payload_str,
                "headers": {
                    "id": request.headers.get("svix-id", ""),
                    "timestamp": request.headers.get("svix-timestamp", ""),
                    "signature": request.headers.get("svix-signature", ""),
                },
                "webhook_secret": settings.resend_webhook_secret,
            }
        )
    except Exception:
        logger.warning("Resend webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid webhook signature") from None

    # Parse event
    try:
        event = json.loads(payload_str)
    except json.JSONDecodeError:
        logger.warning("Resend webhook payload is not valid JSON")
        return {"status": "error", "reason": "invalid payload"}
    event_type = event.get("type", "")

    if event_type != "email.received":
        logger.debug("Ignoring webhook event type: %s", event_type)
        return {"status": "ignored", "reason": f"unhandled event type: {event_type}"}

    # Extract email_id from event data
    data = event.get("data", {})
    email_id = data.get("email_id")

    if not email_id:
        logger.warning("Resend webhook missing email_id in data")
        return {"status": "error", "reason": "missing email_id"}

    # Retrieve full email content from Resend API
    try:
        loop = asyncio.get_running_loop()
        email_content = await loop.run_in_executor(
            None,
            partial(_get_received_email_sync, settings.resend_api_key, email_id),
        )
    except Exception:
        logger.exception("Failed to retrieve email %s from Resend API", email_id)
        return {"status": "error", "reason": "failed to retrieve email content"}

    sender = email_content.get("from", data.get("from", "unknown"))
    subject = email_content.get("subject", data.get("subject", "(no subject)"))
    html_body = email_content.get("html") or ""
    text_body = email_content.get("text") or ""

    # Build and send forwarded email
    forward_from = _build_forward_from(sender, settings.email_from)
    body_html = _build_body_html(html_body, text_body)

    try:
        await _send_email_async(
            {
                "from": forward_from,
                "to": settings.email_forward_to,
                "reply_to": sender,
                "subject": subject,
                "html": body_html,
            }
        )
        logger.info("Forwarded inbound email from %s (subject: %s)", sender, subject)
    except Exception:
        logger.exception("Failed to forward inbound email from %s", sender)
        return {"status": "error", "reason": "failed to send forwarded email"}

    return {"status": "forwarded"}
