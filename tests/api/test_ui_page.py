from httpx import AsyncClient


async def test_ui_page_ok(client: AsyncClient) -> None:
    response = await client.get("/_ui")
    assert response.status_code == 200
