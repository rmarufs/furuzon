import io
from typing import Any

import openpyxl
from httpx import AsyncClient


def _make_xlsx_bytes(rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _register(
    client: AsyncClient,
    email: str = "teacher@example.com",
    password: str = "password123",
    first_name: str = "Иван",
    last_name: str = "Петров",
) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,
        },
    )
    assert resp.status_code == 200


async def test_groups_pages_redirect_to_login_when_unauthenticated(
    client: AsyncClient,
) -> None:
    for path in ("/groups", "/groups/new", "/groups/1"):
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


async def test_group_detail_page_owner_200_and_other_user_404(
    client: AsyncClient,
) -> None:
    await _register(client, email="owner@example.com")
    xlsx_data = _make_xlsx_bytes([["ФИО"], ["Иванов Иван"]])
    create_resp = await client.post(
        "/api/groups",
        files={"file": ("g.xlsx", xlsx_data)},
        data={
            "header_row": "0",
            "columns": "[0]",
            "number": "ИС-301",
            "course": "3",
        },
    )
    assert create_resp.status_code == 200
    gid = create_resp.json()["id"]

    # Owner gets 200 with detail page
    resp_owner = await client.get(f"/groups/{gid}", follow_redirects=False)
    assert resp_owner.status_code == 200
    assert "ИС-301" in resp_owner.text
    assert 'src="/static/js/pages/group_detail.js"' in resp_owner.text

    # Non-existent group returns 404 HTML page
    resp_missing = await client.get("/groups/999999", follow_redirects=False)
    assert resp_missing.status_code == 404
    assert "<!DOCTYPE html>" in resp_missing.text

    # Another teacher gets 404 HTML page for owner's group
    await _register(client, email="other@example.com")
    resp_other = await client.get(f"/groups/{gid}", follow_redirects=False)
    assert resp_other.status_code == 404
    assert "<!DOCTYPE html>" in resp_other.text
