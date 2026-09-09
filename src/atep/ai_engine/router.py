from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.schemas import (
    AiAnalysisRequestCreate,
    AiAnalysisRequestPage,
    AiAnalysisRequestResponse,
    AiTask,
)
from atep.ai_engine.service import create_request, list_requests, request_response, require_request
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id

router = APIRouter(prefix="/ai", tags=["ai-test-engineer"])
read_access = require_permissions(PermissionName.AI_ANALYSIS_READ.value)
manage_access = require_permissions(PermissionName.AI_ANALYSIS_MANAGE.value)
request_path = Path(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")


@router.post("/analysis-requests", response_model=AiAnalysisRequestResponse, status_code=201)
async def create_request_endpoint(
    command: AiAnalysisRequestCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> AiAnalysisRequestResponse:
    analysis, duplicate = await create_request(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return request_response(analysis, duplicate=duplicate)


@router.get("/analysis-requests", response_model=AiAnalysisRequestPage)
async def list_requests_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    task: AiTask | None = None,
) -> AiAnalysisRequestPage:
    rows, total = await list_requests(session, limit=limit, offset=offset, task=task)
    return AiAnalysisRequestPage(
        items=[request_response(item) for item in rows], total=total, limit=limit, offset=offset
    )


@router.get("/analysis-requests/{request_id}", response_model=AiAnalysisRequestResponse)
async def get_request_endpoint(
    request_id: Annotated[str, request_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> AiAnalysisRequestResponse:
    return request_response(await require_request(session, request_id))
