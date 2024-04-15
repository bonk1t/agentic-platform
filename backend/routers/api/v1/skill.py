import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.dependencies.auth import get_current_superuser, get_current_user
from backend.models.auth import User
from backend.models.request_models import SkillExecutePostRequest
from backend.models.response_models import (
    BaseResponse,
    CreateSkillVersionData,
    CreateSkillVersionResponse,
    ExecuteSkillResponse,
    GetSkillListResponse,
    GetSkillResponse,
)
from backend.models.skill_config import SkillConfig
from backend.repositories.skill_config_storage import SkillConfigStorage
from backend.services.skill_service import SkillService

logger = logging.getLogger(__name__)
skill_router = APIRouter(tags=["skill"])


# TODO: introduce a SkillManager class (like AgencyManager and AgentManager)
# TODO: add pagination support for skill list

# FIXME: current limitation on skills: we always use common skills (user_id=None).
# TODO: support dynamic loading of skills (save skills in /approve to Python files in backend/custom_tools,
#  and update the skill mapping).


@skill_router.get("/skill/list")
async def get_skill_list(
    current_user: Annotated[User, Depends(get_current_user)],
    storage: SkillConfigStorage = Depends(SkillConfigStorage),
) -> GetSkillListResponse:
    """Get a list of configs for all skills."""
    skills = storage.load_by_user_id(current_user.id) + storage.load_by_user_id(None)
    return GetSkillListResponse(data=skills)


@skill_router.get("/skill")
async def get_skill_config(
    current_user: Annotated[User, Depends(get_current_user)],
    id: str = Query(..., description="The unique identifier of the skill"),
    storage: SkillConfigStorage = Depends(SkillConfigStorage),
) -> GetSkillResponse:
    """Get a skill configuration by ID.
    NOTE: currently this endpoint is not used in the frontend.
    """
    config = storage.load_by_id(id)
    if not config:
        logger.warning(f"Skill not found: {id}, user: {current_user.id}")
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Skill not found")
    # check if the current_user has permissions to get the skill config
    if config.user_id and config.user_id != current_user.id:
        logger.warning(f"User {current_user.id} does not have permissions to get the skill: {config.id}")
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="You don't have permissions to access this skill")
    return GetSkillResponse(data=config)


@skill_router.post("/skill")
async def create_skill_version(
    current_user: Annotated[User, Depends(get_current_user)],
    config: SkillConfig = Body(...),
    storage: SkillConfigStorage = Depends(SkillConfigStorage),
) -> CreateSkillVersionResponse:
    """Create a new version of the skill configuration.
    NOTE: currently this endpoint is not fully supported.
    """
    skill_config_db = None

    # support template configs:
    if not config.user_id:
        config.id = None
    # check if the current_user has permissions
    if config.id:
        skill_config_db = storage.load_by_id(config.id)
        if not skill_config_db:
            logger.warning(f"Skill not found: {config.id}, user: {current_user.id}")
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Skill not found")
        if skill_config_db.user_id != current_user.id:
            logger.warning(f"User {current_user.id} does not have permissions to update the skill: {config.id}")
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN, detail="You don't have permissions to access this skill"
            )

    # Ensure the skill is associated with the current user
    config.user_id = current_user.id

    config.version = skill_config_db.version + 1 if skill_config_db else 1
    config.approved = False
    config.timestamp = datetime.now(UTC).isoformat()

    skill_id, skill_version = storage.save(config)
    # TODO: return the list of skills
    return CreateSkillVersionResponse(data=CreateSkillVersionData(id=skill_id, version=skill_version))


@skill_router.delete("/skill")
async def delete_skill(
    current_user: Annotated[User, Depends(get_current_user)],
    id: str = Query(..., description="The unique identifier of the skill"),
    storage: SkillConfigStorage = Depends(SkillConfigStorage),
):
    """Delete a skill configuration."""
    db_config = storage.load_by_id(id)
    if not db_config:
        logger.warning(f"Skill not found: {id}, user: {current_user.id}")
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Skill not found")

    if db_config.user_id != current_user.id:
        logger.warning(f"User {current_user.id} does not have permissions to delete the skill: {id}")
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="You don't have permissions to access this skill")

    storage.delete(id)
    # TODO: return the list of skills
    return BaseResponse(message="Skill configuration deleted")


@skill_router.post("/skill/approve")
async def approve_skill(
    current_superuser: Annotated[User, Depends(get_current_superuser)],  # noqa: ARG001
    id: str = Query(..., description="The unique identifier of the skill"),
    storage: SkillConfigStorage = Depends(SkillConfigStorage),
):
    """Approve a skill configuration. This endpoint is only accessible to superusers (currently not accessible).
    NOTE: currently this endpoint is not used in the frontend, and you can only approve skills directly in the DB."""
    config = storage.load_by_id(id)
    if not config:
        logger.warning(f"Skill not found: {id}, user: {current_superuser.id}")
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Skill not found")

    config.approved = True

    storage.save(config)
    return BaseResponse(message="Skill configuration approved")


@skill_router.post("/skill/execute")
async def execute_skill(
    current_user: Annotated[User, Depends(get_current_user)],
    request: SkillExecutePostRequest,
    storage: SkillConfigStorage = Depends(SkillConfigStorage),
    skill_service: SkillService = Depends(SkillService),
) -> ExecuteSkillResponse:
    """Execute a skill."""
    config = storage.load_by_id(request.id)
    if not config:
        logger.warning(f"Skill not found: {request.id}, user: {current_user.id}")
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Skill not found")

    # check if the current_user has permissions to execute the skill
    if config.user_id and config.user_id != current_user.id:
        logger.warning(f"User {current_user.id} does not have permissions to execute the skill: {config.id}")
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="You don't have permissions to access this skill")

    # check if the skill is approved
    if not config.approved:
        logger.warning(f"Skill not approved: {config.id}, user: {current_user.id}")
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Skill not approved")

    output = skill_service.execute_skill(config.title, request.user_prompt)

    return ExecuteSkillResponse(data=output)
