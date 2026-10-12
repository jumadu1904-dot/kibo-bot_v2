import hashlib
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_token: str
    bot_mode: Literal["polling", "webhook"] = "polling"
    public_url: str = ""
    webhook_secret: str = ""
    database_url: str = "sqlite+aiosqlite:///./kibo.db"

    @property
    def webhook_secret_token(self) -> str | None:
        """Telegram's `secret_token` only allows [A-Za-z0-9_-], but a
        provider's auto-generated WEBHOOK_SECRET can be plain base64 (e.g.
        Render's `generateValue`), which includes '+'/'/'/'=' and makes
        `set_webhook` fail with "Secret token contains illegal characters".
        Hashing deterministically derives a safe token from whatever raw
        value ends up in the env var, instead of depending on the provider
        to generate an already-safe one."""
        if not self.webhook_secret:
            return None
        return hashlib.sha256(self.webhook_secret.encode()).hexdigest()

    # Shared secret for GET /check-reminders. The external cron (cron-job.org)
    # must send it as ?token=... — without it, anyone could trigger the job.
    cron_secret: str = ""

    gemini_api_key: str = ""
    # Google retires Gemini model ids for new API keys quite fast (2.0 and
    # then 2.5 flash both went 404 "no longer available to new users" while
    # this project was being built) — check `GET v1beta/models` with your
    # own key if this 404s again, and update both ids below.
    #
    # "-flash-lite" is primary on purpose, not "-flash": on a free API key,
    # the full flash model's daily quota was measured at just 20 requests
    # (resets at midnight Pacific time) and it was frequently 503
    # "overloaded" on top of that, while flash-lite had a much higher quota
    # and responded reliably. The fuller model is kept as a fallback for
    # when flash-lite's own (rarer, but non-zero) retryable failures hit —
    # see kibo.services.interpreter.
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_fallback_model: str = "gemini-3.8-flash"
    google_client_id: str = ""
    google_client_secret: str = ""
    encryption_key: str = ""
    state_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
