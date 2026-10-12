from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    lang: Mapped[str] = mapped_column(String(5), default="en")
    city: Mapped[str | None] = mapped_column(String(120))
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    briefing_time: Mapped[str | None] = mapped_column(String(5))  # "08:00" local time
    briefing_blocks: Mapped[list] = mapped_column(
        JSON, default=lambda: ["weather", "agenda", "tasks", "news"]
    )
    news_topics: Mapped[list] = mapped_column(JSON, default=list)
    onboarding_step: Mapped[str] = mapped_column(String(32), default="language")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GoogleAccount(Base):
    __tablename__ = "google_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    # Fernet-encrypted (see kibo.security) — never store the raw refresh token.
    refresh_token: Mapped[str] = mapped_column(String(512))
    scopes: Mapped[str] = mapped_column(String(256))
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
