import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from nalgonda.dependencies.auth import get_current_active_user
from nalgonda.dependencies.dependencies import get_agency_manager, get_thread_manager
from nalgonda.models.auth import UserInDB
from nalgonda.models.request_models import AgencyMessagePostRequest, ThreadPostRequest
from nalgonda.repositories.agency_config_firestore_storage import AgencyConfigFirestoreStorage
from nalgonda.repositories.session_firestore_storage import SessionConfigFirestoreStorage
from nalgonda.services.agency_manager import AgencyManager
from nalgonda.services.thread_manager import ThreadManager

logger = logging.getLogger(__name__)
session_router = APIRouter(
    responses={404: {"description": "Not found"}},
    tags=["session"],
)


@session_router.get("/session/list")
async def get_session_list(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    storage: SessionConfigFirestoreStorage = Depends(SessionConfigFirestoreStorage),
):
    """Return a list of all sessions for the current user."""
    session_configs = storage.load_by_owner_id(current_user.id)
    return session_configs


@session_router.post("/session")
async def create_session(
    request: ThreadPostRequest,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    agency_manager: AgencyManager = Depends(get_agency_manager),
    thread_manager: ThreadManager = Depends(get_thread_manager),
    storage: AgencyConfigFirestoreStorage = Depends(AgencyConfigFirestoreStorage),
) -> dict:
    """Create a new session for the given agency and return its id."""
    agency_id = request.agency_id
    # check if the current_user has permissions to create a session for the agency
    agency_config = storage.load_by_agency_id(agency_id)
    if not agency_config:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Agency not found")
    if agency_config.owner_id != current_user.id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")

    logger.info(f"Creating a new session for the agency: {agency_id}, and user: {current_user.id}")

    agency = await agency_manager.get_agency(agency_id, None)
    if not agency:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Agency not found")

    thread_id = thread_manager.create_threads(agency)

    await agency_manager.cache_agency(agency, agency_id, thread_id)
    return {"thread_id": thread_id}


@session_router.post("/session/message")
async def post_agency_message(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    request: AgencyMessagePostRequest,
    agency_manager: AgencyManager = Depends(get_agency_manager),
    storage: AgencyConfigFirestoreStorage = Depends(AgencyConfigFirestoreStorage),
) -> dict:
    """Send a message to the User Proxy of the given agency."""
    # check if the current_user has permissions to send a message to the agency
    agency_config = storage.load_by_agency_id(request.agency_id)
    if not agency_config:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Agency not found")
    if agency_config.owner_id != current_user.id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")

    user_message = request.message
    agency_id = request.agency_id
    thread_id = request.thread_id

    logger.info(f"Received message: {user_message}, agency_id: {agency_id}, thread_id: {thread_id}")

    agency = await agency_manager.get_agency(agency_id, thread_id)
    if not agency:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Agency not found")

    try:
        response = await asyncio.to_thread(
            agency.get_completion, message=user_message, yield_messages=False, message_files=None
        )
        return {"response": response}
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail="Something went wrong") from e
