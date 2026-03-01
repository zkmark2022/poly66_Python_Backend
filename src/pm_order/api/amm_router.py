"""AMM-specific order endpoints: Atomic Replace and Batch Cancel.

Mounted at /api/v1/amm/orders/ in main.py.
See interface contract v1.4 §3.1 (Replace) and §3.2 (Batch Cancel).
"""
import logging
from typing import Annotated

from fastapi import Depends
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.database import get_db_session
from src.pm_common.response import ApiResponse
from src.pm_gateway.auth.dependencies import require_amm_user
from src.pm_gateway.user.db_models import UserModel
from src.pm_matching.application.service import get_matching_engine
from src.pm_order.application.amm_schemas import (
    BatchCancelRequest,
    BatchCancelResponse,
    ReplaceRequest,
    ReplaceResponse,
)
from src.pm_order.infrastructure.persistence import OrderRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AMM Orders"])

_repo = OrderRepository()


@router.post("/replace")
async def atomic_replace(
    request: ReplaceRequest,
    current_user: Annotated[UserModel, Depends(require_amm_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse:
    """Atomic Replace: cancel old order + place new order atomically.

    See interface contract v1.4 §3.1.
    """
    engine = get_matching_engine()
    try:
        result = await engine.replace_order(
            old_order_id=request.old_order_id,
            new_order_params=request.new_order,
            user_id=str(current_user.id),
            repo=_repo,
            db=db,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return ApiResponse(
        code=0,
        message="Order replaced successfully",
        data=ReplaceResponse(**result).model_dump(),
    )


@router.post("/batch-cancel")
async def batch_cancel(
    request: BatchCancelRequest,
    current_user: Annotated[UserModel, Depends(require_amm_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse:
    """Batch Cancel: cancel all AMM orders in a market by scope.

    See interface contract v1.4 §3.2.
    """
    engine = get_matching_engine()
    try:
        result = await engine.batch_cancel(
            market_id=request.market_id,
            user_id=str(current_user.id),
            cancel_scope=request.cancel_scope,
            db=db,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return ApiResponse(
        code=0,
        message="Batch cancel completed",
        data=BatchCancelResponse(**result).model_dump(),
    )
