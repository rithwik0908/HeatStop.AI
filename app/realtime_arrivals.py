from __future__ import annotations

import re
from typing import Any

import pandas as pd
import requests

from app.config import settings


SOURCE_LABEL = "MTA Bus Time / SIRI StopMonitoring"
SOURCE_URL = "https://bustime.mta.info/wiki/Developers/SIRIStopMonitoring"
USER_AGENT = {"User-Agent": "HeatStop-AI-MVP/1.0 (rider-copilot)"}


def _normalize_route(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _route_matches(candidate: str, selected_route: str) -> bool:
    if not selected_route:
        return True
    candidate_norm = _normalize_route(candidate)
    selected_norm = _normalize_route(selected_route)
    return bool(candidate_norm and selected_norm and (candidate_norm == selected_norm or candidate_norm.endswith(selected_norm)))


def _parse_eta_minutes(expected_timestamp: str | None, fetched_at: pd.Timestamp) -> int | None:
    if not expected_timestamp:
        return None
    try:
        expected = pd.Timestamp(expected_timestamp)
        if expected.tzinfo is None:
            expected = expected.tz_localize("UTC")
        delta_minutes = (expected - fetched_at).total_seconds() / 60.0
        if delta_minutes < -1:
            return None
        return max(int(round(delta_minutes)), 0)
    except Exception:
        return None


def _parse_arrival_item(visit: dict[str, Any], fetched_at: pd.Timestamp) -> dict[str, Any] | None:
    journey = visit.get("MonitoredVehicleJourney") or {}
    call = journey.get("MonitoredCall") or {}
    route = journey.get("PublishedLineName") or str(journey.get("LineRef") or "").split("_")[-1]
    destination = journey.get("DestinationName")
    expected_timestamp = (
        call.get("ExpectedArrivalTime")
        or call.get("ExpectedDepartureTime")
        or call.get("AimedArrivalTime")
        or call.get("AimedDepartureTime")
    )
    eta_minutes = _parse_eta_minutes(expected_timestamp, fetched_at)
    if not route or eta_minutes is None:
        return None
    return {
        "route": route,
        "destination": destination,
        "eta_minutes": eta_minutes,
        "expected_arrival_timestamp": expected_timestamp,
        "direction_ref": journey.get("DirectionRef"),
        "presentable_distance": (((journey.get("MonitoredCall") or {}).get("Extensions") or {}).get("Distances") or {}).get("PresentableDistance"),
    }


def fetch_stop_arrivals(stop_id: str, route_short_name: str | None = None) -> dict[str, Any]:
    fetched_at = pd.Timestamp.now(tz="UTC")
    if not settings.mta_bus_time_api_key.strip():
        return {
            "status": "unavailable",
            "message": "MTA Bus Time API key is not configured.",
            "source_label": SOURCE_LABEL,
            "source_url": SOURCE_URL,
            "fetched_at": fetched_at.isoformat(),
            "items": [],
            "relevant_items": [],
            "next_arrival": None,
        }

    params = {
        "key": settings.mta_bus_time_api_key,
        "OperatorRef": "MTA",
        "MonitoringRef": str(stop_id),
        "MaximumStopVisits": "6",
    }
    try:
        response = requests.get(
            settings.mta_bus_time_base_url,
            params=params,
            headers=USER_AGENT,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return {
            "status": "error",
            "message": f"Real-time arrivals are unavailable right now: {exc}",
            "source_label": SOURCE_LABEL,
            "source_url": SOURCE_URL,
            "fetched_at": fetched_at.isoformat(),
            "items": [],
            "relevant_items": [],
            "next_arrival": None,
        }
    except ValueError:
        return {
            "status": "error",
            "message": "Real-time arrivals returned an unreadable response.",
            "source_label": SOURCE_LABEL,
            "source_url": SOURCE_URL,
            "fetched_at": fetched_at.isoformat(),
            "items": [],
            "relevant_items": [],
            "next_arrival": None,
        }

    service = ((payload.get("Siri") or {}).get("ServiceDelivery") or {})
    response_timestamp = service.get("ResponseTimestamp")
    fetched_reference = fetched_at
    if response_timestamp:
        try:
            fetched_reference = pd.Timestamp(response_timestamp)
            if fetched_reference.tzinfo is None:
                fetched_reference = fetched_reference.tz_localize("UTC")
        except Exception:
            fetched_reference = fetched_at

    deliveries = service.get("StopMonitoringDelivery") or []
    visits = deliveries[0].get("MonitoredStopVisit", []) if deliveries else []
    items: list[dict[str, Any]] = []
    for visit in visits:
        parsed = _parse_arrival_item(visit, fetched_reference)
        if parsed:
            items.append(parsed)

    items.sort(key=lambda item: (item.get("eta_minutes") is None, item.get("eta_minutes", 9999)))
    relevant_items = [item for item in items if _route_matches(item.get("route", ""), route_short_name or "")]
    next_arrival = relevant_items[0] if relevant_items else (items[0] if items else None)

    status = "ok" if items else "empty"
    message = None
    if status == "empty":
        message = "No live arrivals are available for this stop right now."

    return {
        "status": status,
        "message": message,
        "source_label": SOURCE_LABEL,
        "source_url": SOURCE_URL,
        "fetched_at": fetched_at.isoformat(),
        "response_timestamp": response_timestamp,
        "items": items,
        "relevant_items": relevant_items,
        "next_arrival": next_arrival,
    }
