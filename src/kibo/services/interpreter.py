"""Turns free text or a voice note into typed actions via Gemini (see
docs/ARCHITECTURE.md "Entrada intel·ligent"). Each action type is a Gemini
function declaration (native tool/function calling, not `responseSchema`
free-form JSON — see kibo.clients.gemini for why); Gemini can call zero,
one, or several in parallel for one message, which is exactly the "split
into separate actions, or none" behavior we need. `parse()` then validates
each call's arguments into the matching Pydantic model below, so callers
(kibo.bot.handlers.smart_input) only ever see typed actions.

`parse()` retries the primary model on transient failures (overloaded/
rate-limited) and falls back to a second model with its own quota if the
primary is exhausted — same two-tier strategy as Kibo V1
(kibo-bot-V1/ia.py), which needed it for the same reason: Gemini's shared
capacity occasionally returns 503/429 even on well-formed requests."""

import asyncio
import logging
from datetime import datetime
from typing import Literal, Union
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, ValidationError

from kibo.clients import gemini
from kibo.config import get_settings
from kibo.db.models import User

logger = logging.getLogger(__name__)

MAX_RETRIES_PER_MODEL = 2
INITIAL_BACKOFF_SECONDS = 1

# Each tool's own `required` list is what actually gets enforced by Gemini
# — unlike a shared responseSchema (tried first; dropped because with only
# "type" required across every action shape, the lighter fallback model
# kept omitting CreateReminder.due_at despite the prompt insisting on it).
_TOOLS = [
    {
        "name": "event",
        "description": "A calendar event with a specific time slot (a meeting, an appointment).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "start": {
                    "type": "STRING",
                    "description": (
                        "ISO 8601 UTC datetime, e.g. 2026-10-04T09:00:00Z. Omit entirely if the user "
                        "gave no date/time at all — never invent one; the app will ask separately."
                    ),
                },
                "end": {"type": "STRING", "description": "ISO 8601 UTC datetime, optional"},
                "all_day": {"type": "BOOLEAN"},
                "calendar_name": {
                    "type": "STRING",
                    "description": "Only if the user explicitly named a calendar to add it to",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "reminder",
        "description": (
            "A one-off nudge at a specific time — 'remind me to...', 'recorda'm...', 'avisa'm...'. "
            "You must always compute due_at yourself from whatever time the user gave, converted to "
            "UTC; never call this without it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING"},
                "due_at": {"type": "STRING", "description": "ISO 8601 UTC datetime, required"},
            },
            "required": ["text", "due_at"],
        },
    },
    {
        "name": "task",
        "description": (
            "A to-do item, even if the user calls it 'tasca'/'task' explicitly or mentions a due "
            "day — tasks don't need a specific time, only a day at most."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "list_name": {
                    "type": "STRING",
                    "description": "Only if the user named a specific list/subject/category to file it under",
                },
                "due_at": {"type": "STRING", "description": "ISO 8601 UTC date, optional (time part is ignored)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "note",
        "description": "A free-form note to remember, nothing to act on.",
        "parameters": {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]},
    },
    {
        "name": "query",
        "description": (
            "A question about the user's own agenda/tasks/reminders, or a request to change/remove "
            "something that already exists (move an event, delete a task...) — anything that isn't "
            "creating a brand new event/reminder/task/note. Just capture the question/request as-is; "
            "do NOT try to answer or act on it yourself — you have no real access to the user's data, "
            "so a fabricated answer would be worse than none. The app looks up the real data "
            "separately and answers from that."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"question": {"type": "STRING"}},
            "required": ["question"],
        },
    },
]

_PROMPT_TEMPLATE = """You are the natural-language input parser for Kibo, a personal productivity Telegram bot.
The user's current local date/time is {now_local} ({timezone}). Their language is {lang}.

Read the user's message (text or transcribed voice note) below and call one tool per distinct
instruction in it.

Rule #1, the one you get wrong most often: if the message contains more than one instruction — even
joined in a single sentence by "and"/"i"/"y", or just separated by a comma — each instruction is its
OWN separate tool call. Never merge two different requests into one call's title/text just because
they were typed together, and never drop a detail (like a named list, or a date/time) just because it
sits in the middle of a longer sentence — pass it as its own argument instead of leaving it in free
text or dropping it.

Worked example (different message, just to show the shape — do not reuse any of these values, always
extract from the real message below instead): with "now" = 2026-03-10 09:00 Europe/Madrid (+01:00),
"upload X to groceries and remind me at 19:30 to call mom" is two separate calls, not one:
  task(title="X", list_name="groceries") and reminder(text="Call mom", due_at="2026-03-10T18:30:00Z")

Resolve all relative dates/times ("tomorrow", "next Monday", "in an hour") against the user's current
local date/time above, then convert them to UTC before passing them as an argument.

If the message doesn't match any tool, don't call anything.

Message:
\"\"\"{text}\"\"\"
"""


class InterpretError(Exception):
    """Raised when Gemini's response can't be turned into valid actions."""


class CreateEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["event"]
    title: str
    # None until the user supplies a date/time — see kibo.bot.handlers.smart_input's
    # clarification step, which asks for it before anything reaches the confirmation card.
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    calendar_name: str | None = None
    # Set by kibo.bot.handlers.smart_input once the user has picked a calendar
    # for an ambiguous event — never filled in by Gemini itself.
    calendar_id: str | None = None


class CreateReminder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["reminder"]
    text: str
    due_at: datetime


