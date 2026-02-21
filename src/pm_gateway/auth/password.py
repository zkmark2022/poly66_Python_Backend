"""Password hashing utilities using bcrypt.

Uses the ``bcrypt`` library directly (>=4.0).  passlib[bcrypt] is intentionally
avoided because passlib is unmaintained and incompatible with bcrypt >=4.

MVP NOTE: bcrypt is the default choice.  For higher security in production
consider Argon2id via the ``argon2-cffi`` package.
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt. Returns a utf-8 hash string."""
    hashed_bytes: bytes = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
