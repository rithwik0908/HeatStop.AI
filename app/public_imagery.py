from __future__ import annotations

from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from app.config import IMAGES_DIR, settings
from app.vision import _find_image_path


MAPILLARY_DEMO_TOKEN = "MLY|26275324248758064|7819d63bee8179a083cdd76e20557967"
MAPILLARY_GRAPH_URL = "https://graph.mapillary.com/images"
USER_AGENT = {"User-Agent": "HeatStop-AI-MVP/1.0 (hackathon-demo)"}


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6_371_000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_m * atan2(sqrt(a), sqrt(1 - a))


def _bbox_for_radius(lat: float, lon: float, radius_m: float) -> str:
    lat_delta = radius_m / 111_320
    lon_scale = max(cos(radians(lat)), 0.01)
    lon_delta = radius_m / (111_320 * lon_scale)
    return f"{lon - lon_delta},{lat - lat_delta},{lon + lon_delta},{lat + lat_delta}"


def _mapillary_token() -> tuple[str | None, str | None]:
    if settings.mapillary_access_token:
        return settings.mapillary_access_token, "env"
    if settings.use_mapillary_demo_token:
        return MAPILLARY_DEMO_TOKEN, "official_demo"
    return None, None


def _base_row(stop_id: str) -> dict[str, Any]:
    return {
        "stop_id": stop_id,
        "resolved_image_path": None,
        "image_provider": None,
        "image_source_url": None,
        "image_attribution_url": None,
        "image_author": None,
        "image_license": None,
        "image_capture_date": None,
        "image_distance_m": None,
        "image_fetch_status": None,
        "display_image_provider": None,
        "display_image_source_url": None,
        "display_image_attribution_url": None,
        "display_image_author": None,
        "display_image_license": None,
        "display_image_capture_date": None,
        "display_image_distance_m": None,
        "display_image_fetch_status": None,
        "display_image_kind": None,
    }


def _copy_analysis_to_display(row: dict[str, Any]) -> dict[str, Any]:
    row["display_image_provider"] = row.get("image_provider")
    row["display_image_source_url"] = row.get("image_source_url")
    row["display_image_attribution_url"] = row.get("image_attribution_url")
    row["display_image_author"] = row.get("image_author")
    row["display_image_license"] = row.get("image_license")
    row["display_image_capture_date"] = row.get("image_capture_date")
    row["display_image_distance_m"] = row.get("image_distance_m")
    row["display_image_fetch_status"] = row.get("image_fetch_status")
    row["display_image_kind"] = "local" if row.get("resolved_image_path") else "remote"
    return row


def _download_image(url: str, destination: Path, force: bool = False) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        return destination
    response = requests.get(url, headers=USER_AGENT, stream=True, timeout=60)
    response.raise_for_status()
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=512 * 1024):
            if chunk:
                handle.write(chunk)
    return destination


def _search_mapillary_images(lat: float, lon: float, token: str) -> list[dict[str, Any]]:
    search_radius_m = max(settings.public_imagery_radius_m * 2, 60)
    params = {
        "access_token": token,
        "bbox": _bbox_for_radius(lat, lon, search_radius_m),
        "fields": "id,captured_at,computed_geometry,thumb_1024_url,thumb_2048_url",
        "limit": 50,
    }
    response = requests.get(MAPILLARY_GRAPH_URL, params=params, headers=USER_AGENT, timeout=30)
    response.raise_for_status()
    return response.json().get("data", [])


def _fetch_mapillary_detail(image_id: str, token: str) -> dict[str, Any]:
    fields = "captured_at,thumb_1024_url,thumb_2048_url,creator"
    response = requests.get(
        f"https://graph.mapillary.com/{image_id}",
        params={"access_token": token, "fields": fields},
        headers=USER_AGENT,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _find_latest_mapillary_image(stop_id: str, lat: float, lon: float, token: str) -> dict[str, Any]:
    row = _base_row(stop_id)
    try:
        data = _search_mapillary_images(lat, lon, token)
    except requests.RequestException as exc:
        row["image_fetch_status"] = f"mapillary request failed: {exc.__class__.__name__}"
        return _copy_analysis_to_display(row)

    candidates: list[dict[str, Any]] = []
    for item in data:
        geometry = item.get("computed_geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) != 2:
            continue
        image_id = item.get("id")
        captured_at = item.get("captured_at")
        if not image_id or captured_at is None:
            continue
        image_lon, image_lat = float(coords[0]), float(coords[1])
        distance_m = _distance_meters(lat, lon, image_lat, image_lon)
        if distance_m > settings.public_imagery_radius_m:
            continue
        candidates.append(
            {
                "image_id": str(image_id),
                "captured_at": int(captured_at),
                "distance_m": round(distance_m, 1),
            }
        )

    if not candidates:
        row["image_fetch_status"] = "no nearby public image found"
        return _copy_analysis_to_display(row)

    best = sorted(candidates, key=lambda item: (-item["captured_at"], item["distance_m"]))[0]
    try:
        detail = _fetch_mapillary_detail(best["image_id"], token)
    except requests.RequestException as exc:
        row["image_fetch_status"] = f"mapillary detail failed: {exc.__class__.__name__}"
        return _copy_analysis_to_display(row)

    image_url = detail.get("thumb_1024_url") or detail.get("thumb_2048_url")
    if not image_url:
        row["image_fetch_status"] = "mapillary image missing thumbnail"
        return _copy_analysis_to_display(row)

    image_path = _download_image(image_url, IMAGES_DIR / f"mapillary_{stop_id}.jpg")
    captured_at = datetime.fromtimestamp(best["captured_at"] / 1000, tz=timezone.utc).date().isoformat()
    creator = detail.get("creator", {}) or {}

    row.update(
        {
            "resolved_image_path": str(image_path),
            "image_provider": "Mapillary",
            "image_source_url": image_url,
            "image_attribution_url": f"https://www.mapillary.com/app/?pKey={best['image_id']}",
            "image_author": creator.get("username"),
            "image_license": "Mapillary Terms of Use",
            "image_capture_date": captured_at,
            "image_distance_m": best["distance_m"],
            "image_fetch_status": "downloaded public image",
        }
    )
    return _copy_analysis_to_display(row)


def attach_public_imagery(stops_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    token, _ = _mapillary_token()

    for stop in stops_df.to_dict(orient="records"):
        stop_id = str(stop["stop_id"])
        local_path = _find_image_path(stop_id, IMAGES_DIR)
        if local_path is not None:
            row = _base_row(stop_id)
            row.update(
                {
                    "resolved_image_path": str(local_path),
                    "image_provider": "Local file",
                    "image_fetch_status": "local file present",
                }
            )
            rows.append(_copy_analysis_to_display(row))
            continue

        if not settings.enable_public_imagery:
            row = _base_row(stop_id)
            row["image_fetch_status"] = "public imagery disabled"
            rows.append(_copy_analysis_to_display(row))
            continue

        if not token:
            row = _base_row(stop_id)
            row["image_fetch_status"] = "no public imagery token configured"
            rows.append(_copy_analysis_to_display(row))
            continue

        rows.append(_find_latest_mapillary_image(stop_id, float(stop["stop_lat"]), float(stop["stop_lon"]), token))

    imagery_df = pd.DataFrame(rows)
    return stops_df.merge(imagery_df, on="stop_id", how="left")
