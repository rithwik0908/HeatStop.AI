from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import requests

from app.config import settings


USER_AGENT = {"User-Agent": "HeatStop-AI-MVP/1.0 (hackathon-demo)"}
WEATHER_SOURCE_LABEL = "NWS / weather.gov"
WEATHER_METRIC_LABELS = {
    "heatIndex": "Heat index",
    "apparentTemperature": "Feels-like temperature",
    "temperature": "Air temperature",
}


def _request(url: str, **kwargs) -> requests.Response:
    response = requests.get(url, headers=USER_AGENT, timeout=kwargs.pop("timeout", 60), **kwargs)
    response.raise_for_status()
    return response


def _safe_iso_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return pd.Timestamp(value).isoformat()
    except Exception:
        return value


def metric_display_name(metric_used: str | None) -> str:
    return WEATHER_METRIC_LABELS.get(str(metric_used), "Heat snapshot")


def weather_card_label(metric_used: str | None) -> str:
    if metric_used == "heatIndex":
        return "Current corridor heat index (°F)"
    return "Near-term corridor heat snapshot (°F)"


def fetch_weather_snapshot(lat: float, lon: float, horizon_hours: int | None = None) -> dict[str, Any]:
    horizon_hours = horizon_hours or settings.weather_horizon_hours
    point_url = f"https://api.weather.gov/points/{lat},{lon}"
    point_response = _request(point_url).json()
    grid_url = point_response["properties"]["forecastGridData"]
    grid = _request(grid_url).json()["properties"]

    fetched_at = datetime.now().astimezone()
    horizon = fetched_at + timedelta(hours=horizon_hours)

    def _extract_max(series_name: str) -> float | None:
        values = grid.get(series_name, {}).get("values", [])
        candidates = []
        for item in values:
            start = item["validTime"].split("/")[0]
            timestamp = pd.Timestamp(start)
            if timestamp.tz_convert(fetched_at.tzinfo) < fetched_at or timestamp.tz_convert(fetched_at.tzinfo) > horizon:
                continue
            if item["value"] is not None:
                candidates.append(float(item["value"]))
        if not candidates:
            return None
        return max(candidates)

    max_heat_c = _extract_max("heatIndex")
    max_apparent_c = _extract_max("apparentTemperature")
    max_temp_c = _extract_max("temperature")

    chosen_c = max_heat_c if max_heat_c is not None else (max_apparent_c if max_apparent_c is not None else max_temp_c)
    chosen_label = "heatIndex" if max_heat_c is not None else ("apparentTemperature" if max_apparent_c is not None else "temperature")
    chosen_f = None if chosen_c is None else round((chosen_c * 9 / 5) + 32, 1)
    heat_burden_score = None if chosen_f is None else round(float(np.clip((chosen_f - 80.0) / 25.0, 0, 1)), 3)

    return {
        "weather_point_lat": lat,
        "weather_point_lon": lon,
        "weather_metric_used": chosen_label,
        "weather_metric_display": metric_display_name(chosen_label),
        "max_weather_value_f": chosen_f,
        "heat_burden_score": heat_burden_score,
        "weather_source": grid_url,
        "weather_source_label": WEATHER_SOURCE_LABEL,
        "weather_point_url": point_url,
        "weather_updated_at": _safe_iso_timestamp(grid.get("updateTime")),
        "weather_refreshed_at": fetched_at.isoformat(),
        "weather_horizon_hours": int(horizon_hours),
        "weather_summary": (
            None
            if chosen_f is None
            else f"{metric_display_name(chosen_label)} forecast used for the next {horizon_hours} hours"
        ),
    }


def apply_weather_snapshot(stops_df: pd.DataFrame, weather_snapshot: dict[str, Any]) -> pd.DataFrame:
    updated = stops_df.copy()
    for key, value in weather_snapshot.items():
        updated[key] = value
    return updated


def weather_summary_from_frame(stops_df: pd.DataFrame, fallback_updated_at: str | None = None) -> dict[str, Any]:
    if stops_df.empty:
        return {}

    first = stops_df.iloc[0]
    metric_used = first.get("weather_metric_used")
    value_f = first.get("max_weather_value_f")
    updated_at = first.get("weather_updated_at") or fallback_updated_at
    refreshed_at = first.get("weather_refreshed_at") or fallback_updated_at
    point_url = first.get("weather_point_url")
    if not point_url and pd.notna(first.get("weather_point_lat")) and pd.notna(first.get("weather_point_lon")):
        point_url = f"https://api.weather.gov/points/{first.get('weather_point_lat')},{first.get('weather_point_lon')}"
    return {
        "label": weather_card_label(metric_used),
        "metric_used": metric_used,
        "metric_display": first.get("weather_metric_display") or metric_display_name(metric_used),
        "value_f": None if pd.isna(value_f) else float(value_f),
        "heat_burden_score": None if pd.isna(first.get("heat_burden_score")) else float(first.get("heat_burden_score")),
        "source_label": first.get("weather_source_label") or WEATHER_SOURCE_LABEL,
        "source_url": first.get("weather_source"),
        "point_url": point_url,
        "updated_at": updated_at,
        "refreshed_at": refreshed_at,
        "horizon_hours": None if pd.isna(first.get("weather_horizon_hours")) else int(first.get("weather_horizon_hours")),
        "summary": first.get("weather_summary"),
    }
