from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.test_catalog.models import TestDefinition, TestSuite
from atep.test_catalog.schemas import (
    CATALOG_ID_PATTERN,
    CatalogStatus,
    CatalogStatusUpdate,
    TestDefinitionCreate,
    TestDefinitionPage,
    TestDefinitionResponse,
    TestSuiteCreate,
    TestSuitePage,
    TestSuiteResponse,
)
from atep.test_catalog.service import (
    create_definition,
    create_suite,
    definition_response,
    list_definitions,
    list_suites,
    require_definition,
    require_suite,
    suite_response,
    update_status,
)

router = APIRouter(tags=["test-catalog"])
catalog_read = require_permissions(PermissionName.TEST_CATALOG_READ.value)
catalog_manage = require_permissions(PermissionName.TEST_CATALOG_MANAGE.value)


@router.post(
    "/test-definitions",
    response_model=TestDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_definition_endpoint(
    command: TestDefinitionCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(catalog_manage)],
) -> TestDefinitionResponse:
    item, duplicate = await create_definition(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return definition_response(item)


@router.get("/test-definitions", response_model=TestDefinitionPage)
async def list_definitions_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(catalog_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[CatalogStatus | None, Query(alias="status")] = None,
) -> TestDefinitionPage:
    items, total = await list_definitions(
        session, limit=limit, offset=offset, status=status_filter
    )
    return TestDefinitionPage(
        items=[definition_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/test-definitions/{definition_id}", response_model=TestDefinitionResponse)
async def get_definition_endpoint(
    definition_id: Annotated[str, Path(pattern=CATALOG_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(catalog_read)],
) -> TestDefinitionResponse:
    return definition_response(await require_definition(session, definition_id))


@router.patch(
    "/test-definitions/{definition_id}/status", response_model=TestDefinitionResponse
)
async def update_definition_status_endpoint(
    definition_id: Annotated[str, Path(pattern=CATALOG_ID_PATTERN.pattern)],
    command: CatalogStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(catalog_manage)],
) -> TestDefinitionResponse:
    item = await require_definition(session, definition_id, for_update=True)
    updated, _ = await update_status(
        session,
        resource=item,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    assert isinstance(updated, TestDefinition)
    return definition_response(updated)


@router.post(
    "/test-suites", response_model=TestSuiteResponse, status_code=status.HTTP_201_CREATED
)
async def create_suite_endpoint(
    command: TestSuiteCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(catalog_manage)],
) -> TestSuiteResponse:
    item, duplicate = await create_suite(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return suite_response(item)


@router.get("/test-suites", response_model=TestSuitePage)
async def list_suites_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(catalog_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[CatalogStatus | None, Query(alias="status")] = None,
) -> TestSuitePage:
    items, total = await list_suites(session, limit=limit, offset=offset, status=status_filter)
    return TestSuitePage(
        items=[suite_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/test-suites/{suite_id}", response_model=TestSuiteResponse)
async def get_suite_endpoint(
    suite_id: Annotated[str, Path(pattern=CATALOG_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(catalog_read)],
) -> TestSuiteResponse:
    return suite_response(await require_suite(session, suite_id))


@router.patch("/test-suites/{suite_id}/status", response_model=TestSuiteResponse)
async def update_suite_status_endpoint(
    suite_id: Annotated[str, Path(pattern=CATALOG_ID_PATTERN.pattern)],
    command: CatalogStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(catalog_manage)],
) -> TestSuiteResponse:
    item = await require_suite(session, suite_id, for_update=True)
    updated, _ = await update_status(
        session,
        resource=item,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    assert isinstance(updated, TestSuite)
    return suite_response(updated)
