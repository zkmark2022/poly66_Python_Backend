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
from src.pm_common.database import engine
from src.pm_common.errors import AppError
from src.pm_common.redis_client import close_redis, get_redis
from src.pm_common.response import error_response


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


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    resp = error_response(exc.code, exc.message)
    return JSONResponse(
        status_code=exc.http_status,
        content=resp.model_dump(),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
