import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.params import Query
from starlette.status import HTTP_200_OK, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from nalgonda.dependencies.auth import get_current_active_user
from nalgonda.dependencies.dependencies import get_agency_manager, get_agent_manager
from nalgonda.models.agency_config import AgencyConfig
from nalgonda.models.auth import UserInDB
from nalgonda.repositories.agency_config_firestore_storage import AgencyConfigFirestoreStorage
from nalgonda.services.agency_manager import AgencyManager
from nalgonda.services.agent_manager import AgentManager

logger = logging.getLogger(__name__)
agency_router = APIRouter(
    responses={404: {"description": "Not found"}},
    tags=["agency"],
)


@agency_router.get("/agency/list")
async def get_agency_list(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    storage: AgencyConfigFirestoreStorage = Depends(AgencyConfigFirestoreStorage),
) -> list[AgencyConfig]:
    agencies = storage.load_by_owner_id(current_user.id) + storage.load_by_owner_id(None)
    return agencies


@agency_router.get("/agency")
async def get_agency_config(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    agency_id: str = Query(..., description="The unique identifier of the agency"),
    storage: AgencyConfigFirestoreStorage = Depends(AgencyConfigFirestoreStorage),
) -> AgencyConfig:
    agency_config = storage.load_by_agency_id(agency_id)
    if not agency_config:
        logger.warning(f"Agency not found: {agency_id}, user: {current_user.id}")
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Agency not found")
    # check if the current_user has permissions to get the agency config
    if agency_config.owner_id and agency_config.owner_id != current_user.id:
        logger.warning(f"User {current_user.id} does not have permissions to get agency {agency_id}")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")
    return agency_config


@agency_router.put("/agency", status_code=HTTP_200_OK)
async def update_or_create_agency(
    agency_config: AgencyConfig,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    agency_manager: AgencyManager = Depends(get_agency_manager),
    agent_manager: AgentManager = Depends(get_agent_manager),
    storage: AgencyConfigFirestoreStorage = Depends(AgencyConfigFirestoreStorage),
):
    """Create or update an agency and return its id"""
    # support template configs:
    if not agency_config.owner_id:
        logger.info(f"Creating agency for user: {current_user.id}, agency: {agency_config.name}")
        agency_config.agency_id = None
    else:
        # check if the current_user has permissions
        if agency_config.agency_id:
            agency_config_db = storage.load_by_agency_id(agency_config.agency_id)
            if not agency_config_db:
                logger.warning(f"Agency not found: {agency_config.agency_id}, user: {current_user.id}")
                raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Agency not found")
            if agency_config_db.owner_id != current_user.id:
                logger.warning(
                    f"User {current_user.id} does not have permissions to update agency {agency_config.agency_id}"
                )
                raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")

    # check that all used agents belong to the current user
    for agent_id in agency_config.agents:
        get_result = await agent_manager.get_agent(agent_id)
        if get_result:
            _, agent_config = get_result
            if agent_config.owner_id != current_user.id:
                logger.warning(f"User {current_user.id} does not have permissions to use agent {agent_id}")
                raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")
    # FIXME: current limitation: all agents must belong to the current user.
    # to fix: If the agent is a template (agent_config.owner_id is None), it should be copied for the current user
    # (reuse the code from api/agent.py)

    # Ensure the agency is associated with the current user
    agency_config.owner_id = current_user.id

    agency_id = await agency_manager.update_or_create_agency(agency_config)

    return {"agency_id": agency_id}
