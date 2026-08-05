import hashlib
import os
import shutil
import time
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import anyio
import structlog

from atep.core.observability import Observability

log = structlog.get_logger()


class ObjectTooLargeError(Exception):
    """Raised before an object exceeding the configured bound is retained."""


class ObjectNotAvailableError(Exception):
    """Raised when metadata exists but its object cannot be read."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ArtifactStoreCapacity:
    total_bytes: int
    free_bytes: int


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

    async def capacity(self) -> ArtifactStoreCapacity:
        usage = await anyio.to_thread.run_sync(shutil.disk_usage, self.root)
        return ArtifactStoreCapacity(total_bytes=usage.total, free_bytes=usage.free)

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


class InstrumentedArtifactStore:
    def __init__(
        self,
        store: ArtifactObjectStore,
        observability: Observability,
        *,
        capacity_provider: Callable[[], Awaitable[ArtifactStoreCapacity]] | None = None,
    ) -> None:
        self.store = store
        self.observability = observability
        self.capacity_provider = capacity_provider

    async def ensure_ready(self) -> None:
        started_at = time.perf_counter()
        try:
            await self.store.ensure_ready()
        except BaseException:
            self._observe("ready", "error", started_at)
            raise
        self._observe("ready", "success", started_at)
        await self._refresh_capacity()

    async def put(self, key: str, content: AsyncIterable[bytes], *, max_bytes: int) -> StoredObject:
        started_at = time.perf_counter()
        try:
            stored = await self.store.put(key, content, max_bytes=max_bytes)
        except (ObjectTooLargeError, ValueError):
            self._observe("put", "rejected", started_at)
            raise
        except BaseException:
            self._observe("put", "error", started_at)
            raise
        self._observe("put", "success", started_at, bytes_transferred=stored.size_bytes)
        await self._refresh_capacity()
        return stored

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        started_at = time.perf_counter()
        bytes_transferred = 0
        outcome = "error"
        try:
            async for chunk in self.store.stream(key):
                bytes_transferred += len(chunk)
                yield chunk
            outcome = "success"
        finally:
            self._observe(
                "stream",
                outcome,
                started_at,
                bytes_transferred=bytes_transferred,
            )

    async def exists(self, key: str) -> bool:
        started_at = time.perf_counter()
        try:
            exists = await self.store.exists(key)
        except BaseException:
            self._observe("exists", "error", started_at)
            raise
        self._observe("exists", "success", started_at)
        return exists

    async def delete(self, key: str) -> None:
        started_at = time.perf_counter()
        try:
            await self.store.delete(key)
        except BaseException:
            self._observe("delete", "error", started_at)
            raise
        self._observe("delete", "success", started_at)
        await self._refresh_capacity()

    def _observe(
        self,
        operation: str,
        outcome: str,
        started_at: float,
        *,
        bytes_transferred: int = 0,
    ) -> None:
        self.observability.observe_artifact_store_operation(
            operation=operation,
            outcome=outcome,
            duration_seconds=time.perf_counter() - started_at,
            bytes_transferred=bytes_transferred,
        )

    async def _refresh_capacity(self) -> None:
        if self.capacity_provider is None:
            return
        try:
            capacity = await self.capacity_provider()
        except Exception:
            log.warning("artifact_store_capacity_refresh_failed")
            return
        self.observability.update_artifact_store_capacity(
            total_bytes=capacity.total_bytes,
            free_bytes=capacity.free_bytes,
        )
