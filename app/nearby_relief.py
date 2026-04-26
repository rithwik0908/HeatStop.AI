from __future__ import annotations

import math
from typing import Any

import pandas as pd
import requests

from app.config import settings


SOURCE_LABEL = "OpenStreetMap / Overpass API"
SOURCE_URL = "https://overpass-api.de/"
USER_AGENT = {"User-Agent": "HeatStop-AI-MVP/1.0 (nearby-relief)"}

PLACE_SPECS = [
    {
        "query": 'nwr["amenity"="library"]',
        "category": "Library",
        "kind": "indoor_public_space",
        "usefulness": "Indoor public space with seating and shade.",
        "priority": 6,
    },
    {
        "query": 'nwr["amenity"="community_centre"]',
        "category": "Community center",
        "kind": "indoor_public_space",
        "usefulness": "Indoor public space that may offer seating and cooling relief.",
        "priority": 5,
    },
    {
        "query": 'nwr["amenity"="pharmacy"]',
        "category": "Pharmacy",
        "kind": "indoor_service",
        "usefulness": "Indoor stop for water, cooling, and basic supplies.",
        "priority": 5,
    },
    {
        "query": 'nwr["amenity"="cafe"]',
        "category": "Cafe",
        "kind": "indoor_seating",
        "usefulness": "Indoor seating and a short cooling break while waiting.",
        "priority": 4,
    },
    {
        "query": 'nwr["amenity"="toilets"]',
        "category": "Public restroom",
        "kind": "restroom",
        "usefulness": "Useful for restroom access during a longer wait.",
        "priority": 3,
    },
    {
        "query": 'nwr["amenity"="drinking_water"]',
        "category": "Drinking water",
        "kind": "water_access",
        "usefulness": "Useful for hydration while waiting in heat.",
        "priority": 3,
    },
    {
        "query": 'nwr["leisure"="park"]',
        "category": "Park / green space",
        "kind": "outdoor_shade",
        "usefulness": "Potential outdoor shade or greener relief if indoor options are limited.",
        "priority": 2,
    },
]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _walking_minutes(distance_m: float) -> int:
    return max(int(math.ceil(distance_m / max(settings.rider_walking_speed_m_per_min, 1.0))), 1)


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    blocks = "\n".join(f"  {spec['query']}(around:{radius_m},{lat},{lon});" for spec in PLACE_SPECS)
    return f"""
[out:json][timeout:20];
(
{blocks}
);
out center;
""".strip()


def _element_lat_lon(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None, None


def _spec_for_element(element: dict[str, Any]) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    amenity = tags.get("amenity")
    leisure = tags.get("leisure")
    for spec in PLACE_SPECS:
        if f'"amenity"="{amenity}"' in spec["query"] or f'"leisure"="{leisure}"' in spec["query"]:
            return spec
    return None


def fetch_nearby_relief_places(stop_lat: float, stop_lon: float) -> dict[str, Any]:
    fetched_at = pd.Timestamp.now(tz="UTC").isoformat()
    try:
        response = requests.get(
            settings.relief_places_base_url,
            params={"data": _overpass_query(stop_lat, stop_lon, settings.relief_search_radius_m)},
            headers=USER_AGENT,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return {
            "status": "error",
            "message": f"Nearby relief places are unavailable right now: {exc}",
            "source_label": SOURCE_LABEL,
            "source_url": SOURCE_URL,
            "fetched_at": fetched_at,
            "items": [],
        }
    except ValueError:
        return {
            "status": "error",
            "message": "Nearby relief places returned an unreadable response.",
            "source_label": SOURCE_LABEL,
            "source_url": SOURCE_URL,
            "fetched_at": fetched_at,
            "items": [],
        }

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for element in payload.get("elements", []):
        spec = _spec_for_element(element)
        if spec is None:
            continue
        lat, lon = _element_lat_lon(element)
        if lat is None or lon is None:
            continue
        distance_m = round(_haversine_m(stop_lat, stop_lon, lat, lon), 1)
        tags = element.get("tags") or {}
        name = str(tags.get("name") or "").strip()
        if not name:
            name = spec["category"]
        dedupe_key = (name.lower(), spec["category"], int(distance_m))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            {
                "name": name,
                "category": spec["category"],
                "kind": spec["kind"],
                "distance_m": distance_m,
                "walking_minutes": _walking_minutes(distance_m),
                "usefulness": spec["usefulness"],
                "provider": SOURCE_LABEL,
                "provider_url": SOURCE_URL,
                "lat": lat,
                "lon": lon,
                "osm_url": f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
                "source_tags": tags,
                "priority": spec["priority"],
            }
        )

    items.sort(key=lambda item: (-item["priority"], item["distance_m"], item["name"].lower()))
    trimmed = items[: settings.relief_max_results]
    status = "ok" if trimmed else "empty"
    return {
        "status": status,
        "message": None if trimmed else "No nearby relief places matched the configured categories near this stop.",
        "source_label": SOURCE_LABEL,
        "source_url": SOURCE_URL,
        "fetched_at": fetched_at,
        "items": trimmed,
    }
