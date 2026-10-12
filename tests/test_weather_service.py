import httpx

from kibo.clients.open_meteo import CurrentWeather
from kibo.services import weather


async def test_summary_formats_emoji_and_temperature(monkeypatch):
    async def fake_current_weather(lat, lon):
        return CurrentWeather(temperature_c=18.4, weather_code=0)

    monkeypatch.setattr(weather.open_meteo, "current_weather", fake_current_weather)
    assert await weather.summary(41.38, 2.18) == "☀️ 18°C"


async def test_summary_unknown_code_falls_back_to_default_emoji(monkeypatch):
    async def fake_current_weather(lat, lon):
        return CurrentWeather(temperature_c=10.0, weather_code=999)

    monkeypatch.setattr(weather.open_meteo, "current_weather", fake_current_weather)
    assert await weather.summary(41.38, 2.18) == "🌡️ 10°C"


async def test_summary_returns_none_when_forecast_unreachable(monkeypatch):
    async def fake_current_weather(lat, lon):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(weather.open_meteo, "current_weather", fake_current_weather)
    assert await weather.summary(41.38, 2.18) is None