class CreateTask(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["task"]
    title: str
    list_name: str | None = None
    due_at: datetime | None = None
    # Set by kibo.bot.handlers.smart_input once the user has picked a list
    # for an ambiguous task (see "which list" clarification step) — never
    # filled in by Gemini itself.
    tasklist_id: str | None = None


class CreateNote(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["note"]
    text: str


class Query(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["query"]
    question: str


Action = Union[CreateEvent, CreateReminder, CreateTask, CreateNote, Query]

ACTIONS_BY_TYPE: dict[str, type[BaseModel]] = {
    "event": CreateEvent,
    "reminder": CreateReminder,
    "task": CreateTask,
    "note": CreateNote,
    "query": Query,
}


def _build_prompt(user: User, text: str) -> str:
    now_local = datetime.now(ZoneInfo(user.timezone))
    return _PROMPT_TEMPLATE.format(
        now_local=now_local.isoformat(timespec="minutes"),
        timezone=user.timezone,
        lang=user.lang,
        text=text,
    )


def _parse_items(items: list[dict]) -> list[Action]:
    """Validate each item independently — one malformed action (Gemini
    occasionally omits a required field) shouldn't throw away every other
    action the user asked for in the same message."""
    actions: list[Action] = []
    for item in items:
        model = ACTIONS_BY_TYPE.get(item.get("type"))
        if model is None:
            continue
        try:
            actions.append(model.model_validate(item))
        except ValidationError:
            logger.warning("Dropping invalid '%s' action from Gemini: %r", item.get("type"), item, exc_info=True)
    return actions


async def _generate_with_retry(
    *, model: str, prompt: str, audio_bytes: bytes | None, audio_mime: str | None
) -> list[dict]:
    settings = get_settings()
    backoff = INITIAL_BACKOFF_SECONDS
    last_error: gemini.GeminiError | None = None

    for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
        try:
            return await gemini.generate(
                api_key=settings.gemini_api_key,
                model=model,
                prompt=prompt,
                tools=_TOOLS,
                audio_bytes=audio_bytes,
                audio_mime=audio_mime,
            )
        except gemini.GeminiError as exc:
            last_error = exc
            if not exc.is_retryable:
                raise
            logger.warning("Gemini (%s) failed (attempt %d/%d): %s", model, attempt, MAX_RETRIES_PER_MODEL, exc)
            if attempt < MAX_RETRIES_PER_MODEL:
                await asyncio.sleep(backoff)
                backoff *= 2
    raise last_error


async def parse(
    *, user: User, text: str | None = None, audio_bytes: bytes | None = None, audio_mime: str | None = None
) -> list[Action]:
    """Interpret `text`, or a voice note (`audio_bytes`/`audio_mime`), into
    typed actions for this user. Raises InterpretError if both the primary
    and fallback models fail, or if nothing usable comes back."""
    settings = get_settings()
    prompt = _build_prompt(user, text or "(see attached voice note)")

    try:
        raw = await _generate_with_retry(
            model=settings.gemini_model, prompt=prompt, audio_bytes=audio_bytes, audio_mime=audio_mime
        )
    except gemini.GeminiError as primary_error:
        if not primary_error.is_retryable or not settings.gemini_fallback_model:
            raise InterpretError(str(primary_error)) from primary_error
        logger.warning("Primary Gemini model exhausted, trying fallback %s", settings.gemini_fallback_model)
        try:
            raw = await _generate_with_retry(
                model=settings.gemini_fallback_model, prompt=prompt, audio_bytes=audio_bytes, audio_mime=audio_mime
            )
        except gemini.GeminiError as fallback_error:
            raise InterpretError(str(fallback_error)) from fallback_error

    return _parse_items(raw)


_DATETIME_TOOL = [
    {
        "name": "datetime",
        "description": "The date/time the user's message specifies.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "start": {"type": "STRING", "description": "ISO 8601 UTC datetime"},
                "all_day": {
                    "type": "BOOLEAN",
                    "description": "true if the user only gave a date, with no time of day",
                },
            },
            "required": ["start", "all_day"],
        },
    }
]

_DATETIME_PROMPT_TEMPLATE = """The user's current local date/time is {now_local} ({timezone}).
They were asked when a calendar event should happen, and replied below. Interpret their reply as a
date/time (resolving anything relative, like "tomorrow" or "at 10", against the current date/time
above) and call datetime() with it converted to UTC. If they only gave a day with no time of day
(or said something like "all day"), set all_day=true and use 00:00 as the time.

Reply:
\"\"\"{text}\"\"\"
"""


async def parse_datetime(*, user: User, text: str) -> tuple[datetime, bool] | None:
    """Interpret a single date/time reply (used when clarifying a missing
    event start — see kibo.bot.handlers.smart_input and
    kibo.bot.handlers.agenda's "new event" flow). Returns (start_utc,
    all_day), or None if Gemini couldn't make sense of it."""
    settings = get_settings()
    now_local = datetime.now(ZoneInfo(user.timezone))
    prompt = _DATETIME_PROMPT_TEMPLATE.format(
        now_local=now_local.isoformat(timespec="minutes"), timezone=user.timezone, text=text
    )
    try:
        raw = await gemini.generate(api_key=settings.gemini_api_key, model=settings.gemini_model, prompt=prompt, tools=_DATETIME_TOOL)
    except gemini.GeminiError:
        return None

    for item in raw:
        if item.get("type") != "datetime" or not item.get("start"):
            continue
        try:
            start = datetime.fromisoformat(item["start"])
        except ValueError:
            continue
        return start, bool(item.get("all_day", False))
    return None
