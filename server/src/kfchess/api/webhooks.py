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


def _build_forward_html(
    sender: str,
    subject: str,
    to_addresses: list[str],
    html_body: str,
    text_body: str,
) -> str:
    """Build HTML for the forwarded email with original metadata header."""
    # html_body is already HTML and rendered as-is; text_body needs escaping
    body_content = html_body if html_body else f"<pre>{html_lib.escape(text_body)}</pre>"
    to_display = ", ".join(to_addresses) if to_addresses else "N/A"

    # Escape metadata fields to prevent HTML injection
    sender_escaped = html_lib.escape(sender)
    subject_escaped = html_lib.escape(subject)
    to_escaped = html_lib.escape(to_display)

    return (
        '<div style="border-bottom: 1px solid #ccc; padding-bottom: 10px; '
        'margin-bottom: 10px;">'
        "<p><strong>Forwarded inbound email</strong></p>"
        f"<p><strong>From:</strong> {sender_escaped}</p>"
        f"<p><strong>To:</strong> {to_escaped}</p>"
        f"<p><strong>Subject:</strong> {subject_escaped}</p>"
        "</div>"
        f"<div>{body_content}</div>"
    )


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
    to_addresses = email_content.get("to", data.get("to", []))
    html_body = email_content.get("html") or ""
    text_body = email_content.get("text") or ""

    # Build and send forwarded email
    forward_html = _build_forward_html(
        sender=sender,
        subject=subject,
        to_addresses=to_addresses,
        html_body=html_body,
        text_body=text_body,
    )

    try:
        await _send_email_async(
            {
                "from": settings.email_from,
                "to": settings.email_forward_to,
                "subject": f"[Forwarded] {subject}",
                "html": forward_html,
            }
        )
        logger.info("Forwarded inbound email from %s (subject: %s)", sender, subject)
    except Exception:
        logger.exception("Failed to forward inbound email from %s", sender)
        return {"status": "error", "reason": "failed to send forwarded email"}

    return {"status": "forwarded"}
