# src/pm_order/api/amm_router.py
"""AMM-specific order endpoints: Atomic Replace and Batch Cancel.

Mounted at /api/v1/amm/orders/ in main.py.
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.schemas import ApiResponse
from src.pm_common.database import get_db_session as get_db
from src.pm_gateway.auth.dependencies import require_amm_user
from src.pm_order.application.amm_schemas import (
    BatchCancelRequest,
    BatchCancelResponse,
    ReplaceRequest,
    ReplaceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AMM Orders"])


@router.post("/replace", response_model=ApiResponse[ReplaceResponse])
async def atomic_replace(
    request: ReplaceRequest,
    current_user=Depends(require_amm_user),
    db: AsyncSession = Depends(get_db),
):
    """Atomic Replace: cancel old order + place new order atomically.

    See interface contract v1.4 §3.1.
    """
    from src.pm_matching.application.service import get_matching_engine

    engine = get_matching_engine()

    async with db.begin():
        result = await engine.replace_order(
            old_order_id=request.old_order_id,
            new_order_params=request.new_order,
            user_id=str(current_user.id),
            db=db,
        )

    return ApiResponse(
        code=0,
        message="Order replaced successfully",
        data=ReplaceResponse(**result),
    )


@router.post("/batch-cancel", response_model=ApiResponse[BatchCancelResponse])
async def batch_cancel(
    request: BatchCancelRequest,
    current_user=Depends(require_amm_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch Cancel: cancel all AMM orders in a market.

    See interface contract v1.4 §3.2.
    """
    from src.pm_matching.application.service import get_matching_engine

    engine = get_matching_engine()

    async with db.begin():
        result = await engine.batch_cancel(
            market_id=request.market_id,
            user_id=str(current_user.id),
            cancel_scope=request.cancel_scope,
            db=db,
        )

    return ApiResponse(
        code=0,
        message="Batch cancel completed",
        data=BatchCancelResponse(**result),
    )
