"""Weather block for the daily briefing (see docs/ARCHITECTURE.md F4):
turns clients.open_meteo's current conditions into a short emoji + temperature
line, tolerating Open-Meteo being unreachable (the briefing still sends
without it rather than failing outright)."""

import logging

import httpx

from kibo.clients import open_meteo

logger = logging.getLogger(__name__)

# WMO weather codes (https://open-meteo.com/en/docs), collapsed to a single
# emoji since the briefing needs a one-line summary, not a forecast.
_CODE_EMOJI = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌦️", 56: "🌦️", 57: "🌦️",
    61: "🌧️", 63: "🌧️", 65: "🌧️", 66: "🌧️", 67: "🌧️",
    71: "🌨️", 73: "🌨️", 75: "🌨️", 77: "🌨️",
    80: "🌧️", 81: "🌧️", 82: "🌧️",
    85: "🌨️", 86: "🌨️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}
_DEFAULT_EMOJI = "🌡️"


async def summary(lat: float, lon: float) -> str | None:
    """A one-line "<emoji> <temp>°C" summary, or None if the forecast
    couldn't be fetched."""
    try:
        weather = await open_meteo.current_weather(lat, lon)
    except httpx.HTTPError:
        logger.warning("Failed to fetch current weather", exc_info=True)
        return None
    emoji = _CODE_EMOJI.get(weather.weather_code, _DEFAULT_EMOJI)
    return f"{emoji} {weather.temperature_c:.0f}°C"
