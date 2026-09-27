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

    # Shared secret for GET /check-reminders. The external cron (cron-job.org)
    # must send it as ?token=... — without it, anyone could trigger the job.
    cron_secret: str = ""

    gemini_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    encryption_key: str = ""
    state_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
