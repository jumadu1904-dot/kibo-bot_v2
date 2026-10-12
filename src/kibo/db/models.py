from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """`DateTime(timezone=True)` that's actually reliable across DBs: SQLite
    (used locally/in tests) has no real timezone-aware storage, so a value
    written as UTC-aware comes back *naive* on a fresh read — which then
    blows up the moment it's compared against `datetime.now(timezone.utc)`
    (`TypeError: can't compare offset-naive and offset-aware datetimes`,
    the exact crash that made every confirmation-card button silently do
    nothing — see kibo.services.pending_actions). This type re-attaches UTC
    on the way out (and defensively on the way in) so every column using it
    is guaranteed aware, on SQLite and Postgres alike."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)


class GoogleAccount(Base):
    __tablename__ = "google_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    # Fernet-encrypted (see kibo.security) — never store the raw refresh token.
    refresh_token: Mapped[str] = mapped_column(String(512))
    scopes: Mapped[str] = mapped_column(String(256))
    connected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(String(512))
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)  # UTC
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/sent/cancelled
    # Set when this reminder also has a Google Calendar event (see
    # kibo.services.calendar.create_event); None when Google isn't connected.
    google_event_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Serialized list of kibo.services.interpreter action models, awaiting
    # the user's tap on the confirmation card (see kibo.services.pending_actions).
    payload: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)


class LocalTask(Base):
    """A task or note kept in the bot instead of Google Tasks — used when
    the user hasn't connected Google (tasks) or always (notes, which have
    no Google equivalent). See docs/ARCHITECTURE.md model de dades."""

    __tablename__ = "local_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # task/note
    title: Mapped[str] = mapped_column(String(512))
    done: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
