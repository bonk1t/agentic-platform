import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN

from nalgonda.models.auth import User

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> User:
    try:
        user = auth.verify_id_token(credentials.credentials, check_revoked=True)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials. {err}",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from None
    logger.info(f"Authenticated user: {user}")
    return User(**user)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.disabled:
        logger.error(f"User {current_user.id} is inactive")
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if not current_user.is_superuser:
        logger.error(f"User {current_user.id} is not a superuser")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges")
    return current_user
