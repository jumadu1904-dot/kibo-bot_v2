import base64
import json

import httpx
import pytest

from kibo.clients import gemini

_RealAsyncClient = httpx.AsyncClient

_NOTE_TOOL = [
    {
        "name": "note",
        "description": "A note",
        "parameters": {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]},
    }
]


def _patch_client(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        gemini.httpx,
        "AsyncClient",
        lambda **kwargs: _RealAsyncClient(transport=httpx.MockTransport(handler)),
    )


def _response_with_calls(calls: list[dict]) -> httpx.Response:
    parts = [{"functionCall": {"name": call.pop("type"), "args": call}} for call in calls]
    return httpx.Response(200, json={"candidates": [{"content": {"parts": parts}}]})


async def test_generate_sends_prompt_and_tools(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return _response_with_calls([{"type": "note", "text": "hi"}])

    _patch_client(monkeypatch, handler)
    result = await gemini.generate(api_key="key-123", model="gemini-3.1-flash-lite", prompt="hello", tools=_NOTE_TOOL)

    assert "models/gemini-3.1-flash-lite:generateContent" in captured["url"]
    assert "key=key-123" in captured["url"]
    assert captured["body"]["contents"][0]["parts"] == [{"text": "hello"}]
    assert captured["body"]["tools"] == [{"functionDeclarations": _NOTE_TOOL}]
    assert captured["body"]["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}
    assert result == [{"type": "note", "text": "hi"}]


async def test_generate_returns_multiple_parallel_calls(monkeypatch):
    _patch_client(
        monkeypatch,
        lambda request: _response_with_calls([{"type": "task", "title": "A"}, {"type": "reminder", "text": "B", "due_at": "x"}]),
    )
    result = await gemini.generate(api_key="key", model="m", prompt="p", tools=_NOTE_TOOL)
    assert result == [{"type": "task", "title": "A"}, {"type": "reminder", "text": "B", "due_at": "x"}]


async def test_generate_returns_empty_list_when_no_tool_called(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "no call needed"}]}}]}))
    result = await gemini.generate(api_key="key", model="m", prompt="p", tools=_NOTE_TOOL)
    assert result == []


async def test_generate_includes_inline_audio(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _response_with_calls([])

    _patch_client(monkeypatch, handler)
    await gemini.generate(
        api_key="key", model="gemini-3.1-flash-lite", prompt="transcribe", tools=_NOTE_TOOL,
        audio_bytes=b"raw-audio", audio_mime="audio/ogg",
    )

    parts = captured["body"]["contents"][0]["parts"]
    assert parts[1]["inline_data"]["mime_type"] == "audio/ogg"
    assert base64.b64decode(parts[1]["inline_data"]["data"]) == b"raw-audio"


async def test_generate_raises_on_malformed_response(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"candidates": []}))
    with pytest.raises(gemini.GeminiError) as exc_info:
        await gemini.generate(api_key="key", model="m", prompt="p", tools=_NOTE_TOOL)
    assert exc_info.value.status_code is None
    assert exc_info.value.is_retryable  # no status code (couldn't even reach a verdict) -> worth retrying


async def test_generate_caps_output_tokens_and_leaves_thinking_alone(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _response_with_calls([])

    _patch_client(monkeypatch, handler)
    await gemini.generate(api_key="key", model="m", prompt="p", tools=_NOTE_TOOL)

    config = captured["body"]["generationConfig"]
    assert config["maxOutputTokens"] == gemini.MAX_OUTPUT_TOKENS
    assert "thinkingConfig" not in config  # forcing it to 0 made Gemini 3.x outputs worse, not faster


async def test_generate_wraps_http_status_error_with_code(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(503, text="overloaded"))
    with pytest.raises(gemini.GeminiError) as exc_info:
        await gemini.generate(api_key="key", model="m", prompt="p", tools=_NOTE_TOOL)
    assert exc_info.value.status_code == 503
    assert exc_info.value.is_retryable


async def test_generate_wraps_non_retryable_client_error(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(404, text="not found"))
    with pytest.raises(gemini.GeminiError) as exc_info:
        await gemini.generate(api_key="key", model="m", prompt="p", tools=_NOTE_TOOL)
    assert exc_info.value.status_code == 404
    assert not exc_info.value.is_retryable


async def test_answer_text_returns_plain_text_with_no_tools(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "You have no events today."}]}}]})

    _patch_client(monkeypatch, handler)
    result = await gemini.answer_text(api_key="key", model="m", prompt="What's on today?")

    assert "tools" not in captured["body"]
    assert captured["body"]["contents"][0]["parts"] == [{"text": "What's on today?"}]
    assert result == "You have no events today."


async def test_answer_text_raises_on_malformed_response(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"candidates": []}))
    with pytest.raises(gemini.GeminiError):
        await gemini.answer_text(api_key="key", model="m", prompt="p")
