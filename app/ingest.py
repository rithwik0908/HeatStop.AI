from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from app.config import PROCESSED_DIR, RAW_DIR, settings
from app.data_sources import DATA_SOURCES, MANUAL_INPUTS
from app.public_imagery import attach_public_imagery
from app.scoring import score_stops
from app.vision import analyze_stop_images
from app.weather import apply_weather_snapshot, fetch_weather_snapshot, weather_summary_from_frame


USER_AGENT = {"User-Agent": "HeatStop-AI-MVP/1.0 (hackathon-demo)"}
GTFS_URL = "http://web.mta.info/developers/data/nyct/bus/google_transit_manhattan.zip"
SHELTERS_URL = "https://data.cityofnewyork.us/api/views/t4f2-8md7/rows.csv?accessType=DOWNLOAD"
SEATING_URL = "https://data.cityofnewyork.us/resource/esmy-s8q5.csv?$limit=50000"
TREE_URL = "https://data.cityofnewyork.us/resource/uvpi-gqnh.csv"

GTFS_ZIP_PATH = RAW_DIR / "google_transit_manhattan.zip"
SHELTERS_PATH = RAW_DIR / "nyc_bus_stop_shelters.csv"
SEATING_PATH = RAW_DIR / "nyc_seating_locations.csv"
CORRIDORS_DIR = PROCESSED_DIR / "corridors"
CORRIDORS_INDEX_PATH = PROCESSED_DIR / "corridors_index.json"


def _request(url: str, **kwargs) -> requests.Response:
    response = requests.get(url, headers=USER_AGENT, timeout=kwargs.pop("timeout", 60), **kwargs)
    response.raise_for_status()
    return response


def download_file(url: str, destination: Path, force: bool = False) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        return destination
    response = _request(url, stream=True, timeout=120)
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    return destination


def download_required_datasets(force: bool = False) -> dict[str, Path]:
    return {
        "gtfs_zip": download_file(GTFS_URL, GTFS_ZIP_PATH, force=force),
        "shelters_csv": download_file(SHELTERS_URL, SHELTERS_PATH, force=force),
        "seating_csv": download_file(SEATING_URL, SEATING_PATH, force=force),
    }


def _read_gtfs_table(zip_path: Path, member_name: str, dtype: dict | None = None) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member_name) as handle:
            return pd.read_csv(handle, dtype=dtype)


def load_gtfs_tables(zip_path: Path) -> dict[str, pd.DataFrame]:
    return {
        "routes": _read_gtfs_table(zip_path, "routes.txt", dtype=str),
        "trips": _read_gtfs_table(zip_path, "trips.txt", dtype=str),
        "stop_times": _read_gtfs_table(
            zip_path,
            "stop_times.txt",
            dtype={"trip_id": str, "arrival_time": str, "departure_time": str, "stop_id": str, "stop_sequence": int},
        ),
        "stops": _read_gtfs_table(zip_path, "stops.txt", dtype=str),
        "calendar": _read_gtfs_table(zip_path, "calendar.txt", dtype=str),
        "calendar_dates": _read_gtfs_table(zip_path, "calendar_dates.txt", dtype=str),
    }


def _service_date(input_date: str | None = None) -> date:
    if input_date:
        return datetime.strptime(input_date, "%Y-%m-%d").date()
    return date.today()


def get_active_service_ids(calendar: pd.DataFrame, calendar_dates: pd.DataFrame, service_date: date) -> set[str]:
    day_name = service_date.strftime("%A").lower()
    calendar = calendar.copy()
    calendar["start_date"] = pd.to_datetime(calendar["start_date"], format="%Y%m%d")
    calendar["end_date"] = pd.to_datetime(calendar["end_date"], format="%Y%m%d")
    active = calendar[
        (calendar["start_date"].dt.date <= service_date)
        & (calendar["end_date"].dt.date >= service_date)
        & (calendar[day_name] == "1")
    ]
    active_ids = set(active["service_id"].astype(str))

    if not calendar_dates.empty:
        calendar_dates = calendar_dates.copy()
        calendar_dates["date"] = pd.to_datetime(calendar_dates["date"], format="%Y%m%d").dt.date
        exceptions = calendar_dates[calendar_dates["date"] == service_date]
        for _, row in exceptions.iterrows():
            if row["exception_type"] == "1":
                active_ids.add(str(row["service_id"]))
            elif row["exception_type"] == "2":
                active_ids.discard(str(row["service_id"]))
    return active_ids


