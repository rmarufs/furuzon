from httpx import AsyncClient


async def test_auth_pages_return_200_when_unauthenticated(
    client: AsyncClient,
) -> None:
    for path in (
        "/login",
        "/register",
        "/forgot-password",
        "/reset-password?token=sample-token",
        "/_ui",
    ):
        res = await client.get(path, follow_redirects=False)
        assert res.status_code == 200, path


async def test_protected_pages_redirect_to_login_when_unauthenticated(
    client: AsyncClient,
) -> None:
    for path in ("/", "/settings"):
        res = await client.get(path, follow_redirects=False)
        assert res.status_code == 302, path
        assert res.headers["location"] == "/login"


async def test_auth_pages_redirect_to_home_when_authenticated(
    client: AsyncClient,
) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "logged@example.com", "password": "password123"},
    )

    for path in (
        "/login",
        "/register",
        "/forgot-password",
        "/reset-password?token=sample-token",
    ):
        res = await client.get(path, follow_redirects=False)
        assert res.status_code == 302, path
        assert res.headers["location"] == "/"

    home_res = await client.get("/", follow_redirects=False)
    assert home_res.status_code == 200
    assert "logged@example.com" in home_res.text

    settings_res = await client.get("/settings", follow_redirects=False)
    assert settings_res.status_code == 200
    assert "logged@example.com" in settings_res.text


async def test_user_language_and_theme_from_profile_in_html(
    client: AsyncClient,
) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "tgdark@example.com", "password": "password123"},
    )
    await client.patch(
        "/api/me/preferences",
        json={"language": "tg", "theme": "dark"},
    )

    # Set conflicting cookies to ensure profile takes precedence over cookies
    client.cookies.set("lang", "ru")
    client.cookies.set("theme", "light")

    res = await client.get("/")
    assert res.status_code == 200
    assert 'lang="tg"' in res.text
    assert 'data-theme="dark"' in res.text
