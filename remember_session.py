from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken

REMEMBER_DAYS_DEFAULT = 30


def fernet_key_from_secret(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet(secret: str) -> Fernet:
    return Fernet(fernet_key_from_secret(secret))


def seal_remember_payload(
    refresh_token: str,
    secret: str | None,
    *,
    ttl_days: int = REMEMBER_DAYS_DEFAULT,
    now: datetime | None = None,
) -> str | None:
    if not secret or not refresh_token:
        return None
    current = now or datetime.now(timezone.utc)
    payload = json.dumps(
        {
            "refresh_token": refresh_token,
            "exp": int((current + timedelta(days=ttl_days)).timestamp()),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return _fernet(secret).encrypt(payload).decode("ascii")


def unseal_remember_payload(
    value: str | None,
    secret: str | None,
    *,
    now: datetime | None = None,
) -> str | None:
    if not secret or not value:
        return None
    try:
        raw = _fernet(secret).decrypt(str(value).encode("ascii"))
    except (InvalidToken, ValueError, TypeError):
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    current = now or datetime.now(timezone.utc)
    if int(payload.get("exp") or 0) < int(current.timestamp()):
        return None
    token = payload.get("refresh_token")
    if not isinstance(token, str) or not token:
        return None
    return token
