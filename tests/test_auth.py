"""
Portfolio Health Monitor – Authentication API Integration Tests
Tests for:
1. User Registration (valid, duplicate, validation failures)
2. OAuth2 Password Form Login (POST /api/v1/auth/token)
3. JSON Payload Login (POST /api/v1/auth/login)
4. Authenticated Profile Retrieval (GET /api/v1/auth/me)
5. Security Rejections (wrong password, non-existent user, deactivated account, invalid token)
"""

import asyncio
import uuid

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.user import User


@pytest.fixture(autouse=True)
def dispose_db_pool():
    """Ensure engine pool connections do not bleed across async test event loops."""
    yield
    asyncio.run(engine.dispose())


@pytest.mark.anyio
async def test_user_registration_success():
    """Verify new user registration via POST /api/v1/auth/register."""
    unique_email = f"newuser_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "email": unique_email,
        "password": "SecurePassword123!",
        "full_name": "New Alpha Trader",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == unique_email.lower()
        assert data["full_name"] == "New Alpha Trader"
        assert data["is_active"] is True
        assert "id" in data
        assert "hashed_password" not in data


@pytest.mark.anyio
async def test_user_registration_duplicate_email_conflict():
    """Verify duplicate email registration is rejected with 409 Conflict."""
    email = f"dup_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Original User",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # First registration succeeds
        res1 = await client.post("/api/v1/auth/register", json=payload)
        assert res1.status_code == 201

        # Second registration with same email fails with 409
        res2 = await client.post("/api/v1/auth/register", json=payload)
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]


@pytest.mark.anyio
async def test_user_registration_validation_errors():
    """Verify input validation rejects invalid emails and weak passwords."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Invalid email
        res_email = await client.post(
            "/api/v1/auth/register",
            json={"email": "invalid-email", "password": "ValidPassword123!"},
        )
        assert res_email.status_code == 422

        # 2. Short password (< 8 chars)
        res_pwd = await client.post(
            "/api/v1/auth/register",
            json={"email": "valid@example.com", "password": "short"},
        )
        assert res_pwd.status_code == 422


@pytest.mark.anyio
async def test_oauth2_form_login_success_and_failure():
    """Verify OAuth2 password flow login via POST /api/v1/auth/token."""
    email = f"oauth_{uuid.uuid4().hex[:6]}@example.com"
    password = "CorrectPassword123!"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Register user
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "OAuth User"},
        )
        assert reg_res.status_code == 201

        # 2. Login with form data (username=email, password=password)
        login_res = await client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": password},
        )
        assert login_res.status_code == 200
        data = login_res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

        # 3. Login with incorrect password fails with 401
        bad_pwd_res = await client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": "WrongPassword!"},
        )
        assert bad_pwd_res.status_code == 401
        assert "Incorrect email or password" in bad_pwd_res.json()["detail"]

        # 4. Login with non-existent email fails with 401
        no_user_res = await client.post(
            "/api/v1/auth/token",
            data={"username": "nonexistent@example.com", "password": password},
        )
        assert no_user_res.status_code == 401


@pytest.mark.anyio
async def test_json_login_success_and_failure():
    """Verify JSON body login via POST /api/v1/auth/login."""
    email = f"jsonuser_{uuid.uuid4().hex[:6]}@example.com"
    password = "JsonLoginPass123!"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "JSON User"},
        )

        # Successful JSON login
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert res.status_code == 200
        assert "access_token" in res.json()

        # Failed JSON login
        res_fail = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword"},
        )
        assert res_fail.status_code == 401


@pytest.mark.anyio
async def test_authenticated_profile_retrieval_me():
    """Verify GET /api/v1/auth/me returns authenticated user's profile."""
    email = f"profile_{uuid.uuid4().hex[:6]}@example.com"
    password = "ProfilePassword123!"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Register and login
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Profile Owner"},
        )
        token_res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        token = token_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Fetch own profile
        me_res = await client.get("/api/v1/auth/me", headers=headers)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == email.lower()
        assert me_data["full_name"] == "Profile Owner"
        assert me_data["is_active"] is True

        # 2. Reject with invalid/tampered token
        bad_token_headers = {"Authorization": "Bearer invalid.fake.token"}
        bad_res = await client.get("/api/v1/auth/me", headers=bad_token_headers)
        assert bad_res.status_code == 401


@pytest.mark.anyio
async def test_deactivated_user_login_blocked():
    """Verify deactivated user is prohibited from logging in."""
    email = f"deactive_{uuid.uuid4().hex[:6]}@example.com"
    password = "ValidPassword123!"

    async with AsyncSessionLocal() as session:
        # Directly insert deactivated user
        from app.core.security import get_password_hash
        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Deactivated User",
            is_active=False,
        )
        session.add(user)
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Attempt login via /token
        res_token = await client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": password},
        )
        assert res_token.status_code == 403
        assert "deactivated" in res_token.json()["detail"].lower()

        # Attempt login via /login
        res_json = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert res_json.status_code == 403

