from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import mailer
from app.models.user import PasswordResetToken


def _extract_token(body: str) -> str:
    for line in body.splitlines():
        if "/reset-password?token=" in line:
            parsed = urlparse(line.strip())
            return parse_qs(parsed.query)["token"][0]
    raise AssertionError("Reset token URL not found in email body")


async def test_register_and_me(client: AsyncClient) -> None:
    client.cookies.set("lang", "tg")
    client.cookies.set("theme", "dark")

    reg = await client.post(
        "/api/auth/register",
        json={"email": "Teacher@Example.com", "password": "password123"},
    )
    assert reg.status_code == 200
    data = reg.json()
    assert data["email"] == "teacher@example.com"
    assert data["language"] == "tg"
    assert data["theme"] == "dark"

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == data["id"]
    assert me.json()["email"] == "teacher@example.com"


async def test_register_duplicate_email_case_insensitive(
    client: AsyncClient,
) -> None:
    first = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/auth/register",
        json={"email": "USER@EXAMPLE.COM", "password": "password123"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "email_taken"


async def test_register_short_password(client: AsyncClient) -> None:
    res = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


async def test_me_unauthenticated(client: AsyncClient) -> None:
    res = await client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "not_authenticated"


async def test_login_and_logout(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "login@example.com", "password": "password123"},
    )

    logout_res = await client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 401

    wrong_pass = await client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "wrongpassword"},
    )
    assert wrong_pass.status_code == 401
    assert wrong_pass.json()["error"]["code"] == "invalid_credentials"

    no_user = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    assert no_user.status_code == 401
    assert no_user.json()["error"]["code"] == "invalid_credentials"

    valid = await client.post(
        "/api/auth/login",
        json={"email": "LOGIN@EXAMPLE.COM", "password": "password123"},
    )
    assert valid.status_code == 200
    assert valid.json()["email"] == "login@example.com"
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_forgot_and_reset_password_flow(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_emails: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str) -> None:
        sent_emails.append((to, subject, body))

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    await client.post(
        "/api/auth/register",
        json={"email": "reset@example.com", "password": "oldpassword1"},
    )
    await client.post("/api/auth/logout")

    missing_res = await client.post(
        "/api/auth/forgot-password",
        json={"email": "nonexistent@example.com"},
    )
    existing_res = await client.post(
        "/api/auth/forgot-password",
        json={"email": "reset@example.com"},
    )
    assert missing_res.status_code == 200
    assert existing_res.status_code == 200
    assert missing_res.json() == existing_res.json()
    assert len(sent_emails) == 1

    first_token = _extract_token(sent_emails[0][2])

    # Requesting a second reset invalidates the first token
    await client.post(
        "/api/auth/forgot-password",
        json={"email": "reset@example.com"},
    )
    assert len(sent_emails) == 2
    second_token = _extract_token(sent_emails[1][2])

    revoked_attempt = await client.post(
        "/api/auth/reset-password",
        json={"token": first_token, "new_password": "newpassword1"},
    )
    assert revoked_attempt.status_code == 400
    assert (
        revoked_attempt.json()["error"]["code"] == "invalid_or_expired_token"
    )

    reset_ok = await client.post(
        "/api/auth/reset-password",
        json={"token": second_token, "new_password": "newpassword1"},
    )
    assert reset_ok.status_code == 200

    # User is not automatically logged in after password reset
    assert (await client.get("/api/auth/me")).status_code == 401

    # Reusing the same token fails
    reuse = await client.post(
        "/api/auth/reset-password",
        json={"token": second_token, "new_password": "anotherpassword1"},
    )
    assert reuse.status_code == 400
    assert reuse.json()["error"]["code"] == "invalid_or_expired_token"

    # Old password no longer works, new password works
    old_login = await client.post(
        "/api/auth/login",
        json={"email": "reset@example.com", "password": "oldpassword1"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/auth/login",
        json={"email": "reset@example.com", "password": "newpassword1"},
    )
    assert new_login.status_code == 200


async def test_reset_password_expired_and_unknown_token(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_emails: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str) -> None:
        sent_emails.append((to, subject, body))

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    await client.post(
        "/api/auth/register",
        json={"email": "exp@example.com", "password": "oldpassword1"},
    )
    await client.post("/api/auth/logout")

    unknown = await client.post(
        "/api/auth/reset-password",
        json={"token": "unknown-token", "new_password": "newpassword1"},
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "invalid_or_expired_token"

    await client.post(
        "/api/auth/forgot-password",
        json={"email": "exp@example.com"},
    )
    token = _extract_token(sent_emails[0][2])

    await db_session.execute(
        update(PasswordResetToken).values(
            expires_at=datetime.now(UTC) - timedelta(minutes=1)
        )
    )
    await db_session.commit()

    expired = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassword1"},
    )
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "invalid_or_expired_token"


async def test_change_password_and_preferences(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "prefs@example.com", "password": "initialpass1"},
    )

    bad_change = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "wrongcurrent",
            "new_password": "updatedpass1",
        },
    )
    assert bad_change.status_code == 400
    assert bad_change.json()["error"]["code"] == "wrong_current_password"

    good_change = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "initialpass1",
            "new_password": "updatedpass1",
        },
    )
    assert good_change.status_code == 200

    prefs = await client.patch(
        "/api/me/preferences",
        json={"language": "tg", "theme": "dark"},
    )
    assert prefs.status_code == 200
    assert prefs.json()["language"] == "tg"
    assert prefs.json()["theme"] == "dark"

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["language"] == "tg"
    assert me.json()["theme"] == "dark"

    await client.post("/api/auth/logout")
    login_new = await client.post(
        "/api/auth/login",
        json={"email": "prefs@example.com", "password": "updatedpass1"},
    )
    assert login_new.status_code == 200


async def test_reset_password_token_cannot_be_reused(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_emails: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str) -> None:
        sent_emails.append((to, subject, body))

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    await client.post(
        "/api/auth/register",
        json={"email": "once@example.com", "password": "oldpassword1"},
    )
    await client.post("/api/auth/logout")

    await client.post(
        "/api/auth/forgot-password",
        json={"email": "once@example.com"},
    )
    assert len(sent_emails) == 1
    token = _extract_token(sent_emails[0][2])

    first = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassword1"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassword2"},
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_or_expired_token"


async def test_forgot_password_nonexistent_email_same_response_and_no_mail(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_emails: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str) -> None:
        sent_emails.append((to, subject, body))

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    await client.post(
        "/api/auth/register",
        json={"email": "known@example.com", "password": "password123"},
    )
    await client.post("/api/auth/logout")

    missing_res = await client.post(
        "/api/auth/forgot-password",
        json={"email": "missing@example.com"},
    )
    assert missing_res.status_code == 200
    assert sent_emails == []

    existing_res = await client.post(
        "/api/auth/forgot-password",
        json={"email": "known@example.com"},
    )
    assert existing_res.status_code == missing_res.status_code
    assert existing_res.json() == missing_res.json()
    assert len(sent_emails) == 1

