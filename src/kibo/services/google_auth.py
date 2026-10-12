"""Per-user Google OAuth: building the consent URL, handling the
`/oauth/google/callback` redirect, and getting a fresh access token on
demand for the Calendar/Tasks services (see docs/ARCHITECTURE.md "OAuth de
Google per usuari"). No access token is cached in the DB — we exchange the
stored (encrypted) refresh token for a new one on every call, which is
simpler and avoids an extra expiry column."""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from kibo import security
from kibo.clients import google_api
from kibo.config import get_settings
from kibo.db.models import GoogleAccount, User
from kibo.db.repositories import google_accounts

logger = logging.getLogger(__name__)


def _redirect_uri() -> str:
    return f"{get_settings().public_url}/oauth/google/callback"


def get_authorization_url(telegram_id: int) -> str:
    settings = get_settings()
    state = security.sign_state(telegram_id)
    return google_api.build_authorization_url(
        client_id=settings.google_client_id,
        redirect_uri=_redirect_uri(),
        state=state,
    )


async def is_connected(session: AsyncSession, user: User) -> bool:
    return await google_accounts.get_by_user_id(session, user.id) is not None


async def handle_callback(session: AsyncSession, *, code: str, state: str) -> int | None:
    """Verify `state`, exchange `code` for tokens and store the encrypted
    refresh token. Returns the telegram_id the connection belongs to, or
    None if `state` is invalid/expired."""
    telegram_id = security.verify_state(state)
    if telegram_id is None:
        return None

    settings = get_settings()
    token = await google_api.exchange_code(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=_redirect_uri(),
        code=code,
    )
    if token.refresh_token is None:
        # Google only omits this if the user already granted consent and we
        # didn't force a fresh one — we always pass prompt=consent, so this
        # shouldn't happen in practice, but there's nothing useful to store.
        return None

    from kibo.db.repositories import users as users_repo

    user = await users_repo.get_by_telegram_id(session, telegram_id)
    if user is None:
        return None

    await google_accounts.upsert(
        session,
        user.id,
        refresh_token=security.encrypt(token.refresh_token),
        scopes=token.scope,
    )
    return telegram_id


async def get_access_token(session: AsyncSession, user: User) -> str | None:
    account: GoogleAccount | None = await google_accounts.get_by_user_id(session, user.id)
    if account is None:
        return None
    settings = get_settings()
    refresh_token = security.decrypt(account.refresh_token)
    return await google_api.refresh_access_token(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        refresh_token=refresh_token,
    )


async def disconnect(session: AsyncSession, user: User) -> None:
    account = await google_accounts.get_by_user_id(session, user.id)
    if account is not None:
        try:
            await google_api.revoke_token(security.decrypt(account.refresh_token))
        except httpx.HTTPError:
            # Best-effort: still remove our copy even if Google's revoke call fails
            # (e.g. the token was already revoked or Google is unreachable).
            logger.warning("Failed to revoke Google token for user %s", user.id, exc_info=True)
    await google_accounts.delete_for_user(session, user.id)
