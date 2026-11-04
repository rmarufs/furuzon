from pathlib import Path

import aiofiles
import aiofiles.os

from app.storage.base import Storage


class LocalStorage(Storage):
    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir).resolve()

    def _resolve_path(self, key: str) -> Path:
        clean_key = key.strip().lstrip("/\\")
        if not clean_key or ".." in Path(clean_key).parts:
            raise ValueError(f"Invalid storage key: {key!r}")
        target = (self._base_dir / clean_key).resolve()
        if self._base_dir not in target.parents:
            raise ValueError(f"Invalid storage key path: {key!r}")
        return target

    async def save(self, key: str, data: bytes, content_type: str) -> None:
        del content_type
        target = self._resolve_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "wb") as fh:
            await fh.write(data)

    async def read(self, key: str) -> bytes:
        target = self._resolve_path(key)
        if not target.is_file():
            raise FileNotFoundError(key)
        async with aiofiles.open(target, "rb") as fh:
            return await fh.read()

    async def delete(self, key: str) -> None:
        target = self._resolve_path(key)
        try:
            await aiofiles.os.remove(target)
        except FileNotFoundError:
            pass

    async def exists(self, key: str) -> bool:
        target = self._resolve_path(key)
        return target.is_file()