def gtfs_time_to_seconds(value: str) -> int | None:
    if pd.isna(value) or not str(value).strip():
        return None
    parts = str(value).split(":")
    if len(parts) != 3:
        return None
    hours, minutes, seconds = map(int, parts)
    return hours * 3600 + minutes * 60 + seconds


def _select_route_id(routes: pd.DataFrame, route_short_name: str) -> str:
    exact = routes.loc[routes["route_short_name"] == route_short_name, "route_id"]
    if exact.empty:
        exact = routes.loc[routes["route_id"] == route_short_name, "route_id"]
    if exact.empty:
        available = ", ".join(sorted(routes["route_short_name"].dropna().unique())[:20])
        raise ValueError(f"Route `{route_short_name}` not found in GTFS. Available examples: {available}")
    return str(exact.iloc[0])


def build_route_stop_frame(
    gtfs_tables: dict[str, pd.DataFrame],
    route_short_name: str,
    direction_id: int,
    service_date: date,
    stop_limit: int,
    window_start: str,
    window_end: str,
) -> pd.DataFrame:
    routes = gtfs_tables["routes"]
    trips = gtfs_tables["trips"]
    stop_times = gtfs_tables["stop_times"]
    stops = gtfs_tables["stops"]
    route_id = _select_route_id(routes, route_short_name)
    active_service_ids = get_active_service_ids(gtfs_tables["calendar"], gtfs_tables["calendar_dates"], service_date)

    candidate_trips = trips[
        (trips["route_id"] == route_id)
        & (trips["direction_id"].astype(str) == str(direction_id))
        & (trips["service_id"].astype(str).isin(active_service_ids))
    ]
    if candidate_trips.empty:
        raise ValueError(f"No active trips found for route `{route_short_name}` direction `{direction_id}` on {service_date}.")

    trip_counts = (
        stop_times[stop_times["trip_id"].isin(candidate_trips["trip_id"])]
        .groupby("trip_id")["stop_sequence"]
        .max()
        .sort_values(ascending=False)
    )
    exemplar_trip_id = str(trip_counts.index[0])
    exemplar_trip = candidate_trips.loc[candidate_trips["trip_id"] == exemplar_trip_id].iloc[0]

    exemplar_stops = (
        stop_times.loc[stop_times["trip_id"] == exemplar_trip_id, ["stop_id", "stop_sequence"]]
        .sort_values("stop_sequence")
        .drop_duplicates("stop_id")
        .head(stop_limit)
    )

    stop_lookup = stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]].copy()
    stop_lookup["stop_lat"] = pd.to_numeric(stop_lookup["stop_lat"], errors="coerce")
    stop_lookup["stop_lon"] = pd.to_numeric(stop_lookup["stop_lon"], errors="coerce")

    corridor_stops = exemplar_stops.merge(stop_lookup, on="stop_id", how="left")

    stop_times_active = stop_times[stop_times["trip_id"].isin(candidate_trips["trip_id"])].copy()
    stop_times_active["departure_secs"] = stop_times_active["departure_time"].map(gtfs_time_to_seconds)
    start_secs = gtfs_time_to_seconds(window_start) or 0
    end_secs = gtfs_time_to_seconds(window_end) or 24 * 3600

    windowed = stop_times_active[
        stop_times_active["departure_secs"].notna()
        & (stop_times_active["departure_secs"] >= start_secs)
        & (stop_times_active["departure_secs"] <= end_secs)
        & (stop_times_active["stop_id"].isin(corridor_stops["stop_id"]))
    ]

    headway_rows = []
    for stop_id, group in windowed.groupby("stop_id"):
        departures = sorted(group["departure_secs"].astype(int).tolist())
        diffs = np.diff(departures)
        headway_minutes = float(np.mean(diffs) / 60.0) if len(diffs) else np.nan
        headway_rows.append(
            {
                "stop_id": stop_id,
                "avg_headway_minutes": round(headway_minutes, 2) if pd.notna(headway_minutes) else np.nan,
                "scheduled_departures_in_window": len(departures),
            }
        )
    headways = pd.DataFrame(headway_rows)
    route_median = float(headways["avg_headway_minutes"].median()) if not headways.empty else np.nan
    corridor_stops = corridor_stops.merge(headways, on="stop_id", how="left")
    corridor_stops["avg_headway_minutes"] = corridor_stops["avg_headway_minutes"].fillna(route_median)
    corridor_stops["scheduled_departures_in_window"] = corridor_stops["scheduled_departures_in_window"].fillna(0).astype(int)
    corridor_stops["route_id"] = route_id
    corridor_stops["route_short_name"] = route_short_name
    corridor_stops["direction_id"] = int(direction_id)
    corridor_stops["trip_headsign"] = exemplar_trip.get("trip_headsign")
    corridor_stops["service_date"] = service_date.isoformat()
    corridor_stops["wait_source"] = f"MTA GTFS window {window_start}-{window_end}"
    return corridor_stops


