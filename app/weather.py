"""Weather tool — real climate for a study-destination city.

A student weighing an offer abroad genuinely cares what the weather is like in
Berlin, Budapest, or Abu Dhabi. This uses Open-Meteo (free, no API key): first
geocode the city name, then read the current conditions.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import FORECAST_BASE, GEOCODE_BASE, REQUEST_TIMEOUT

# WMO weather-interpretation codes -> short human text.
_WMO: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snowfall",
    73: "moderate snowfall",
    75: "heavy snowfall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class WeatherError(Exception):
    """The city could not be found or the weather service was unreachable."""


def get_weather(city: str) -> dict[str, Any]:
    """Current weather for `city`. Raises WeatherError if the city is unknown."""
    if not city or not city.strip():
        raise WeatherError("no city name was provided")

    place = _geocode(city.strip())
    forecast = _current(place["latitude"], place["longitude"])
    current = forecast.get("current", {})
    code = int(current.get("weather_code", -1))

    return {
        "city": place.get("name"),
        "country": place.get("country"),
        "temperature_c": current.get("temperature_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "conditions": _WMO.get(code, f"code {code}"),
        "observed_local_time": current.get("time"),
        "timezone": forecast.get("timezone"),
    }


def _geocode(city: str) -> dict[str, Any]:
    try:
        resp = httpx.get(
            GEOCODE_BASE,
            params={"name": city, "count": 1, "language": "en"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results")
    except httpx.HTTPError as exc:
        raise WeatherError(f"geocoding service unreachable: {exc}") from exc
    except ValueError as exc:
        raise WeatherError("geocoding returned a non-JSON response") from exc
    if not results:
        raise WeatherError(f"could not find a city named {city!r}")
    return results[0]


def _current(lat: float, lon: float) -> dict[str, Any]:
    try:
        resp = httpx.get(
            FORECAST_BASE,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise WeatherError(f"weather service unreachable: {exc}") from exc
    except ValueError as exc:
        raise WeatherError("weather service returned a non-JSON response") from exc
