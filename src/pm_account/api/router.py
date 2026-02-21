"""pm_account REST API — 4 endpoints, all require JWT authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_account.application.schemas import DepositRequest, WithdrawRequest
from src.pm_account.application.service import AccountApplicationService
from src.pm_common.database import get_db_session
from src.pm_common.response import ApiResponse, success_response
from src.pm_gateway.auth.dependencies import get_current_user
from src.pm_gateway.user.db_models import UserModel

router = APIRouter(prefix="/account", tags=["account"])

_service = AccountApplicationService()


@router.get("/balance")
async def get_balance(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> ApiResponse:
    data = await _service.get_balance(db, str(current_user.id))
    resp = success_response(data.model_dump())
    resp.request_id = getattr(request.state, "request_id", resp.request_id)
    return resp


@router.post("/deposit")
async def deposit(
    body: DepositRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> ApiResponse:
    data = await _service.deposit(db, str(current_user.id), body.amount_cents)
    resp = success_response(data.model_dump())
    resp.request_id = getattr(request.state, "request_id", resp.request_id)
    return resp


@router.post("/withdraw")
async def withdraw(
    body: WithdrawRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> ApiResponse:
    data = await _service.withdraw(db, str(current_user.id), body.amount_cents)
    resp = success_response(data.model_dump())
    resp.request_id = getattr(request.state, "request_id", resp.request_id)
    return resp


@router.get("/ledger")
async def list_ledger(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
    cursor: str | None = Query(None, description="Pagination cursor (opaque Base64)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    entry_type: str | None = Query(None, description="Filter by LedgerEntryType"),
) -> ApiResponse:
    data = await _service.list_ledger(
        db, str(current_user.id), cursor, limit, entry_type
    )
    resp = success_response(data.model_dump())
    resp.request_id = getattr(request.state, "request_id", resp.request_id)
    return resp