def _to_gdf(df: pd.DataFrame, lon_col: str, lat_col: str) -> gpd.GeoDataFrame:
    frame = df.copy()
    frame[lon_col] = pd.to_numeric(frame[lon_col], errors="coerce")
    frame[lat_col] = pd.to_numeric(frame[lat_col], errors="coerce")
    frame = frame.dropna(subset=[lon_col, lat_col])
    return gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(frame[lon_col], frame[lat_col]), crs="EPSG:4326").to_crs(2263)


def fetch_tree_subset(stops_df: pd.DataFrame, route_short_name: str, direction_id: int, force: bool = False) -> Path:
    tree_path = RAW_DIR / f"nyc_street_trees_{route_short_name}_{direction_id}.csv"
    if tree_path.exists() and not force:
        return tree_path

    min_lat = stops_df["stop_lat"].astype(float).min() - 0.01
    max_lat = stops_df["stop_lat"].astype(float).max() + 0.01
    min_lon = stops_df["stop_lon"].astype(float).min() - 0.01
    max_lon = stops_df["stop_lon"].astype(float).max() + 0.01
    params = {
        "$select": "tree_id,latitude,longitude,tree_dbh,spc_common,health",
        "$where": (
            f"latitude >= {min_lat} AND latitude <= {max_lat} "
            f"AND longitude >= {min_lon} AND longitude <= {max_lon}"
        ),
        "$limit": 50000,
    }
    response = _request(TREE_URL, params=params, timeout=120)
    tree_path.write_text(response.text)
    return tree_path


