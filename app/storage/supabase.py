from urllib.parse import quote

import httpx

from app.storage.base import Storage


class SupabaseStorage(Storage):
    def __init__(
        self,
        *,
        url: str,
        service_key: str,
        bucket: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = url.rstrip("/")
        self._service_key = service_key
        self._bucket = bucket.strip("/")
        self._timeout = timeout

    def _object_url(self, key: str) -> str:
        safe_key = quote(key.lstrip("/"), safe="/")
        return f"{self._base_url}/storage/v1/object/{self._bucket}/{safe_key}"

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._service_key}",
            "apikey": self._service_key,
        }

    async def save(self, key: str, data: bytes, content_type: str) -> None:
        headers = {
            **self._auth_headers(),
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._object_url(key),
                content=data,
                headers=headers,
            )
            resp.raise_for_status()

    async def read(self, key: str) -> bytes:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                self._object_url(key),
                headers=self._auth_headers(),
            )
            if resp.status_code in (400, 404):
                raise FileNotFoundError(key)
            resp.raise_for_status()
            return resp.content

    async def delete(self, key: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.delete(
                self._object_url(key),
                headers=self._auth_headers(),
            )
            if resp.status_code in (400, 404):
                return
            resp.raise_for_status()

    async def exists(self, key: str) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                self._object_url(key),
                headers=self._auth_headers(),
            )
            if resp.status_code == 200:
                return True
            if resp.status_code in (400, 404):
                return False
            resp.raise_for_status()
            return False
