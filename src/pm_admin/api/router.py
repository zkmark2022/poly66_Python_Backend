# src/pm_admin/api/router.py
"""Admin REST API."""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_admin.application.service import AdminService
from src.pm_common.database import get_db_session
from src.pm_common.response import ApiResponse, success_response
from src.pm_gateway.auth.dependencies import get_current_user
from src.pm_gateway.user.db_models import UserModel

router = APIRouter(prefix="/admin", tags=["admin"])
_service = AdminService()


class ResolveRequest(BaseModel):
    outcome: str


@router.post("/markets/{market_id}/resolve")
async def resolve_market(
    market_id: str,
    body: ResolveRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse:
    result = await _service.resolve_market(market_id, body.outcome, db)
    return success_response(result)