def attach_spatial_features(
    stops_df: pd.DataFrame,
    shelters_path: Path,
    seating_path: Path,
    tree_path: Path,
    shelter_radius_ft: float,
    seating_radius_ft: float,
    tree_radius_ft: float,
) -> pd.DataFrame:
    stops_gdf = _to_gdf(stops_df, "stop_lon", "stop_lat")
    shelters_gdf = _to_gdf(pd.read_csv(shelters_path, dtype=str), "Longitude", "Latitude")
    seating_gdf = _to_gdf(pd.read_csv(seating_path, dtype=str), "longitude", "latitude")
    tree_df = pd.read_csv(tree_path, dtype=str)
    tree_gdf = _to_gdf(tree_df, "longitude", "latitude")

    shelter_values = []
    seating_values = []
    tree_values = []

    for _, stop in stops_gdf.iterrows():
        shelter_distances = shelters_gdf.distance(stop.geometry)
        shelter_min = float(shelter_distances.min()) if not shelters_gdf.empty else np.nan
        shelter_values.append(
            {
                "stop_id": stop["stop_id"],
                "has_shelter": bool(shelter_min <= shelter_radius_ft) if pd.notna(shelter_min) else np.nan,
                "shelter_distance_ft": round(shelter_min, 1) if pd.notna(shelter_min) else np.nan,
                "shelter_source": "NYC DOT Bus Stop Shelters",
            }
        )

        seating_distances = seating_gdf.distance(stop.geometry)
        seating_min = float(seating_distances.min()) if not seating_gdf.empty else np.nan
        seating_values.append(
            {
                "stop_id": stop["stop_id"],
                "has_nearby_seating": bool(seating_min <= seating_radius_ft) if pd.notna(seating_min) else np.nan,
                "seating_distance_ft": round(seating_min, 1) if pd.notna(seating_min) else np.nan,
                "bench_source": "NYC DOT Seating Locations",
            }
        )

        tree_distances = tree_gdf.distance(stop.geometry)
        nearby = tree_gdf.loc[tree_distances <= tree_radius_ft]
        dbh_sum = pd.to_numeric(nearby.get("tree_dbh"), errors="coerce").fillna(0).sum() if not nearby.empty else 0.0
        tree_values.append(
            {
                "stop_id": stop["stop_id"],
                "nearby_tree_count": int(len(nearby)),
                "nearby_tree_dbh_sum": round(float(dbh_sum), 1),
                "tree_source": "NYC Street Tree Census",
            }
        )

    enriched = (
        stops_df.merge(pd.DataFrame(shelter_values), on="stop_id", how="left")
        .merge(pd.DataFrame(seating_values), on="stop_id", how="left")
        .merge(pd.DataFrame(tree_values), on="stop_id", how="left")
    )
    return enriched


def make_corridor_id(route_short_name: str, direction_id: int) -> str:
    safe_route = re.sub(r"[^a-zA-Z0-9]+", "_", route_short_name).strip("_").lower()
    return f"{safe_route}__dir_{direction_id}"


def _corridor_paths(corridor_id: str) -> dict[str, Path]:
    corridor_dir = CORRIDORS_DIR / corridor_id
    return {
        "dir": corridor_dir,
        "csv": corridor_dir / "stops_scored.csv",
        "geojson": corridor_dir / "stops_scored.geojson",
        "meta": corridor_dir / "build_meta.json",
    }


def _empty_state() -> dict:
    return {
        "status": "empty",
        "message": "No processed dataset found. Run `python scripts/build_demo_data.py` first.",
        "sources": [asdict(source) for source in DATA_SOURCES],
        "manual_inputs": MANUAL_INPUTS,
        "corridors": [],
    }


def _read_corridors_index() -> dict:
    if not CORRIDORS_INDEX_PATH.exists():
        return {"corridors": [], "default_corridor_id": None}
    return json.loads(CORRIDORS_INDEX_PATH.read_text())


def list_processed_corridors() -> list[dict]:
    index = _read_corridors_index()
    corridors = index.get("corridors", [])
    if corridors:
        return corridors

    meta_path = PROCESSED_DIR / "build_meta.json"
    if not meta_path.exists():
        return []
    meta = json.loads(meta_path.read_text())
    corridor_id = meta.get("corridor_id") or make_corridor_id(meta["route_short_name"], int(meta["direction_id"]))
    return [
        {
            "corridor_id": corridor_id,
            "label": meta.get("corridor_name", f"{meta['route_short_name']} direction {meta['direction_id']}"),
            "route_short_name": meta["route_short_name"],
            "direction_id": int(meta["direction_id"]),
            "service_date": meta.get("service_date"),
            "stop_count": meta.get("stop_count"),
            "generated_at": meta.get("generated_at"),
        }
    ]


def _resolve_corridor_id(corridor_id: str | None) -> str | None:
    if corridor_id:
        return corridor_id
    index = _read_corridors_index()
    if index.get("default_corridor_id"):
        return index["default_corridor_id"]
    corridors = index.get("corridors", [])
    if corridors:
        return corridors[0]["corridor_id"]
    return None


