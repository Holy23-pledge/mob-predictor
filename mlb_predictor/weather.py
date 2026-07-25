"""Game-time weather via Open-Meteo. Decomposes wind along the park's
center-field bearing (blowing out vs in)."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .fetch import get_json

URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat:.2f}"
       "&longitude={lon:.2f}"
       "&hourly=temperature_2m,precipitation_probability,"
       "wind_speed_10m,wind_direction_10m"
       "&timezone={tz}&forecast_days=3")


def game_weather(lat: float, lon: float, tz: str, game_utc: str,
                 cf_bearing: float) -> dict | None:
    try:
        dt = datetime.fromisoformat(game_utc.replace("Z", "+00:00"))
        local = _to_local(dt, tz)
        data = get_json(URL.format(lat=lat, lon=lon, tz=tz.replace("/", "%2F")))
        hours = data["hourly"]["time"]
        target = local.strftime("%Y-%m-%dT%H:00")
        idx = hours.index(target) if target in hours else min(
            range(len(hours)), key=lambda i: abs(_hour_of(hours[i]) - local.hour))
        h = data["hourly"]
        wind_speed = h["wind_speed_10m"][idx] / 1.60934      # km/h -> mph
        wind_from = h["wind_direction_10m"][idx]
        temp_f = h["temperature_2m"][idx] * 9 / 5 + 32       # C -> F
        toward = (wind_from + 180) % 360
        out_component = wind_speed * math.cos(math.radians(toward - cf_bearing))
        return {
            "local_time": local.strftime("%Y-%m-%d %H:%M"),
            "temp_f": temp_f,
            "precip_prob": h["precipitation_probability"][idx],
            "wind_mph": wind_speed,
            "wind_from_deg": wind_from,
            "wind_out_mph": round(out_component, 1),
            "wind_dir_label": _compass(wind_from),
        }
    except Exception:
        return None


def _to_local(dt: datetime, tz: str) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo(tz))
    except Exception:
        return dt.astimezone(timezone.utc)


def _hour_of(iso: str) -> int:
    return int(iso[11:13])


def _compass(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]
