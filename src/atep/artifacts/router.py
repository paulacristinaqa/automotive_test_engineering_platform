from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.artifacts.schemas import (
    ARTIFACT_ID_PATTERN,
    ArtifactCreate,
    ArtifactKind,
    ArtifactPage,
    ArtifactResponse,
    artifact_response,
)
from atep.artifacts.service import create_artifact_metadata, list_artifacts, require_artifact
from atep.artifacts.storage import (
    ArtifactObjectStore,
    ObjectTooLargeError,
)
from atep.core.config import Settings, get_settings
from atep.core.errors import (
    EmptyTestArtifactError,
    TestArtifactTooLargeError,
    TestArtifactUnavailableError,
)
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.test_runs.schemas import RUN_ID_PATTERN
from atep.test_runs.service import require_test_run

router = APIRouter(prefix="/test-runs", tags=["test-artifacts"])
artifacts_read = require_permissions(PermissionName.TEST_ARTIFACTS_READ.value)
artifacts_write = require_permissions(PermissionName.TEST_ARTIFACTS_WRITE.value)


def get_artifact_store(request: Request) -> ArtifactObjectStore:
    return cast(ArtifactObjectStore, request.app.state.artifact_store)


async def upload_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(64 * 1024):
        yield chunk


@router.post(
    "/{run_id}/artifacts", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED
)
async def upload_artifact_endpoint(
    run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN.pattern)],
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(artifacts_write)],
    store: Annotated[ArtifactObjectStore, Depends(get_artifact_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    artifact_id: Annotated[str, Form(min_length=8, max_length=64)],
    kind: Annotated[ArtifactKind, Form()],
    file: Annotated[UploadFile, File()],
) -> ArtifactResponse:
    test_run, _vehicle = await require_test_run(session, run_id)
    try:
        command = ArtifactCreate(
            artifact_id=artifact_id,
            kind=kind,
            filename=file.filename or "",
            media_type=file.content_type or "application/octet-stream",
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    object_key = f"test-runs/{test_run.id}/{uuid4().hex}"
    try:
        stored = await store.put(
            object_key, upload_chunks(file), max_bytes=settings.test_artifact_max_bytes
        )
    except ObjectTooLargeError as exc:
        raise TestArtifactTooLargeError(max_bytes=settings.test_artifact_max_bytes) from exc
    finally:
        await file.close()
    if stored.size_bytes == 0:
        await store.delete(stored.key)
        raise EmptyTestArtifactError()

    try:
        artifact, duplicate = await create_artifact_metadata(
            session,
            test_run=test_run,
            command=command,
            stored=stored,
            actor_user_id=actor.id,
            correlation_id=request_correlation_id(request),
        )
        if duplicate:
            await store.delete(stored.key)
        await session.commit()
    except BaseException:
        if "duplicate" not in locals() or not duplicate:
            await store.delete(stored.key)
        raise
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return artifact_response(artifact, run_id)


@router.get("/{run_id}/artifacts", response_model=ArtifactPage)
async def list_artifacts_endpoint(
    run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(artifacts_read)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    kind: Annotated[ArtifactKind | None, Query()] = None,
) -> ArtifactPage:
    test_run, _vehicle = await require_test_run(session, run_id)
    artifacts, total = await list_artifacts(
        session, test_run=test_run, limit=limit, offset=offset, kind=kind
    )
    return ArtifactPage(
        items=[artifact_response(item, run_id) for item in artifacts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact_endpoint(
    run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN.pattern)],
    artifact_id: Annotated[str, Path(pattern=ARTIFACT_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(artifacts_read)],
) -> ArtifactResponse:
    artifact, associated_run = await require_artifact(
        session, run_id=run_id, artifact_id=artifact_id
    )
    return artifact_response(artifact, associated_run.run_id)


@router.get("/{run_id}/artifacts/{artifact_id}/content")
async def download_artifact_endpoint(
    run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN.pattern)],
    artifact_id: Annotated[str, Path(pattern=ARTIFACT_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(artifacts_read)],
    store: Annotated[ArtifactObjectStore, Depends(get_artifact_store)],
) -> StreamingResponse:
    artifact, _associated_run = await require_artifact(
        session, run_id=run_id, artifact_id=artifact_id
    )
    if not await store.exists(artifact.object_key):
        raise TestArtifactUnavailableError()
    return StreamingResponse(
        store.stream(artifact.object_key),
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Content-Length": str(artifact.size_bytes),
            "ETag": f'"{artifact.sha256}"',
            "X-Content-SHA256": artifact.sha256,
        },
    )