def _write_latest_outputs(scored: pd.DataFrame, build_meta: dict) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PROCESSED_DIR / "stops_scored.csv"
    geojson_path = PROCESSED_DIR / "stops_scored.geojson"
    meta_path = PROCESSED_DIR / "build_meta.json"

    scored.to_csv(csv_path, index=False)
    gdf = gpd.GeoDataFrame(
        scored.copy(),
        geometry=gpd.points_from_xy(pd.to_numeric(scored["stop_lon"]), pd.to_numeric(scored["stop_lat"])),
        crs="EPSG:4326",
    )
    gdf.to_file(geojson_path, driver="GeoJSON")
    meta_path.write_text(json.dumps(build_meta, indent=2))


def _update_corridors_index(summary: dict, set_default: bool) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    index = _read_corridors_index()
    corridors = [item for item in index.get("corridors", []) if item.get("corridor_id") != summary["corridor_id"]]
    corridors.append(summary)
    corridors = sorted(corridors, key=lambda item: (str(item.get("route_short_name", "")), int(item.get("direction_id", 0))))
    default_corridor_id = index.get("default_corridor_id")
    if set_default or not default_corridor_id:
        default_corridor_id = summary["corridor_id"]
    CORRIDORS_INDEX_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().astimezone().isoformat(),
                "default_corridor_id": default_corridor_id,
                "corridors": corridors,
            },
            indent=2,
        )
    )


def build_processed_dataset(
    route_short_name: str | None = None,
    direction_id: int | None = None,
    stop_limit: int | None = None,
    service_date_value: str | None = None,
    force_download: bool = False,
    set_default: bool = True,
) -> pd.DataFrame:
    route_short_name = route_short_name or settings.route_short_name
    direction_id = settings.direction_id if direction_id is None else direction_id
    stop_limit = stop_limit or settings.stop_limit
    service_date_obj = _service_date(service_date_value or settings.service_date or None)
    corridor_id = make_corridor_id(route_short_name, int(direction_id))
    corridor_name = f"{settings.city_name} {route_short_name} direction {direction_id}"

    download_required_datasets(force=force_download)
    gtfs_tables = load_gtfs_tables(GTFS_ZIP_PATH)
    stops_df = build_route_stop_frame(
        gtfs_tables=gtfs_tables,
        route_short_name=route_short_name,
        direction_id=direction_id,
        service_date=service_date_obj,
        stop_limit=stop_limit,
        window_start=settings.headway_window_start,
        window_end=settings.headway_window_end,
    )

    tree_path = fetch_tree_subset(stops_df, route_short_name=route_short_name, direction_id=direction_id, force=force_download)
    stops_df = attach_spatial_features(
        stops_df,
        shelters_path=SHELTERS_PATH,
        seating_path=SEATING_PATH,
        tree_path=tree_path,
        shelter_radius_ft=settings.shelter_match_radius_ft,
        seating_radius_ft=settings.seating_match_radius_ft,
        tree_radius_ft=settings.tree_buffer_radius_ft,
    )

    centroid_lat = round(float(stops_df["stop_lat"].astype(float).mean()), 6)
    centroid_lon = round(float(stops_df["stop_lon"].astype(float).mean()), 6)
    weather = fetch_weather_snapshot(centroid_lat, centroid_lon, horizon_hours=settings.weather_horizon_hours)
    for key, value in weather.items():
        stops_df[key] = value

    stops_df = attach_public_imagery(stops_df)
    image_features = analyze_stop_images(stops_df)
    stops_df = stops_df.merge(image_features, on="stop_id", how="left")

    stops_df["route_rank"] = range(1, len(stops_df) + 1)
    stops_df["corridor_name"] = corridor_name
    stops_df["corridor_id"] = corridor_id
    scored = score_stops(stops_df, weights=settings.score_weights)

    corridor_paths = _corridor_paths(corridor_id)
    corridor_paths["dir"].mkdir(parents=True, exist_ok=True)
    scored.to_csv(corridor_paths["csv"], index=False)
    gdf = gpd.GeoDataFrame(
        scored.copy(),
        geometry=gpd.points_from_xy(pd.to_numeric(scored["stop_lon"]), pd.to_numeric(scored["stop_lat"])),
        crs="EPSG:4326",
    )
    gdf.to_file(corridor_paths["geojson"], driver="GeoJSON")

    build_meta = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "corridor_id": corridor_id,
        "corridor_name": corridor_name,
        "city_name": settings.city_name,
        "route_short_name": route_short_name,
        "direction_id": direction_id,
        "stop_limit": stop_limit,
        "stop_count": int(len(scored)),
        "service_date": service_date_obj.isoformat(),
        "headway_window": [settings.headway_window_start, settings.headway_window_end],
        "score_weights": settings.score_weights,
        "sources": [asdict(source) for source in DATA_SOURCES],
        "manual_inputs": MANUAL_INPUTS,
        "weather": weather_summary_from_frame(stops_df, fallback_updated_at=datetime.now().astimezone().isoformat()),
    }
    corridor_paths["meta"].write_text(json.dumps(build_meta, indent=2))
    _write_latest_outputs(scored, build_meta)
    _update_corridors_index(
        {
            "corridor_id": corridor_id,
            "label": corridor_name,
            "route_short_name": route_short_name,
            "direction_id": int(direction_id),
            "service_date": service_date_obj.isoformat(),
            "stop_count": int(len(scored)),
            "generated_at": build_meta["generated_at"],
        },
        set_default=set_default,
    )
    return scored


