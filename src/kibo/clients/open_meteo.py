"""Open-Meteo: geocoding by city name and timezone lookup by coordinates.
No API key needed. Used during onboarding/settings to resolve a user's
location and IANA timezone (see docs/ARCHITECTURE.md)."""

import asyncio
from dataclasses import dataclass

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


async def _get(client: httpx.AsyncClient, url: str, *, params: dict) -> httpx.Response:
    """GET with one retry on 429 — Render's free tier shares its outbound
    IP across many other services, so Open-Meteo's per-IP rate limit can
    trip from traffic that isn't even ours."""
    response = await client.get(url, params=params)
    if response.status_code == 429:
        await asyncio.sleep(2)
        response = await client.get(url, params=params)
    response.raise_for_status()
    return response


@dataclass
class CityMatch:
    name: str
    country: str
    lat: float
    lon: float
    timezone: str


@dataclass
class CurrentWeather:
    temperature_c: float
    weather_code: int  # WMO code, see kibo.services.weather


async def geocode_city(name: str) -> CityMatch | None:
    """Look up a city by free-text name. Returns the best (first) match,
    or None if Open-Meteo found nothing."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await _get(client, GEOCODING_URL, params={"name": name, "count": 1})
        data = response.json()
    results = data.get("results") or []
    if not results:
        return None
    result = results[0]
    return CityMatch(
        name=result["name"],
        country=result.get("country", ""),
        lat=result["latitude"],
        lon=result["longitude"],
        timezone=result["timezone"],
    )


async def timezone_for(lat: float, lon: float) -> str:
    """Resolve the IANA timezone for a pair of coordinates (used when the
    user shares their GPS location instead of typing a city name)."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await _get(
            client,
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "timezone": "auto",
                "current": "temperature_2m",
            },
        )
        data = response.json()
    return data["timezone"]


async def current_weather(lat: float, lon: float) -> CurrentWeather:
    """Current temperature and WMO weather code — the weather block of the
    daily briefing (see kibo.services.weather)."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await _get(
            client,
            FORECAST_URL,
            params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code"},
        )
        data = response.json()
    current = data["current"]
    return CurrentWeather(temperature_c=current["temperature_2m"], weather_code=current["weather_code"])
