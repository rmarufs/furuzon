from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


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
        json={
            "first_name": "Фарход",
            "last_name": "Назаров",
            "email": "logged@example.com",
            "password": "password123",
        },
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
    assert "Фарход Назаров" in home_res.text
    assert "logged@example.com" in home_res.text
    assert "Добро пожаловать в личный кабинет преподавателя" in home_res.text
    assert "Создать первую группу" in home_res.text
    assert 'href="/groups/new"' in home_res.text

    bottom_nav_start = home_res.text.index('class="bottom-nav"')
    bottom_nav_end = home_res.text.index("</nav>", bottom_nav_start)
    bottom_nav_html = home_res.text[bottom_nav_start:bottom_nav_end]
    pos_materials = bottom_nav_html.index('href="/materials"')
    pos_groups = bottom_nav_html.index('href="/groups"')
    assert pos_materials < pos_groups
    assert 'href="/sheets"' not in home_res.text

    not_found_res = await client.get("/sheets", follow_redirects=False)
    assert not_found_res.status_code == 404

    settings_res = await client.get("/settings", follow_redirects=False)
    assert settings_res.status_code == 200
    assert "Фарход Назаров" in settings_res.text
    assert 'value="Фарход"' in settings_res.text
    assert 'value="Назаров"' in settings_res.text
    assert "logged@example.com" in settings_res.text


async def test_user_language_and_theme_from_profile_in_html(
    client: AsyncClient,
) -> None:
    await client.post(
        "/api/auth/register",
        json={
            "first_name": "Иван",
            "last_name": "Петров",
            "email": "tgdark@example.com",
            "password": "password123",
        },
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


async def test_groups_page_profile_menu_with_and_without_names(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    reg = await client.post(
        "/api/auth/register",
        json={
            "first_name": "Саида",
            "last_name": "Юсупова",
            "email": "saida@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200

    res = await client.get("/groups", follow_redirects=False)
    assert res.status_code == 200
    assert "Саида Юсупова" in res.text
    assert '<span class="profile-btn__avatar" aria-hidden="true">СЮ</span>' in res.text
    assert '<span class="profile-btn__name">Саида Юсупова</span>' in res.text

    # Simulate legacy user without first_name and last_name
    await db_session.execute(
        update(User)
        .where(User.email == "saida@example.com")
        .values(first_name="", last_name="")
    )
    await db_session.commit()

    res_no_name = await client.get("/groups", follow_redirects=False)
    assert res_no_name.status_code == 200
    assert (
        '<span class="profile-btn__name">saida@example.com</span>'
        in res_no_name.text
    )
    assert (
        '<span class="profile-btn__avatar" aria-hidden="true">S</span>'
        in res_no_name.text
    )
