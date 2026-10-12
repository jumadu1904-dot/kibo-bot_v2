"""Thin httpx wrapper around Gemini's `generateContent` REST endpoint — no
google-genai SDK, to stay consistent with the rest of the project (see
clients/google_api.py, clients/open_meteo.py).

`generate()` uses native function calling (`tools`/`functionCall`), not
`responseSchema` free-form JSON: with a single flat schema shared by every
action type, only "type" could be marked required, and the weaker fallback
model reliably dropped "due_at" from reminders despite the prompt insisting
on it — the model just didn't feel schema-enforced to include it. Each tool
below has its own `required` list that Gemini actually enforces, which
fixed that dead reliably. `toolConfig.mode: "AUTO"` lets a response call
zero, one, or several tools in parallel — exactly the "split into separate
actions, or none" behavior kibo.services.interpreter needs.

`answer_text()` is a plain (no tools) call used for grounded Q&A (see
kibo.bot.handlers.smart_input._answer_query): the caller fetches real
Calendar/Tasks/reminders data first and hands it to the prompt, so the
model answers from that instead of guessing — asking Gemini to answer
"what's on my calendar" directly, with no data, just produces a
plausible-sounding but made-up answer.

We deliberately do NOT force `thinkingConfig.thinkingBudget: 0`: on the
current Gemini 3.x models that made things worse, not faster — with no
scratch space, the model's reasoning leaked straight into argument values
(a garbled title instead of a short one). Each model's own default
thinking budget gave cleaner results in testing, at only a small latency
cost."""

import base64
from typing import Any

import httpx

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_OUTPUT_TOKENS = 2048


class GeminiError(Exception):
    """Raised when a call to Gemini didn't produce usable output — a
    transport/HTTP failure (`status_code` set, see `is_retryable`) or a
    malformed/empty response (`status_code` None, not worth retrying)."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_retryable(self) -> bool:
        """Overloaded (503), rate-limited (429), or a network-level failure
        (no status code at all) — all worth retrying/falling back to a
        different model. Any other 4xx (bad request, invalid key...) will
        just fail the same way again."""
        return self.status_code is None or self.status_code == 429 or 500 <= self.status_code < 600


async def _post(*, api_key: str, model: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{API_BASE}/models/{model}:generateContent",
                params={"key": api_key},
                json=body,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise GeminiError(f"Gemini request failed: {exc}", status_code=exc.response.status_code) from exc
    except httpx.HTTPError as exc:
        raise GeminiError(f"Gemini request failed: {exc}") from exc


def _build_parts(prompt: str, audio_bytes: bytes | None, audio_mime: str | None) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if audio_bytes is not None:
        parts.append(
            {"inline_data": {"mime_type": audio_mime, "data": base64.b64encode(audio_bytes).decode()}}
        )
    return parts


async def generate(
    *,
    api_key: str,
    model: str,
    prompt: str,
    tools: list[dict[str, Any]],
    audio_bytes: bytes | None = None,
    audio_mime: str | None = None,
) -> list[dict[str, Any]]:
    """Call Gemini with `prompt` (plus inline audio if given) and `tools`
    (Gemini function declarations — see kibo.services.interpreter). Returns
    one dict per function call Gemini made, each `{"type": <tool name>,
    **arguments}` — zero, one, or several, in the order Gemini returned
    them. Raises GeminiError (never a raw httpx exception) on any failure."""
    body = {
        "contents": [{"parts": _build_parts(prompt, audio_bytes, audio_mime)}],
        "tools": [{"functionDeclarations": tools}],
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
    }
    data = await _post(api_key=api_key, model=model, body=body)

    try:
        candidate_parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        raise GeminiError(f"Gemini returned no candidates: {data}") from exc

    return [
        {"type": part["functionCall"]["name"], **part["functionCall"].get("args", {})}
        for part in candidate_parts
        if "functionCall" in part
    ]


async def answer_text(*, api_key: str, model: str, prompt: str) -> str:
    """Plain text completion, no tools — see module docstring."""
    body = {
        "contents": [{"parts": _build_parts(prompt, None, None)}],
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
    }
    data = await _post(api_key=api_key, model=model, body=body)

    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part["text"] for part in parts if "text" in part)
    except (KeyError, IndexError) as exc:
        raise GeminiError(f"Gemini returned no candidates: {data}") from exc
