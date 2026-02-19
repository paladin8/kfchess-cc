"""Unit tests for Resend inbound email webhook endpoint."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kfchess.api.webhooks import _build_forward_html, resend_inbound_webhook


def _make_request(
    payload: dict,
    svix_id: str = "msg_123",
    svix_timestamp: str = "1700000000",
    svix_signature: str = "v1,signature",
) -> MagicMock:
    """Create a mock FastAPI Request with the given payload and headers."""
    request = MagicMock()
    body = json.dumps(payload).encode("utf-8")
    request.body = AsyncMock(return_value=body)
    request.headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }
    return request


def _make_settings(enabled: bool = True) -> MagicMock:
    """Create mock settings for webhook tests."""
    settings = MagicMock()
    settings.inbound_email_enabled = enabled
    settings.resend_webhook_secret = "whsec_testsecret" if enabled else ""
    settings.resend_api_key = "re_testkey" if enabled else ""
    settings.email_forward_to = "admin@example.com" if enabled else ""
    settings.email_from = "noreply@kfchess.com"
    settings.rate_limiting_enabled = False
    return settings


def _email_received_payload(email_id: str = "em_123", **overrides) -> dict:
    """Create an email.received webhook payload."""
    data = {
        "email_id": email_id,
        "from": "sender@example.com",
        "to": ["inbox@kfchess.com"],
        "subject": "Test Subject",
    }
    data.update(overrides)
    return {"type": "email.received", "data": data}


def _received_email_content(**overrides) -> dict:
    """Create a mock received email content response."""
    content = {
        "id": "em_123",
        "from": "sender@example.com",
        "to": ["inbox@kfchess.com"],
        "subject": "Test Subject",
        "html": "<p>Hello world</p>",
        "text": "Hello world",
    }
    content.update(overrides)
    return content


class TestResendWebhookConfiguration:
    """Tests for webhook endpoint configuration checks."""

    @pytest.mark.asyncio
    async def test_returns_404_when_not_configured(self) -> None:
        """Returns 404 when inbound email webhook is not configured."""
        settings = _make_settings(enabled=False)
        request = _make_request({"type": "email.received"})

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with pytest.raises(Exception) as exc_info:
                await resend_inbound_webhook(request)

        assert exc_info.value.status_code == 404


class TestResendWebhookSignatureVerification:
    """Tests for webhook signature verification."""

    @pytest.mark.asyncio
    async def test_returns_401_for_invalid_signature(self) -> None:
        """Returns 401 when webhook signature verification fails."""
        settings = _make_settings()
        request = _make_request({"type": "email.received"})

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch(
                "kfchess.api.webhooks.resend.Webhooks.verify",
                side_effect=ValueError("no matching signature found"),
            ):
                with pytest.raises(Exception) as exc_info:
                    await resend_inbound_webhook(request)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_passes_correct_params_to_verify(self) -> None:
        """Passes raw payload, headers, and secret to resend.Webhooks.verify."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify") as mock_verify:
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        return_value=_received_email_content()
                    )
                    with patch(
                        "kfchess.api.webhooks._send_email_async",
                        new_callable=AsyncMock,
                    ):
                        await resend_inbound_webhook(request)

        mock_verify.assert_called_once()
        call_args = mock_verify.call_args[0][0]
        assert call_args["payload"] == json.dumps(payload)
        assert call_args["headers"]["id"] == "msg_123"
        assert call_args["headers"]["timestamp"] == "1700000000"
        assert call_args["headers"]["signature"] == "v1,signature"
        assert call_args["webhook_secret"] == "whsec_testsecret"


class TestResendWebhookEventFiltering:
    """Tests for webhook event type filtering."""

    @pytest.mark.asyncio
    async def test_ignores_non_email_received_events(self) -> None:
        """Returns ignored status for non-email.received event types."""
        settings = _make_settings()
        payload = {"type": "email.sent", "data": {}}
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                result = await resend_inbound_webhook(request)

        assert result["status"] == "ignored"
        assert "email.sent" in result["reason"]

    @pytest.mark.asyncio
    async def test_ignores_domain_events(self) -> None:
        """Returns ignored status for domain events."""
        settings = _make_settings()
        payload = {"type": "domain.created", "data": {}}
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                result = await resend_inbound_webhook(request)

        assert result["status"] == "ignored"


