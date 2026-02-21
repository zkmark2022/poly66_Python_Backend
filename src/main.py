"""FastAPI application entry point.

Run with: uvicorn src.main:app --reload --port 8000
"""

# ruff: noqa: E402  -- uvloop.install() must run before other imports

import uvloop

uvloop.install()

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from config.settings import settings
from src.pm_account.api.router import router as account_router
from src.pm_common.database import engine
from src.pm_common.errors import AppError
from src.pm_common.redis_client import close_redis, get_redis
from src.pm_common.response import error_response
from src.pm_gateway.api.router import router as auth_router
from src.pm_gateway.middleware.request_log import RequestLogMiddleware
from src.pm_market.api.router import router as market_router
from src.pm_order.api.router import router as order_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: verify DB + Redis connections. Shutdown: dispose."""
    # Startup
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await get_redis()
    yield
    # Shutdown
    await engine.dispose()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(RequestLogMiddleware)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    resp = error_response(exc.code, exc.message)
    return JSONResponse(
        status_code=exc.http_status,
        content=resp.model_dump(),
    )


app.include_router(auth_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(order_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
