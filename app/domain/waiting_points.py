from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd


DEFAULT_WAITING_POINT_TYPE = "bus_stop"
DEFAULT_WAITING_ZONE_TYPE = "corridor"
DEFAULT_SOURCE_ADAPTER = "mta_bus_gtfs"


@dataclass(frozen=True)
class WaitingZoneMembership:
    waiting_zone_id: str | None
    waiting_zone_name: str | None
    waiting_zone_type: str = DEFAULT_WAITING_ZONE_TYPE


@dataclass(frozen=True)
class WaitingPoint:
    waiting_point_id: str
    waiting_point_name: str
    waiting_point_type: str = DEFAULT_WAITING_POINT_TYPE
    waiting_point_lat: float | None = None
    waiting_point_lon: float | None = None
    source_record_id: str | None = None
    source_adapter: str = DEFAULT_SOURCE_ADAPTER
    route_short_name: str | None = None
    direction_id: int | None = None
    waiting_zone_id: str | None = None
    waiting_zone_name: str | None = None
    waiting_zone_type: str = DEFAULT_WAITING_ZONE_TYPE


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def canonical_waiting_point_record(
    record: Mapping[str, Any],
    *,
    waiting_point_type: str = DEFAULT_WAITING_POINT_TYPE,
    waiting_zone_type: str = DEFAULT_WAITING_ZONE_TYPE,
    source_adapter: str = DEFAULT_SOURCE_ADAPTER,
) -> dict[str, Any]:
    waiting_point_id = str(record.get("waiting_point_id") or record.get("stop_id") or "")
    waiting_point_name = str(record.get("waiting_point_name") or record.get("stop_name") or "")
    waiting_zone_id = record.get("waiting_zone_id") or record.get("corridor_id")
    waiting_zone_name = record.get("waiting_zone_name") or record.get("corridor_name")
    return {
        "waiting_point_id": waiting_point_id,
        "waiting_point_name": waiting_point_name,
        "waiting_point_type": record.get("waiting_point_type") or waiting_point_type,
        "waiting_point_lat": _safe_float(record.get("waiting_point_lat", record.get("stop_lat"))),
        "waiting_point_lon": _safe_float(record.get("waiting_point_lon", record.get("stop_lon"))),
        "waiting_zone_id": waiting_zone_id,
        "waiting_zone_name": waiting_zone_name,
        "waiting_zone_type": record.get("waiting_zone_type") or waiting_zone_type,
        "source_record_id": record.get("source_record_id") or record.get("stop_id") or waiting_point_id,
        "source_adapter": record.get("source_adapter") or source_adapter,
    }


def waiting_point_from_record(
    record: Mapping[str, Any],
    *,
    waiting_point_type: str = DEFAULT_WAITING_POINT_TYPE,
    waiting_zone_type: str = DEFAULT_WAITING_ZONE_TYPE,
    source_adapter: str = DEFAULT_SOURCE_ADAPTER,
) -> WaitingPoint:
    normalized = canonical_waiting_point_record(
        record,
        waiting_point_type=waiting_point_type,
        waiting_zone_type=waiting_zone_type,
        source_adapter=source_adapter,
    )
    return WaitingPoint(
        waiting_point_id=str(normalized["waiting_point_id"]),
        waiting_point_name=str(normalized["waiting_point_name"]),
        waiting_point_type=str(normalized["waiting_point_type"]),
        waiting_point_lat=normalized.get("waiting_point_lat"),
        waiting_point_lon=normalized.get("waiting_point_lon"),
        source_record_id=str(normalized.get("source_record_id") or ""),
        source_adapter=str(normalized["source_adapter"]),
        route_short_name=record.get("route_short_name"),
        direction_id=record.get("direction_id"),
        waiting_zone_id=normalized.get("waiting_zone_id"),
        waiting_zone_name=normalized.get("waiting_zone_name"),
        waiting_zone_type=str(normalized["waiting_zone_type"]),
    )


def add_waiting_point_aliases(
    frame: pd.DataFrame,
    *,
    waiting_point_type: str = DEFAULT_WAITING_POINT_TYPE,
    waiting_zone_type: str = DEFAULT_WAITING_ZONE_TYPE,
    source_adapter: str = DEFAULT_SOURCE_ADAPTER,
) -> pd.DataFrame:
    updated = frame.copy()
    if "waiting_point_id" not in updated.columns and "stop_id" in updated.columns:
        updated["waiting_point_id"] = updated["stop_id"].astype(str)
    if "waiting_point_name" not in updated.columns and "stop_name" in updated.columns:
        updated["waiting_point_name"] = updated["stop_name"].astype(str)
    if "waiting_point_lat" not in updated.columns and "stop_lat" in updated.columns:
        updated["waiting_point_lat"] = pd.to_numeric(updated["stop_lat"], errors="coerce")
    if "waiting_point_lon" not in updated.columns and "stop_lon" in updated.columns:
        updated["waiting_point_lon"] = pd.to_numeric(updated["stop_lon"], errors="coerce")
    updated["waiting_point_type"] = updated.get("waiting_point_type", waiting_point_type)
    if "corridor_id" in updated.columns and "waiting_zone_id" not in updated.columns:
        updated["waiting_zone_id"] = updated["corridor_id"]
    if "corridor_name" in updated.columns and "waiting_zone_name" not in updated.columns:
        updated["waiting_zone_name"] = updated["corridor_name"]
    updated["waiting_zone_type"] = updated.get("waiting_zone_type", waiting_zone_type)
    if "source_record_id" not in updated.columns and "stop_id" in updated.columns:
        updated["source_record_id"] = updated["stop_id"].astype(str)
    updated["source_adapter"] = updated.get("source_adapter", source_adapter)
    return updated
