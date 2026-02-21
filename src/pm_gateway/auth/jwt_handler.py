"""JWT token creation and verification.

MVP NOTE: Using HS256 (symmetric HMAC). All services share one JWT_SECRET.
For production with multiple services, upgrade to RS256 (asymmetric RSA):
  - Private key signs tokens (auth service only)
  - Public key verifies tokens (all services, no secret sharing needed)
  - Key rotation becomes possible without downtime

MVP NOTE: No token revocation. Once issued, tokens are valid until expiry.
For production, add jti (JWT ID) claim + Redis blacklist to support logout
and immediate revocation on security incidents.
"""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from config.settings import settings
from src.pm_common.errors import InvalidCredentialsError, InvalidRefreshTokenError

_ALGORITHM = settings.JWT_ALGORITHM  # "HS256"
_ACCESS_EXPIRE = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
_REFRESH_EXPIRE = timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)


def create_access_token(user_id: str) -> str:
    """Issue a short-lived access token (default: 30 min)."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + _ACCESS_EXPIRE,
    }
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def create_refresh_token(user_id: str) -> str:
    """Issue a long-lived refresh token (default: 7 days).

    MVP NOTE: Refresh tokens are not rotated on use. For production,
    implement refresh token rotation: each /auth/refresh call issues
    a new refresh token and invalidates the old one (via jti + Redis).
    """
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + _REFRESH_EXPIRE,
    }
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def decode_token(token: str, expected_type: str) -> dict[str, str]:
    """Decode and validate a JWT token.

    Args:
        token: Raw JWT string.
        expected_type: "access" or "refresh". Strictly enforced to prevent
                       token type confusion attacks.

    Returns:
        Decoded payload dict with at minimum {"sub": ..., "type": ...}.

    Raises:
        InvalidCredentialsError: Token invalid/expired and expected_type="access".
        InvalidRefreshTokenError: Token invalid/expired and expected_type="refresh".
    """
    payload: dict[str, str] = {}
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[_ALGORITHM],  # Explicit list prevents algorithm confusion
        )
    except JWTError:
        _raise_auth_error(expected_type)

    if payload.get("type") != expected_type:
        _raise_auth_error(expected_type)

    return payload


def _raise_auth_error(expected_type: str) -> None:
    """Raise the appropriate error based on which token type was expected."""
    if expected_type == "access":
        raise InvalidCredentialsError()
    raise InvalidRefreshTokenError()
