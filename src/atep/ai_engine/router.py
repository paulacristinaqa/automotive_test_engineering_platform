from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.log_intelligence import (
    create_log_analysis,
    list_log_analyses,
    log_analysis_response,
    require_log_analysis,
)
from atep.ai_engine.schemas import (
    AiAnalysisExecute,
    AiAnalysisExecutionPage,
    AiAnalysisExecutionResponse,
    AiAnalysisRequestCreate,
    AiAnalysisRequestPage,
    AiAnalysisRequestResponse,
    AiLogAnalysisCreate,
    AiLogAnalysisPage,
    AiLogAnalysisResponse,
    AiTask,
    AiTestSuggestionCreate,
    AiTestSuggestionPage,
    AiTestSuggestionPromote,
    AiTestSuggestionResponse,
    AiTestSuggestionReview,
)
from atep.ai_engine.service import (
    create_request,
    execute_request,
    execution_response,
    list_executions,
    list_requests,
    request_response,
    require_request,
)
from atep.ai_engine.test_generation import (
    create_suggestion,
    list_suggestions,
    promote_suggestion,
    require_suggestion,
    review_suggestion,
    suggestion_response,
)
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


@router.post(
    "/analysis-requests/{request_id}/executions",
    response_model=AiAnalysisExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_request_endpoint(
    request_id: Annotated[str, request_path],
    command: AiAnalysisExecute,
    http_request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> AiAnalysisExecutionResponse:
    analysis = await require_request(session, request_id, for_update=True)
    execution, duplicate = await execute_request(
        session,
        request=analysis,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(http_request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return execution_response(execution, request=analysis, duplicate=duplicate)


@router.get(
    "/analysis-requests/{request_id}/executions",
    response_model=AiAnalysisExecutionPage,
)
async def list_executions_endpoint(
    request_id: Annotated[str, request_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> AiAnalysisExecutionPage:
    analysis = await require_request(session, request_id)
    rows, total = await list_executions(session, request=analysis, limit=limit, offset=offset)
    return AiAnalysisExecutionPage(
        items=[execution_response(item, request=analysis) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/analysis-requests/{request_id}/log-intelligence",
    response_model=AiLogAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_log_analysis_endpoint(
    request_id: Annotated[str, request_path],
    command: AiLogAnalysisCreate,
    http_request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> AiLogAnalysisResponse:
    analysis_request = await require_request(session, request_id, for_update=True)
    analysis, duplicate = await create_log_analysis(
        session,
        request=analysis_request,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(http_request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return log_analysis_response(analysis, request=analysis_request, duplicate=duplicate)


@router.get("/log-analyses", response_model=AiLogAnalysisPage)
async def list_log_analyses_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    source: Annotated[
        str | None, Query(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    ] = None,
) -> AiLogAnalysisPage:
    rows, total = await list_log_analyses(session, limit=limit, offset=offset, source=source)
    return AiLogAnalysisPage(
        items=[log_analysis_response(item, request=request) for item, request in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/log-analyses/{analysis_id}", response_model=AiLogAnalysisResponse)
async def get_log_analysis_endpoint(
    analysis_id: Annotated[str, request_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> AiLogAnalysisResponse:
    analysis, analysis_request = await require_log_analysis(session, analysis_id)
    return log_analysis_response(analysis, request=analysis_request)


@router.post(
    "/analysis-requests/{request_id}/test-suggestions",
    response_model=AiTestSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_suggestion_endpoint(
    request_id: Annotated[str, request_path],
    command: AiTestSuggestionCreate,
    http_request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> AiTestSuggestionResponse:
    analysis_request = await require_request(session, request_id, for_update=True)
    suggestion, duplicate = await create_suggestion(
        session,
        request=analysis_request,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(http_request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return suggestion_response(suggestion, request=analysis_request, duplicate=duplicate)


@router.get("/test-suggestions", response_model=AiTestSuggestionPage)
async def list_test_suggestions_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    suggestion_status: Annotated[
        str | None, Query(alias="status", pattern=r"^(draft|approved|rejected|promoted)$")
    ] = None,
) -> AiTestSuggestionPage:
    rows, total = await list_suggestions(
        session, limit=limit, offset=offset, status=suggestion_status
    )
    return AiTestSuggestionPage(
        items=[suggestion_response(item, request=request) for item, request in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/test-suggestions/{suggestion_id}", response_model=AiTestSuggestionResponse)
async def get_test_suggestion_endpoint(
    suggestion_id: Annotated[str, request_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> AiTestSuggestionResponse:
    suggestion, analysis_request = await require_suggestion(session, suggestion_id)
    return suggestion_response(suggestion, request=analysis_request)


@router.post("/test-suggestions/{suggestion_id}/review", response_model=AiTestSuggestionResponse)
async def review_test_suggestion_endpoint(
    suggestion_id: Annotated[str, request_path],
    command: AiTestSuggestionReview,
    http_request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> AiTestSuggestionResponse:
    suggestion, analysis_request = await require_suggestion(session, suggestion_id, for_update=True)
    suggestion, duplicate = await review_suggestion(
        session,
        suggestion=suggestion,
        request=analysis_request,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(http_request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return suggestion_response(suggestion, request=analysis_request, duplicate=duplicate)


@router.post("/test-suggestions/{suggestion_id}/promotion", response_model=AiTestSuggestionResponse)
async def promote_test_suggestion_endpoint(
    suggestion_id: Annotated[str, request_path],
    command: AiTestSuggestionPromote,
    http_request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> AiTestSuggestionResponse:
    suggestion, analysis_request = await require_suggestion(session, suggestion_id, for_update=True)
    suggestion, duplicate = await promote_suggestion(
        session,
        suggestion=suggestion,
        request=analysis_request,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(http_request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return suggestion_response(suggestion, request=analysis_request, duplicate=duplicate)