class TestResendWebhookEmailRetrieval:
    """Tests for email content retrieval."""

    @pytest.mark.asyncio
    async def test_returns_error_when_email_id_missing(self) -> None:
        """Returns error when webhook payload has no email_id."""
        settings = _make_settings()
        payload = {"type": "email.received", "data": {"from": "test@example.com"}}
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                result = await resend_inbound_webhook(request)

        assert result["status"] == "error"
        assert "email_id" in result["reason"]

    @pytest.mark.asyncio
    async def test_returns_error_when_retrieval_fails(self) -> None:
        """Returns error when Resend API call to get email fails."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        side_effect=Exception("API error")
                    )
                    result = await resend_inbound_webhook(request)

        assert result["status"] == "error"
        assert "retrieve" in result["reason"]


class TestResendWebhookEmailForwarding:
    """Tests for email forwarding."""

    @pytest.mark.asyncio
    async def test_forwards_email_to_configured_address(self) -> None:
        """Forwards the email to EMAIL_FORWARD_TO address."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        return_value=_received_email_content()
                    )
                    with patch(
                        "kfchess.api.webhooks._send_email_async",
                        new_callable=AsyncMock,
                    ) as mock_send:
                        result = await resend_inbound_webhook(request)

        assert result["status"] == "forwarded"
        mock_send.assert_called_once()

        email_params = mock_send.call_args[0][0]
        assert email_params["to"] == "admin@example.com"
        assert email_params["from"] == "noreply@kfchess.com"

    @pytest.mark.asyncio
    async def test_subject_prefixed_with_forwarded(self) -> None:
        """Forwarded email subject is prefixed with [Forwarded]."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        return_value=_received_email_content(subject="Hello there")
                    )
                    with patch(
                        "kfchess.api.webhooks._send_email_async",
                        new_callable=AsyncMock,
                    ) as mock_send:
                        await resend_inbound_webhook(request)

        email_params = mock_send.call_args[0][0]
        assert email_params["subject"] == "[Forwarded] Hello there"

    @pytest.mark.asyncio
    async def test_forward_includes_html_body(self) -> None:
        """Forwarded email includes HTML body from original."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        return_value=_received_email_content(
                            html="<b>Important</b>", text="Important"
                        )
                    )
                    with patch(
                        "kfchess.api.webhooks._send_email_async",
                        new_callable=AsyncMock,
                    ) as mock_send:
                        await resend_inbound_webhook(request)

        html = mock_send.call_args[0][0]["html"]
        assert "<b>Important</b>" in html
        # Should prefer HTML over text
        assert "<pre>" not in html

    @pytest.mark.asyncio
    async def test_forward_falls_back_to_text_body(self) -> None:
        """Forwarded email falls back to text body when HTML is absent."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        return_value=_received_email_content(
                            html=None, text="Plain text email"
                        )
                    )
                    with patch(
                        "kfchess.api.webhooks._send_email_async",
                        new_callable=AsyncMock,
                    ) as mock_send:
                        await resend_inbound_webhook(request)

        html = mock_send.call_args[0][0]["html"]
        assert "<pre>Plain text email</pre>" in html

    @pytest.mark.asyncio
    async def test_forward_includes_sender_metadata(self) -> None:
        """Forwarded email includes From and To from original."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        return_value=_received_email_content(
                            **{"from": "alice@example.com"}
                        )
                    )
                    with patch(
                        "kfchess.api.webhooks._send_email_async",
                        new_callable=AsyncMock,
                    ) as mock_send:
                        await resend_inbound_webhook(request)

        html = mock_send.call_args[0][0]["html"]
        assert "alice@example.com" in html

    @pytest.mark.asyncio
    async def test_returns_error_when_send_fails(self) -> None:
        """Returns error when sending the forwarded email fails."""
        settings = _make_settings()
        payload = _email_received_payload()
        request = _make_request(payload)

        with patch("kfchess.api.webhooks.get_settings", return_value=settings):
            with patch("kfchess.api.webhooks.resend.Webhooks.verify"):
                with patch(
                    "kfchess.api.webhooks.asyncio.get_running_loop"
                ) as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(
                        return_value=_received_email_content()
                    )
                    with patch(
                        "kfchess.api.webhooks._send_email_async",
                        new_callable=AsyncMock,
                        side_effect=Exception("Send failed"),
                    ):
                        result = await resend_inbound_webhook(request)

        assert result["status"] == "error"
        assert "send" in result["reason"]


class TestBuildForwardHtml:
    """Tests for _build_forward_html helper."""

    def test_includes_sender(self) -> None:
        """HTML includes sender in the forwarded header."""
        html = _build_forward_html(
            sender="alice@example.com",
            subject="Hi",
            to_addresses=["inbox@kfchess.com"],
            html_body="<p>body</p>",
            text_body="body",
        )
        assert "alice@example.com" in html

    def test_includes_subject(self) -> None:
        """HTML includes subject in the forwarded header."""
        html = _build_forward_html(
            sender="a@b.com",
            subject="Important Message",
            to_addresses=[],
            html_body="<p>body</p>",
            text_body="",
        )
        assert "Important Message" in html

    def test_uses_html_body_when_present(self) -> None:
        """Uses HTML body content when available."""
        html = _build_forward_html(
            sender="a@b.com",
            subject="Hi",
            to_addresses=[],
            html_body="<strong>formatted</strong>",
            text_body="plain",
        )
        assert "<strong>formatted</strong>" in html
        assert "<pre>" not in html

    def test_wraps_text_in_pre_when_no_html(self) -> None:
        """Wraps plain text in <pre> tags when no HTML body."""
        html = _build_forward_html(
            sender="a@b.com",
            subject="Hi",
            to_addresses=[],
            html_body="",
            text_body="plain text here",
        )
        assert "<pre>plain text here</pre>" in html

    def test_handles_empty_to_addresses(self) -> None:
        """Handles empty to_addresses list."""
        html = _build_forward_html(
            sender="a@b.com",
            subject="Hi",
            to_addresses=[],
            html_body="<p>body</p>",
            text_body="",
        )
        assert "N/A" in html

    def test_joins_multiple_to_addresses(self) -> None:
        """Joins multiple to addresses with commas."""
        html = _build_forward_html(
            sender="a@b.com",
            subject="Hi",
            to_addresses=["one@test.com", "two@test.com"],
            html_body="<p>body</p>",
            text_body="",
        )
        assert "one@test.com, two@test.com" in html

    def test_escapes_html_in_metadata(self) -> None:
        """Metadata fields are HTML-escaped to prevent injection."""
        html = _build_forward_html(
            sender="<script>alert('xss')</script>",
            subject="<img onerror=alert(1)>",
            to_addresses=["<b>bold</b>@test.com"],
            html_body="<p>body</p>",
            text_body="",
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<img onerror" not in html
        assert "&lt;img onerror" in html
        assert "<b>bold</b>" not in html

    def test_escapes_html_in_text_fallback(self) -> None:
        """Text body fallback is HTML-escaped inside <pre> tags."""
        html = _build_forward_html(
            sender="a@b.com",
            subject="Hi",
            to_addresses=[],
            html_body="",
            text_body="<script>alert('xss')</script>",
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
