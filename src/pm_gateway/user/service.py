"""User domain service: register, login, refresh.

All DB operations use the injected AsyncSession. Transactions are managed
by the caller (router layer) via `async with db.begin()`.
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.errors import (
    AccountDisabledError,
    EmailExistsError,
    InvalidCredentialsError,
    UsernameExistsError,
)
from src.pm_gateway.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.pm_gateway.auth.password import hash_password, verify_password
from src.pm_gateway.user.db_models import UserModel


class UserService:
    """Stateless service — instantiate once, reuse across requests."""

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        db: AsyncSession,
    ) -> UserModel:
        """Register a new user and auto-create their account row.

        Atomically inserts into `users` and `accounts` in a single transaction.
        The caller must wrap this in `async with db.begin()`.
        """
        # Check username uniqueness (DB UNIQUE constraint is the final guard)
        result = await db.execute(
            select(UserModel).where(UserModel.username == username)
        )
        if result.scalar_one_or_none() is not None:
            raise UsernameExistsError()

        # Check email uniqueness
        result = await db.execute(
            select(UserModel).where(UserModel.email == email)
        )
        if result.scalar_one_or_none() is not None:
            raise EmailExistsError()

        # Create user row
        user = UserModel(
            username=username,
            email=email,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        await db.flush()  # Get user.id without committing

        # Auto-create accounts row in the same transaction
        # Inline import avoids any future circular dependency with pm_account module
        await db.execute(
            text(
                "INSERT INTO accounts (user_id, available_balance, frozen_balance, version) "
                "VALUES (:user_id, 0, 0, 0)"
            ),
            {"user_id": str(user.id)},
        )

        return user

    async def login(
        self,
        username: str,
        password: str,
        db: AsyncSession,
    ) -> tuple[str, str]:
        """Authenticate user and return (access_token, refresh_token).

        Note: "User not found" and "Wrong password" both raise InvalidCredentialsError
        intentionally — prevents username enumeration attacks.
        """
        result = await db.execute(
            select(UserModel).where(UserModel.username == username)
        )
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise AccountDisabledError()

        return (
            create_access_token(str(user.id)),
            create_refresh_token(str(user.id)),
        )

    async def refresh(self, refresh_token: str) -> str:
        """Validate refresh token and return a new access token.

        MVP NOTE: Does not rotate the refresh token. For production, implement
        refresh token rotation: issue new refresh_token + invalidate old one
        via jti claim stored in Redis.
        """
        payload = decode_token(refresh_token, expected_type="refresh")
        user_id: str = str(payload["sub"])
        return create_access_token(user_id)
