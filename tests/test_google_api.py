import json

import httpx

from kibo.clients import google_api

_RealAsyncClient = httpx.AsyncClient


def _patch_client(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        google_api.httpx,
        "AsyncClient",
        lambda **kwargs: _RealAsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_build_authorization_url_includes_state_and_scopes():
    url = google_api.build_authorization_url(
        client_id="cid", redirect_uri="http://localhost:8000/oauth/google/callback", state="abc123"
    )
    assert url.startswith(google_api.AUTH_URL)
    assert "state=abc123" in url
    assert "client_id=cid" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url


async def test_exchange_code_returns_token_response(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "oauth2.googleapis.com/token" in str(request.url)
        return httpx.Response(
            200,
            json={
                "access_token": "access-123",
                "refresh_token": "refresh-456",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/calendar.events",
            },
        )

    _patch_client(monkeypatch, handler)
    token = await google_api.exchange_code(
        client_id="cid", client_secret="secret", redirect_uri="http://x/callback", code="code-1"
    )
    assert token.access_token == "access-123"
    assert token.refresh_token == "refresh-456"
    assert token.expires_in == 3600


async def test_refresh_access_token_returns_access_token(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"access_token": "new-access"}))
    access_token = await google_api.refresh_access_token(
        client_id="cid", client_secret="secret", refresh_token="refresh-456"
    )
    assert access_token == "new-access"


async def test_list_events_returns_items(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "calendar/v3/calendars/primary/events" in str(request.url)
        assert request.headers["Authorization"] == "Bearer access-123"
        return httpx.Response(200, json={"items": [{"summary": "Meeting"}]})

    _patch_client(monkeypatch, handler)
    items = await google_api.list_events("access-123", time_min="2026-01-01T00:00:00", time_max="2026-01-02T00:00:00")
    assert items == [{"summary": "Meeting"}]


async def test_list_tasks_returns_items(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"items": [{"id": "1", "title": "Buy milk"}]}))
    items = await google_api.list_tasks("access-123")
    assert items == [{"id": "1", "title": "Buy milk"}]


async def test_insert_task_posts_title(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert json.loads(request.content) == {"title": "New task"}
        return httpx.Response(200, json={"id": "2", "title": "New task"})

    _patch_client(monkeypatch, handler)
    result = await google_api.insert_task("access-123", title="New task")
    assert result["id"] == "2"


async def test_insert_task_targets_given_list_and_sends_due(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/lists/my-list/tasks" in str(request.url)
        assert json.loads(request.content) == {"title": "New task", "due": "2026-10-04T00:00:00.000Z"}
        return httpx.Response(200, json={"id": "2", "title": "New task"})

    _patch_client(monkeypatch, handler)
    await google_api.insert_task("access-123", title="New task", tasklist_id="my-list", due="2026-10-04T00:00:00.000Z")


async def test_list_tasklists_returns_items(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"items": [{"id": "l1", "title": "Matemàtiques"}]}))
    items = await google_api.list_tasklists("access-123")
    assert items == [{"id": "l1", "title": "Matemàtiques"}]


async def test_complete_task_patches_status(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path.endswith("/task-1")
        return httpx.Response(200, json={"id": "task-1", "status": "completed"})

    _patch_client(monkeypatch, handler)
    result = await google_api.complete_task("access-123", task_id="task-1")
    assert result["status"] == "completed"
