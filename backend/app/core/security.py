import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt

from app.core.config import settings


PBKDF2_ITERATIONS = 600_000
PBKDF2_ALGORITHM = "sha256"
SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    encoded_salt = base64.b64encode(salt).decode("ascii")
    encoded_digest = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${encoded_salt}${encoded_digest}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        scheme, iterations, encoded_salt, encoded_digest = hashed_password.split("$", 3)
        if not scheme.startswith("pbkdf2_"):
            return False
        algorithm = scheme.replace("pbkdf2_", "", 1)
        salt = base64.b64decode(encoded_salt.encode("ascii"))
        expected_digest = base64.b64decode(encoded_digest.encode("ascii"))
        digest = hashlib.pbkdf2_hmac(
            algorithm,
            plain_password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(digest, expected_digest)
    except Exception:
        return False


def create_access_token(subject: str, expires_minutes: int | None = None, extra: dict[str, Any] | None = None) -> str:
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
