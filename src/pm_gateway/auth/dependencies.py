"""FastAPI dependency: get_current_user.

Usage in any protected router:
    from src.pm_gateway.auth.dependencies import get_current_user

    @router.get("/protected")
    async def protected(user: UserModel = Depends(get_current_user)):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.database import get_db_session
from src.pm_common.errors import AccountDisabledError, InvalidCredentialsError
from src.pm_gateway.auth.jwt_handler import decode_token
from src.pm_gateway.user.db_models import UserModel

# tokenUrl tells Swagger UI where to get a token (used for the "Authorize" button)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Reusable 401 exception with WWW-Authenticate header (OAuth2 standard)
_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> UserModel:
    """Extract and validate the JWT Bearer token, return the UserModel.

    Raises HTTP 401 if the token is missing, invalid, or expired.
    Raises HTTP 422 (AccountDisabledError) if the user account is disabled.
    """
    try:
        payload = decode_token(token, expected_type="access")
    except InvalidCredentialsError:
        raise _CREDENTIALS_EXCEPTION from None

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise _CREDENTIALS_EXCEPTION

    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    if not user.is_active:
        raise AccountDisabledError()

    return user
