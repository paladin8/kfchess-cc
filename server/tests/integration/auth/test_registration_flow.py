"""Integration tests for user registration flow."""

import pytest
from httpx import ASGITransport, AsyncClient

from kfchess.main import app


def generate_test_email() -> str:
    """Generate a unique test email."""
    import uuid

    return f"test_{uuid.uuid4().hex[:8]}@example.com"


class TestRegistrationFlow:
    """Test the complete registration flow."""

    @pytest.mark.asyncio
    async def test_register_new_user_success(self):
        """Test successful user registration."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": generate_test_email(),
                    "password": "testpassword123",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert "email" in data
            assert data["is_active"] is True
            assert data["is_verified"] is False
            assert "id" in data
            assert "username" in data
            assert "password" not in data
            assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_generates_random_username(self):
        """Test that registration generates a random username."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": generate_test_email(),
                    "password": "testpassword123",
                },
            )

            assert response.status_code == 201
            data = response.json()
            username = data["username"]

            # Username should have format "Adjective Animal Piece Number"
            parts = username.split()
            assert len(parts) == 4
            assert parts[3].isdigit()
            assert len(parts[3]) == 5

    @pytest.mark.asyncio
    async def test_register_with_custom_username(self):
        """Test registration with a custom username."""
        import uuid

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Use unique username to avoid conflicts with previous test runs
            custom_username = f"ChessPlayer{uuid.uuid4().hex[:6]}"
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": generate_test_email(),
                    "password": "testpassword123",
                    "username": custom_username,
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["username"] == custom_username

    @pytest.mark.asyncio
    async def test_register_duplicate_email_fails(self):
        """Test that registering with existing email fails."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = generate_test_email()

            # First registration
            response1 = await client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "testpassword123",
                },
            )
            assert response1.status_code == 201

            # Second registration with same email
            response2 = await client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "differentpassword123",
                },
            )
            assert response2.status_code == 400
            data = response2.json()
            assert "REGISTER_USER_ALREADY_EXISTS" in data.get("detail", "")

    @pytest.mark.asyncio
    async def test_register_password_too_short_fails(self):
        """Test that password below minimum length is rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": generate_test_email(),
                    "password": "short",
                },
            )

            assert response.status_code == 422
            data = response.json()
            errors = data.get("detail", [])
            assert any("password" in str(e).lower() for e in errors)

    @pytest.mark.asyncio
    async def test_register_password_too_long_fails(self):
        """Test that password above maximum length is rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": generate_test_email(),
                    "password": "x" * 129,
                },
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_fails(self):
        """Test that invalid email format is rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": "not-an-email",
                    "password": "testpassword123",
                },
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_email_fails(self):
        """Test that missing email is rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "password": "testpassword123",
                },
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_password_fails(self):
        """Test that missing password is rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": generate_test_email(),
                },
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_can_login_after_registration(self):
        """Test that user can log in immediately after registration."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = generate_test_email()
            password = "testpassword123"

            # Register
            register_response = await client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": password,
                },
            )
            assert register_response.status_code == 201

            # Login (cookie-based auth returns 204 on success)
            login_response = await client.post(
                "/api/auth/login",
                data={
                    "username": email,
                    "password": password,
                },
            )
            assert login_response.status_code == 204

            # Verify cookie is set
            assert "kfchess_auth" in client.cookies

    @pytest.mark.asyncio
    async def test_can_access_me_endpoint_after_registration_and_login(self):
        """Test that user can access /users/me after registration and login."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = generate_test_email()
            password = "testpassword123"

            # Register
            await client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": password,
                },
            )

            # Login
            login_response = await client.post(
                "/api/auth/login",
                data={
                    "username": email,
                    "password": password,
                },
            )
            assert login_response.status_code == 204

            # Access /users/me
            me_response = await client.get("/api/users/me")
            assert me_response.status_code == 200
            data = me_response.json()
            assert data["email"] == email
