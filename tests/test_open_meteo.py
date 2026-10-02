import httpx

from kibo.clients import open_meteo

_RealAsyncClient = httpx.AsyncClient


def _patch_client(monkeypatch, handler) -> None:
    # `open_meteo.httpx` is the same module object as `httpx` here, so
    # patching `AsyncClient` on it patches it everywhere — capture the real
    # class first or the lambda below would call itself.
    monkeypatch.setattr(
        open_meteo.httpx,
        "AsyncClient",
        lambda **kwargs: _RealAsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_geocode_city_returns_first_match(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "geocoding-api" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Barcelona",
                        "country": "Spain",
                        "latitude": 41.38,
                        "longitude": 2.18,
                        "timezone": "Europe/Madrid",
                    }
                ]
            },
        )

    _patch_client(monkeypatch, handler)
    match = await open_meteo.geocode_city("Barcelona")
    assert match == open_meteo.CityMatch(
        name="Barcelona", country="Spain", lat=41.38, lon=2.18, timezone="Europe/Madrid"
    )


async def test_geocode_city_no_results(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"results": []}))
    assert await open_meteo.geocode_city("Nowhereville") is None


async def test_timezone_for(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.open-meteo.com" in str(request.url)
        return httpx.Response(200, json={"timezone": "Europe/Madrid", "current": {}})

    _patch_client(monkeypatch, handler)
    assert await open_meteo.timezone_for(41.38, 2.18) == "Europe/Madrid"
