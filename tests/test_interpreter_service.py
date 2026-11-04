import pytest

from kibo.db.models import User
from kibo.services import interpreter


def _user() -> User:
    return User(id=1, telegram_id=1, lang="en", timezone="Europe/Madrid")


async def test_parse_returns_typed_actions(monkeypatch):
    async def fake_generate(**kwargs):
        return [
            {"type": "event", "title": "Meeting with Laura", "start": "2026-01-02T09:00:00Z"},
            {"type": "task", "title": "Buy milk"},
        ]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    actions = await interpreter.parse(user=_user(), text="tomorrow at 10 meeting with Laura, buy milk")

    assert len(actions) == 2
    assert isinstance(actions[0], interpreter.CreateEvent)
    assert actions[0].title == "Meeting with Laura"
    assert isinstance(actions[1], interpreter.CreateTask)
    assert actions[1].title == "Buy milk"


async def test_parse_returns_event_with_no_start_when_omitted(monkeypatch):
    async def fake_generate(**kwargs):
        return [{"type": "event", "title": "Dentist appointment"}]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    actions = await interpreter.parse(user=_user(), text="add a dentist appointment")
    assert len(actions) == 1
    assert isinstance(actions[0], interpreter.CreateEvent)
    assert actions[0].start is None


async def test_parse_returns_query_without_requiring_an_answer(monkeypatch):
    # Gemini only ever has to capture the question — it has no real access
    # to the user's data, so it must never be asked to answer it itself
    # (see kibo.bot.handlers.smart_input._answer_query, which looks up the
    # real data and answers from that instead).
    async def fake_generate(**kwargs):
        return [{"type": "query", "question": "What's on my agenda today?"}]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    actions = await interpreter.parse(user=_user(), text="what do I have today?")
    assert len(actions) == 1
    assert isinstance(actions[0], interpreter.Query)
    assert actions[0].question == "What's on my agenda today?"
    assert not hasattr(actions[0], "answer")


async def test_parse_ignores_unknown_action_types(monkeypatch):
    async def fake_generate(**kwargs):
        return [{"type": "unknown_future_type", "foo": "bar"}]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    actions = await interpreter.parse(user=_user(), text="whatever")
    assert actions == []


async def test_parse_drops_invalid_action_instead_of_failing_the_whole_batch(monkeypatch):
    async def fake_generate(**kwargs):
        return [
            {"type": "reminder", "text": "no due date"},  # missing required due_at
            {"type": "task", "title": "Buy milk"},
        ]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    actions = await interpreter.parse(user=_user(), text="whatever")
    assert len(actions) == 1
    assert isinstance(actions[0], interpreter.CreateTask)


async def test_parse_wraps_gemini_errors(monkeypatch):
    from kibo.clients import gemini

    async def fake_generate(**kwargs):
        raise gemini.GeminiError("boom", status_code=400)  # not retryable

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    with pytest.raises(interpreter.InterpretError):
        await interpreter.parse(user=_user(), text="whatever")


async def test_parse_retries_primary_model_before_succeeding(monkeypatch):
    from kibo.clients import gemini

    monkeypatch.setattr(interpreter, "INITIAL_BACKOFF_SECONDS", 0)
    calls = {"count": 0}

    async def fake_generate(*, model, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise gemini.GeminiError("overloaded", status_code=503)
        return [{"type": "note", "text": "hi"}]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    actions = await interpreter.parse(user=_user(), text="whatever")
    assert calls["count"] == 2
    assert isinstance(actions[0], interpreter.CreateNote)


async def test_parse_falls_back_to_second_model_when_primary_exhausted(monkeypatch):
    from kibo.clients import gemini

    monkeypatch.setattr(interpreter, "INITIAL_BACKOFF_SECONDS", 0)
    seen_models = []

    async def fake_generate(*, model, **kwargs):
        seen_models.append(model)
        if model == interpreter.get_settings().gemini_model:
            raise gemini.GeminiError("overloaded", status_code=503)
        return [{"type": "note", "text": "hi"}]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    actions = await interpreter.parse(user=_user(), text="whatever")
    assert isinstance(actions[0], interpreter.CreateNote)
    assert interpreter.get_settings().gemini_fallback_model in seen_models


async def test_parse_raises_when_both_models_exhausted(monkeypatch):
    from kibo.clients import gemini

    monkeypatch.setattr(interpreter, "INITIAL_BACKOFF_SECONDS", 0)

    async def fake_generate(**kwargs):
        raise gemini.GeminiError("overloaded", status_code=503)

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    with pytest.raises(interpreter.InterpretError):
        await interpreter.parse(user=_user(), text="whatever")


async def test_parse_datetime_returns_start_and_all_day(monkeypatch):
    async def fake_generate(**kwargs):
        return [{"type": "datetime", "start": "2026-01-02T09:00:00Z", "all_day": False}]

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    result = await interpreter.parse_datetime(user=_user(), text="tomorrow at 10")
    assert result is not None
    start, all_day = result
    assert start.isoformat() == "2026-01-02T09:00:00+00:00"
    assert all_day is False


async def test_parse_datetime_returns_none_when_gemini_fails(monkeypatch):
    from kibo.clients import gemini

    async def fake_generate(**kwargs):
        raise gemini.GeminiError("boom", status_code=400)

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    assert await interpreter.parse_datetime(user=_user(), text="whenever") is None


async def test_parse_datetime_returns_none_when_no_call_made(monkeypatch):
    async def fake_generate(**kwargs):
        return []

    monkeypatch.setattr(interpreter.gemini, "generate", fake_generate)
    assert await interpreter.parse_datetime(user=_user(), text="whenever") is None
