"""AMM-specific endpoints: Privileged Mint and Burn.

Mounted at /api/v1/amm/ in main.py.
See interface contract v1.4 §3.3 (Mint) and §3.4 (Burn).
"""
import logging

from fastapi import Depends
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.application.amm_schemas import (
    BurnRequest,
    BurnResponse,
    MintRequest,
    MintResponse,
)
from src.pm_clearing.domain.burn_service import execute_privileged_burn
from src.pm_clearing.domain.mint_service import execute_privileged_mint
from src.pm_common.database import get_db_session
from src.pm_common.response import ApiResponse, success_response
from src.pm_gateway.auth.dependencies import require_amm_user
from src.pm_gateway.user.db_models import UserModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AMM"])


@router.post("/mint", status_code=201)
async def privileged_mint(
    request: MintRequest,
    current_user: UserModel = Depends(require_amm_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """Privileged Mint: create YES+NO share pairs for AMM.

    See interface contract v1.4 §3.3.
    Returns 201 on success, 200 on idempotent hit.
    """
    try:
        async with db.begin():
            result = await execute_privileged_mint(
                user_id=str(current_user.id),
                market_id=request.market_id,
                quantity=request.quantity,
                idempotency_key=request.idempotency_key,
                db=db,
            )
    except Exception:
        raise

    if result.get("idempotent_hit"):
        return ApiResponse(code=0, message="Mint already processed (idempotent)", data=result)

    return ApiResponse(
        code=0,
        message="Shares minted successfully",
        data=MintResponse(**result).model_dump(),
    )


@router.post("/burn")
async def privileged_burn(
    request: BurnRequest,
    current_user: UserModel = Depends(require_amm_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """Privileged Burn (Auto-Merge): destroy YES+NO share pairs, recover cash.

    See interface contract v1.4 §3.4.
    Returns 200 on success, 200 on idempotent hit.
    """
    async with db.begin():
        result = await execute_privileged_burn(
            user_id=str(current_user.id),
            market_id=request.market_id,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
            db=db,
        )

    if result.get("idempotent_hit"):
        return ApiResponse(code=0, message="Burn already processed (idempotent)", data=result)

    return ApiResponse(
        code=0,
        message="Shares burned (auto-merge) successfully",
        data=BurnResponse(**result).model_dump(),
    )
