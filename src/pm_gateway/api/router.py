"""Auth API router: register, login, refresh.

All endpoints return ApiResponse[T]. request_id is read from
request.state (injected by RequestLogMiddleware).

Ref: Planning/Detail_Design/02_API接口契约.md §2.1-2.3
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from src.pm_common.database import get_db_session
from src.pm_common.response import ApiResponse, success_response
from src.pm_gateway.user.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    UserInfo,
)
from src.pm_gateway.user.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])
_service = UserService()


def _get_request_id(request: Request) -> str:
    """Read request_id injected by RequestLogMiddleware, fallback if absent."""
    return getattr(request.state, "request_id", "req_unknown")


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse,
    summary="User registration",
)
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    async with db.begin():
        user = await _service.register(body.username, body.email, body.password, db)

    data = RegisterResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        created_at=user.created_at.isoformat(),
    )
    resp = success_response(data.model_dump())
    resp.request_id = _get_request_id(request)
    resp.message = "User registered successfully"
    return resp


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse,
    summary="User login",
)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    user, access_token, refresh_token = await _service.login(body.username, body.password, db)

    data = LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=UserInfo(
            user_id=str(user.id),
            username=user.username,
            email=user.email,
        ),
    )
    resp = success_response(data.model_dump())
    resp.request_id = _get_request_id(request)
    resp.message = "Login successful"
    return resp


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse,
    summary="Refresh access token",
)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
) -> ApiResponse:
    new_access_token = await _service.refresh(body.refresh_token)

    data = RefreshResponse(
        access_token=new_access_token,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )
    resp = success_response(data.model_dump())
    resp.request_id = _get_request_id(request)
    resp.message = "Token refreshed"
    return resp
