from httpx import AsyncClient


async def _register(
    client: AsyncClient,
    email: str = "teacher@example.com",
    password: str = "password123",
) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200


async def test_groups_pages_redirect_to_login_when_unauthenticated(
    client: AsyncClient,
) -> None:
    for path in ("/groups", "/groups/new"):
        resp = await client.get(path, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"


async def test_groups_pages_return_200_when_authenticated(
    client: AsyncClient,
) -> None:
    await _register(client)

    resp_list = await client.get("/groups", follow_redirects=False)
    assert resp_list.status_code == 200
    assert 'src="/static/js/pages/groups.js"' in resp_list.text

    resp_new = await client.get("/groups/new", follow_redirects=False)
    assert resp_new.status_code == 200
    assert 'src="/static/js/pages/group_upload.js"' in resp_new.text
