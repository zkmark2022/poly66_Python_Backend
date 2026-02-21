"""Pydantic request/response schemas for pm_gateway.

All responses are wrapped in ApiResponse[T] at the router layer.
Ref: Planning/Detail_Design/02_API接口契约.md §2.1-2.3
"""

import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """Enforce: at least one uppercase, one lowercase, one digit."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    """Minimal user info embedded in responses."""

    user_id: str
    username: str
    email: str


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    email: str
    created_at: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800  # 30 minutes in seconds
    user: UserInfo


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int = 1800
