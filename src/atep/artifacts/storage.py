import hashlib
import os
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import anyio


class ObjectTooLargeError(Exception):
    """Raised before an object exceeding the configured bound is retained."""


class ObjectNotAvailableError(Exception):
    """Raised when metadata exists but its object cannot be read."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str


class ArtifactObjectStore(Protocol):
    async def ensure_ready(self) -> None: ...

    async def put(
        self, key: str, content: AsyncIterable[bytes], *, max_bytes: int
    ) -> StoredObject: ...

    def stream(self, key: str) -> AsyncIterator[bytes]: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> None: ...


class FilesystemArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def ensure_ready(self) -> None:
        await anyio.to_thread.run_sync(lambda: self.root.mkdir(parents=True, exist_ok=True))

    async def put(self, key: str, content: AsyncIterable[bytes], *, max_bytes: int) -> StoredObject:
        target = self._path(key)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.upload")
        await anyio.to_thread.run_sync(lambda: target.parent.mkdir(parents=True, exist_ok=True))
        digest = hashlib.sha256()
        size = 0
        try:
            async with await anyio.open_file(temporary, "xb") as output:
                async for chunk in content:
                    size += len(chunk)
                    if size > max_bytes:
                        raise ObjectTooLargeError
                    digest.update(chunk)
                    await output.write(chunk)
            await anyio.to_thread.run_sync(os.replace, temporary, target)
        except BaseException:
            await anyio.to_thread.run_sync(temporary.unlink, True)
            raise
        return StoredObject(key=key, size_bytes=size, sha256=digest.hexdigest())

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        try:
            async with await anyio.open_file(path, "rb") as source:
                while chunk := await source.read(64 * 1024):
                    yield chunk
        except FileNotFoundError as exc:
            raise ObjectNotAvailableError from exc

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await anyio.to_thread.run_sync(path.unlink, True)

    async def exists(self, key: str) -> bool:
        path = self._path(key)
        return await anyio.to_thread.run_sync(path.is_file)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("object key escapes the configured storage root")
        return candidate
