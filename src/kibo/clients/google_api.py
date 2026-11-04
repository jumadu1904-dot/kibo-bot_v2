"""Thin httpx wrapper around Google's OAuth2, Calendar v3 and Tasks v1 REST
APIs — no google-api-python-client, to stay consistent with the rest of the
project (see clients/open_meteo.py). Callers (kibo.services.google_auth,
kibo.services.calendar, kibo.services.tasks) hold the access token and pass
it in; this module only knows how to shape the HTTP calls."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
TASKLISTS_URL = "https://tasks.googleapis.com/tasks/v1/users/@me/lists"


def _calendar_events_url(calendar_id: str) -> str:
    # Calendar ids can be email-like (shared calendars) or contain "#" (the
    # holiday/birthdays ones) — both need escaping to be a valid path segment.
    return f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events"


def _tasks_url(tasklist_id: str) -> str:
    return f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks",
]


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # otherwise Google only returns a refresh_token on first-ever consent
        "state": state,
    }
    return f"{AUTH_URL}?{httpx.QueryParams(params)}"


async def exchange_code(*, client_id: str, client_secret: str, redirect_uri: str, code: str) -> TokenResponse:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        data = response.json()
    return TokenResponse(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_in=data["expires_in"],
        scope=data.get("scope", ""),
    )


async def refresh_access_token(*, client_id: str, client_secret: str, refresh_token: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()
    return data["access_token"]


async def revoke_token(token: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(REVOKE_URL, params={"token": token})


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def list_calendars(access_token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(CALENDAR_LIST_URL, headers=_auth_headers(access_token))
        response.raise_for_status()
        data = response.json()
    return data.get("items", [])


async def list_events(
    access_token: str, *, calendar_id: str = "primary", time_min: str, time_max: str
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            _calendar_events_url(calendar_id),
            headers=_auth_headers(access_token),
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        response.raise_for_status()
        data = response.json()
    return data.get("items", [])


async def insert_event(access_token: str, *, calendar_id: str = "primary", body: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            _calendar_events_url(calendar_id),
            headers=_auth_headers(access_token),
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def update_event(
    access_token: str, *, calendar_id: str = "primary", event_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{_calendar_events_url(calendar_id)}/{event_id}",
            headers=_auth_headers(access_token),
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def delete_event(access_token: str, *, calendar_id: str = "primary", event_id: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.delete(
            f"{_calendar_events_url(calendar_id)}/{event_id}",
            headers=_auth_headers(access_token),
        )
        if response.status_code != 404:  # already gone is as good as deleted
            response.raise_for_status()


async def list_tasklists(access_token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(TASKLISTS_URL, headers=_auth_headers(access_token))
        response.raise_for_status()
        data = response.json()
    return data.get("items", [])


async def list_tasks(access_token: str, *, tasklist_id: str = "@default") -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            _tasks_url(tasklist_id),
            headers=_auth_headers(access_token),
            params={"showCompleted": "false"},
        )
        response.raise_for_status()
        data = response.json()
    return data.get("items", [])


async def insert_task(
    access_token: str, *, title: str, tasklist_id: str = "@default", due: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"title": title}
    if due:
        body["due"] = due
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            _tasks_url(tasklist_id),
            headers=_auth_headers(access_token),
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def complete_task(access_token: str, *, task_id: str, tasklist_id: str = "@default") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{_tasks_url(tasklist_id)}/{task_id}",
            headers=_auth_headers(access_token),
            json={"status": "completed"},
        )
        response.raise_for_status()
        return response.json()
