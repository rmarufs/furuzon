from abc import ABC, abstractmethod


class Storage(ABC):
    @abstractmethod
    async def save(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def read(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        raise NotImplementedError
