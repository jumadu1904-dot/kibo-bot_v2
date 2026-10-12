"""Two unrelated pieces of crypto glue needed by the Google OAuth flow
(see docs/ARCHITECTURE.md "OAuth de Google"):

1. Encrypting the refresh token before it's stored (`encrypt`/`decrypt`).
2. Signing the `state` query param so `/oauth/google/callback` can trust
   which Telegram user a redirect belongs to, and reject stale or forged
   ones (`sign_state`/`verify_state`).
"""

import base64
import hashlib
import hmac
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken

from kibo.config import get_settings

STATE_TTL_SECONDS = 10 * 60


def encrypt(value: str) -> str:
    key = get_settings().encryption_key.encode()
    return Fernet(key).encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    key = get_settings().encryption_key.encode()
    return Fernet(key).decrypt(token.encode()).decode()


def sign_state(telegram_id: int) -> str:
    """Build the `state` param for a Google OAuth URL: payload + HMAC,
    base64url-encoded so it's safe to put in a query string."""
    secret = get_settings().state_secret.encode()
    nonce = secrets.token_urlsafe(8)
    expires_at = int(time.time()) + STATE_TTL_SECONDS
    payload = f"{telegram_id}:{nonce}:{expires_at}"
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode()


def verify_state(state: str) -> int | None:
    """Return the `telegram_id` encoded in `state` if its signature is
    valid and it hasn't expired, else None."""
    secret = get_settings().state_secret.encode()
    try:
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        payload, signature = decoded.rsplit(".", 1)
        telegram_id_str, _nonce, expires_at_str = payload.split(":")
    except (ValueError, UnicodeDecodeError):
        return None

    expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    if int(expires_at_str) < int(time.time()):
        return None
    return int(telegram_id_str)


__all__ = ["InvalidToken", "decrypt", "encrypt", "sign_state", "verify_state"]
