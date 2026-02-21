"""Unified API response wrapper.

All API endpoints return this format:
{
    "code": 0,           // 0=success, non-0=error code
    "message": "success",
    "data": { ... },     // null on error
    "timestamp": "...",
    "request_id": "..."
}

Ref: Planning/Detail_Design/02_API接口契约.md §1.3
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")


def success_response(data: Any = None) -> ApiResponse:
    return ApiResponse(code=0, message="success", data=data)


def error_response(code: int, message: str) -> ApiResponse:
    return ApiResponse(code=code, message=message, data=None)
