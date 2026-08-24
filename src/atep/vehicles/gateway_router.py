from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.registry.service import authenticate_module
from atep.registry.workload_identity import ModuleAuthentication, module_authentication
from atep.vehicles.vhal_contracts import VhalMappingCatalog, vhal_mapping_catalog

TELEMETRY_PUBLISH_CAPABILITY = "vehicle.telemetry.publish"

router = APIRouter(prefix="/vehicle-gateway", tags=["vehicle-gateway"])


@router.get("/vhal-mappings", response_model=VhalMappingCatalog)
async def get_vhal_mappings(
    session: Annotated[AsyncSession, Depends(get_session)],
    module_id: Annotated[UUID, Header(alias="X-ATEP-Module-ID")],
    authentication: Annotated[ModuleAuthentication, Depends(module_authentication)],
) -> VhalMappingCatalog:
    """Publish the reviewed AAOS mapping only to a telemetry-authorized gateway."""

    await authenticate_module(
        session,
        module_id=module_id,
        token=authentication.token,
        spiffe_module_name=authentication.spiffe_module_name,
        required_capability=TELEMETRY_PUBLISH_CAPABILITY,
    )
    return vhal_mapping_catalog()
