from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DataSource:
    name: str
    category: str
    source_url: str
    local_file: str
    fields_used: list[str]
    notes: str


DATA_SOURCES = [
    DataSource(
        name="MTA Manhattan GTFS",
        category="Transit schedule and stop locations",
        source_url="http://web.mta.info/developers/data/nyct/bus/google_transit_manhattan.zip",
        local_file="data/raw/google_transit_manhattan.zip",
        fields_used=[
            "routes.route_id",
            "routes.route_short_name",
            "trips.trip_id",
            "trips.direction_id",
            "stop_times.stop_id",
            "stop_times.stop_sequence",
            "stop_times.departure_time",
            "stops.stop_name",
            "stops.stop_lat",
            "stops.stop_lon",
            "calendar.*",
            "calendar_dates.*",
        ],
        notes="Official MTA Manhattan bus GTFS feed. Used to identify corridor stops and scheduled wait burden.",
    ),
    DataSource(
        name="NYC DOT Bus Stop Shelters",
        category="Stop amenity",
        source_url="https://data.cityofnewyork.us/api/views/t4f2-8md7/rows.csv?accessType=DOWNLOAD",
        local_file="data/raw/nyc_bus_stop_shelters.csv",
        fields_used=["Shelter_ID", "On_Street", "Cross_Stre", "Longitude", "Latitude"],
        notes="Official NYC DOT shelter inventory. Spatially joined to route stops to infer shelter presence.",
    ),
    DataSource(
        name="NYC DOT Seating Locations",
        category="Street furniture / seating proxy",
        source_url="https://data.cityofnewyork.us/resource/esmy-s8q5.csv",
        local_file="data/raw/nyc_seating_locations.csv",
        fields_used=["asset_subtype", "latitude", "longitude", "siteid"],
        notes="Official NYC DOT seating inventory. Spatially joined to route stops as a nearby seating proxy.",
    ),
    DataSource(
        name="NYC Street Tree Census",
        category="Tree cover proxy",
        source_url="https://data.cityofnewyork.us/resource/uvpi-gqnh.csv",
        local_file="data/raw/nyc_street_trees_{route}_{direction}.csv",
        fields_used=["tree_id", "latitude", "longitude", "tree_dbh", "spc_common", "health"],
        notes="Official tree inventory. Queried only within the corridor bounding box and buffered around stops.",
    ),
    DataSource(
        name="NYC Facilities Database",
        category="Vulnerability proxies",
        source_url="https://data.cityofnewyork.us/resource/ji82-xba5.csv",
        local_file="data/raw/nyc_vulnerability_facilities_{corridor_id}.csv",
        fields_used=["facname", "latitude", "longitude", "facgroup", "facsubgrp", "factype", "opname"],
        notes="Official NYC facilities inventory. Queried within the corridor bounding box and filtered to hospitals, senior services, and K-12 schools as place-based vulnerability proxies.",
    ),
    DataSource(
        name="NWS / NOAA Gridpoint Forecast",
        category="Heat burden",
        source_url="https://api.weather.gov/points/{lat},{lon}",
        local_file="live_api_call",
        fields_used=["heatIndex.values", "apparentTemperature.values", "temperature.values"],
        notes="Official National Weather Service forecast grid. Used to compute corridor-wide near-term heat burden.",
    ),
    DataSource(
        name="Local stop imagery",
        category="Optional image analysis",
        source_url="local_folder",
        local_file="data/raw/stop_images/",
        fields_used=["real image pixels only"],
        notes="User-supplied real stop images. If missing, image-derived features remain null and the UI shows image unavailable.",
    ),
    DataSource(
        name="Mapillary street-level imagery",
        category="Optional public imagery",
        source_url="https://www.mapillary.com/developer/api-documentation/",
        local_file="data/raw/stop_images/mapillary_<stop_id>.jpg",
        fields_used=["captured_at", "thumb_1024_url", "computed_geometry", "creator.username"],
        notes="Optional stop-area street imagery used when no local image is present. The MVP uses the latest nearby image and displays attribution.",
    ),
]


MANUAL_INPUTS = [
    {
        "item": "Real bus stop images",
        "path": "data/raw/stop_images/",
        "required_for": "Image-based shelter/tree/openness heuristics",
        "instruction": "Add real JPG/PNG files named `<stop_id>.jpg` or provide `manifest.csv` with `stop_id,file_name,source_url`.",
    }
]


def serialize_sources() -> list[dict]:
    return [asdict(source) for source in DATA_SOURCES]
