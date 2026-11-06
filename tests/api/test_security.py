import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings
from app.main import create_app
from app.services.excel.reader import MAX_RAW_SCAN_COLUMNS, _read_xls


def test_prod_env_rejects_default_or_short_secret_key_and_insecure_cookie() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            ENV="prod",
            SECRET_KEY=DEFAULT_SECRET_KEY,
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            ENV="prod",
            SECRET_KEY="short-secret-key",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(
            ENV="prod",
            SECRET_KEY="s" * 32,
            COOKIE_SECURE=False,
        )

    valid = Settings(
        ENV="prod",
        SECRET_KEY="s" * 32,
        COOKIE_SECURE=True,
    )
    assert valid.ENV == "prod"


@pytest.mark.asyncio
async def test_docs_and_ui_return_404_in_prod() -> None:
    prod_settings = Settings(
        ENV="prod",
        SECRET_KEY="p" * 32,
        COOKIE_SECURE=True,
    )
    prod_app = create_app(prod_settings)
    transport = ASGITransport(app=prod_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for path in ("/docs", "/redoc", "/openapi.json", "/_ui"):
            resp = await ac.get(path)
            assert resp.status_code == 404, f"Expected 404 for {path} in prod"


@pytest.mark.asyncio
async def test_security_headers_present_on_responses(client: AsyncClient) -> None:
    for path in ("/login", "/api/auth/me"):
        resp = await client.get(path)
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert (
            resp.headers.get("Referrer-Policy")
            == "strict-origin-when-cross-origin"
        )


@pytest.mark.asyncio
async def test_csrf_blocks_foreign_origin_and_allows_missing_or_same_origin(
    client: AsyncClient,
) -> None:
    payload = {
        "first_name": "Иван",
        "last_name": "Иванов",
        "email": "csrf@example.com",
        "password": "password123",
    }

    # Foreign Origin -> 403
    foreign_resp = await client.post(
        "/api/auth/register",
        json=payload,
        headers={"Origin": "https://evil.example.com"},
    )
    assert foreign_resp.status_code == 403
    assert foreign_resp.json()["error"]["code"] == "csrf_failed"
    assert foreign_resp.headers.get("X-Frame-Options") == "DENY"

    # Without Origin -> 200
    no_origin_resp = await client.post("/api/auth/register", json=payload)
    assert no_origin_resp.status_code == 200

    # Same Origin -> 200
    same_origin_resp = await client.patch(
        "/api/me/profile",
        json={"first_name": "Пётр", "last_name": "Петров"},
        headers={"Origin": "http://test"},
    )
    assert same_origin_resp.status_code == 200


@pytest.mark.asyncio
async def test_login_rate_limit_and_reset_on_success(
    client: AsyncClient,
) -> None:
    email = "ratelimit@example.com"
    await client.post(
        "/api/auth/register",
        json={
            "first_name": "Анна",
            "last_name": "Смирнова",
            "email": email,
            "password": "correct-password",
        },
    )
    await client.post("/api/auth/logout")

    # 9 failed attempts, then 1 successful login resets the pair counter
    for _ in range(9):
        r = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
        assert r.status_code == 401

    ok_resp = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "correct-password"},
    )
    assert ok_resp.status_code == 200
    await client.post("/api/auth/logout")

    # Now 10 failed attempts hit the pair limit on the 11th attempt
    for _ in range(10):
        r = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
        assert r.status_code == 401

    limited = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrong-password"},
        headers={"Cookie": "lang=ru"},
    )
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    assert int(limited.headers["Retry-After"]) >= 1
    body = limited.json()
    assert body["error"]["code"] == "too_many_requests"
    assert "Слишком много попыток" in body["error"]["details"]["message"]


def test_read_xls_rejects_excessive_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSheet:
        nrows = 1
        ncols = MAX_RAW_SCAN_COLUMNS + 1

    class FakeWorkbook:
        datemode = 0

        def sheets(self) -> list[FakeSheet]:
            return [FakeSheet()]

    import xlrd

    monkeypatch.setattr(xlrd, "open_workbook", lambda **_: FakeWorkbook())
    from app.core.exceptions import AppError

    with pytest.raises(AppError) as exc_info:
        _read_xls(b"dummy")
    assert exc_info.value.code == "excel_too_large"
    assert exc_info.value.status_code == 422