def build_processed_datasets(
    corridor_specs: list[tuple[str, int]],
    stop_limit: int | None = None,
    service_date_value: str | None = None,
    force_download: bool = False,
) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    for idx, (route_short_name, direction_id) in enumerate(corridor_specs):
        outputs[make_corridor_id(route_short_name, direction_id)] = build_processed_dataset(
            route_short_name=route_short_name,
            direction_id=direction_id,
            stop_limit=stop_limit,
            service_date_value=service_date_value,
            force_download=force_download,
            set_default=idx == 0,
        )
    return outputs


def load_processed_outputs(corridor_id: str | None = None) -> tuple[pd.DataFrame, dict]:
    resolved_corridor_id = _resolve_corridor_id(corridor_id)
    if resolved_corridor_id:
        paths = _corridor_paths(resolved_corridor_id)
        if paths["csv"].exists():
            df = pd.read_csv(paths["csv"], dtype={"stop_id": str})
            meta = json.loads(paths["meta"].read_text()) if paths["meta"].exists() else {}
            meta["available_corridors"] = list_processed_corridors()
            return df, meta

    csv_path = PROCESSED_DIR / "stops_scored.csv"
    meta_path = PROCESSED_DIR / "build_meta.json"
    if not csv_path.exists():
        return pd.DataFrame(), _empty_state()
    df = pd.read_csv(csv_path, dtype={"stop_id": str})
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta["available_corridors"] = list_processed_corridors()
    return df, meta


def refresh_corridor_weather_scores(corridor_id: str | None = None) -> tuple[pd.DataFrame, dict]:
    df, meta = load_processed_outputs(corridor_id=corridor_id)
    if df.empty:
        return df, meta

    centroid_lat = round(float(df["stop_lat"].astype(float).mean()), 6)
    centroid_lon = round(float(df["stop_lon"].astype(float).mean()), 6)
    weather = fetch_weather_snapshot(centroid_lat, centroid_lon, horizon_hours=settings.weather_horizon_hours)
    refreshed = apply_weather_snapshot(df, weather)

    active_weights = meta.get("score_weights") or settings.score_weights
    rescored = score_stops(refreshed, weights=active_weights, planner_mode="auto")
    refreshed_meta = {
        **meta,
        "weather": weather_summary_from_frame(rescored, fallback_updated_at=meta.get("generated_at")),
        "live_weather_refresh": True,
    }
    return rescored, refreshed_meta
