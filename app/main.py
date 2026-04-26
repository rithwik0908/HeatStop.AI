from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import IMAGES_DIR, settings
from app.data_sources import MANUAL_INPUTS, serialize_sources
from app.ingest import PROCESSED_DIR, list_processed_corridors, load_processed_outputs, refresh_corridor_weather_scores
from app.nearby_relief import fetch_nearby_relief_places
from app.planner import build_planner_note, recommend_action_summary
from app.realtime_arrivals import fetch_stop_arrivals
from app.weather import weather_summary_from_frame


app = FastAPI(title="HeatStop AI API", version="0.1.0")
allow_origins = settings.cors_allow_origins or ["http://localhost:8501", "http://127.0.0.1:8501"]
allow_credentials = settings.cors_allow_credentials and "*" not in allow_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


def _clean_records(df: pd.DataFrame) -> list[dict]:
    cleaned = df.replace({np.nan: None}).to_dict(orient="records")
    for row in cleaned:
        if row.get("score_breakdown_json"):
            row["score_breakdown"] = json.loads(row["score_breakdown_json"])
        else:
            row["score_breakdown"] = {}
        if not row.get("recommended_action_summary"):
            row["recommended_action_summary"] = recommend_action_summary(row)
        if not row.get("planner_note_source") or not row.get("planner_note_urgency"):
            top_contributors = [item.strip() for item in str(row.get("top_contributors", "")).split(",") if item.strip()]
            fallback_note = build_planner_note(row, top_contributors, mode="fallback")
            row["planner_note"] = row.get("planner_note") or fallback_note["planner_note"]
            row["planner_note_reason"] = row.get("planner_note_reason") or fallback_note["planner_note_reason"]
            row["planner_note_recommendation"] = row.get("planner_note_recommendation") or fallback_note["planner_note_recommendation"]
            row["planner_note_urgency"] = row.get("planner_note_urgency") or fallback_note["planner_note_urgency"]
            row["planner_note_source"] = row.get("planner_note_source") or fallback_note["planner_note_source"]
        image_path = row.get("image_path")
        if image_path:
            image_name = Path(image_path).name
            row["image_url"] = f"/images/{image_name}"
        if row.get("display_image_source_url"):
            row["display_image_url"] = row["display_image_source_url"]
        elif row.get("image_url"):
            row["display_image_url"] = row["image_url"]
    return cleaned


def _enrich_meta(meta: dict, df: pd.DataFrame) -> dict:
    enriched = dict(meta)
    enriched["sources"] = enriched.get("sources", serialize_sources())
    enriched["manual_inputs"] = enriched.get("manual_inputs", MANUAL_INPUTS)
    fallback_updated_at = enriched.get("generated_at")
    enriched["weather"] = weather_summary_from_frame(df, fallback_updated_at=fallback_updated_at) if not df.empty else {}
    return enriched


@app.get("/")
def root() -> dict:
    return {
        "name": "HeatStop AI API",
        "status": "ok",
        "message": "Backend is running.",
        "endpoints": {
            "health": "/health",
            "corridors": "/corridors",
            "meta": "/meta",
            "stops": "/stops",
            "refresh_weather": "/weather/refresh",
            "rider_support": "/stops/{stop_id}/rider-support",
            "geojson": "/geojson",
            "docs": "/docs",
        },
    }


@app.get("/health")
def health() -> dict:
    df, meta = load_processed_outputs()
    corridors = list_processed_corridors()
    return {
        "status": "ok",
        "processed_rows": int(len(df)),
        "has_processed_data": not df.empty,
        "message": meta.get("message"),
        "corridors_count": len(corridors),
        "default_corridor_id": meta.get("corridor_id"),
    }


@app.get("/corridors")
def corridors() -> dict:
    items = list_processed_corridors()
    return {"items": items, "count": len(items)}


@app.get("/meta")
def meta(corridor_id: str | None = None) -> dict:
    df, build_meta = load_processed_outputs(corridor_id=corridor_id)
    if build_meta.get("status") == "empty":
        return build_meta
    return _enrich_meta(build_meta, df)


@app.get("/stops")
def get_stops(top_n: int | None = None, corridor_id: str | None = None) -> dict:
    df, meta = load_processed_outputs(corridor_id=corridor_id)
    if df.empty:
        return {"items": [], "meta": meta}
    if top_n:
        df = df.head(top_n)
    return {"items": _clean_records(df), "meta": _enrich_meta(meta, df)}


@app.get("/stops/{stop_id}")
def get_stop(stop_id: str, corridor_id: str | None = None) -> dict:
    df, meta = load_processed_outputs(corridor_id=corridor_id)
    if df.empty:
        raise HTTPException(status_code=404, detail="Processed dataset not found.")
    match = df.loc[df["stop_id"].astype(str) == str(stop_id)]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Stop `{stop_id}` not found.")
    return {"item": _clean_records(match)[0], "meta": _enrich_meta(meta, match)}


@app.post("/weather/refresh")
def refresh_weather(corridor_id: str | None = None) -> dict:
    df, meta = refresh_corridor_weather_scores(corridor_id=corridor_id)
    if df.empty:
        raise HTTPException(status_code=404, detail="Processed dataset not found.")
    enriched_meta = _enrich_meta(meta, df)
    return {
        "corridor_id": enriched_meta.get("corridor_id"),
        "items": _clean_records(df),
        "meta": enriched_meta,
        "weather": enriched_meta.get("weather", {}),
    }


@app.get("/stops/{stop_id}/rider-support")
def get_rider_support(stop_id: str, corridor_id: str | None = None) -> dict:
    df, meta = load_processed_outputs(corridor_id=corridor_id)
    if df.empty:
        raise HTTPException(status_code=404, detail="Processed dataset not found.")
    match = df.loc[df["stop_id"].astype(str) == str(stop_id)]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Stop `{stop_id}` not found.")

    row = _clean_records(match)[0]
    stop_lat = float(row["stop_lat"])
    stop_lon = float(row["stop_lon"])
    arrivals = fetch_stop_arrivals(str(stop_id), route_short_name=row.get("route_short_name"))
    relief_places = fetch_nearby_relief_places(stop_lat, stop_lon)
    return {
        "stop": {
            "stop_id": str(row["stop_id"]),
            "stop_name": row.get("stop_name"),
            "route_short_name": row.get("route_short_name"),
            "direction_id": row.get("direction_id"),
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
            "corridor_id": meta.get("corridor_id"),
        },
        "arrivals": arrivals,
        "nearby_relief": relief_places,
        "meta": {"corridor_id": meta.get("corridor_id")},
    }


@app.get("/geojson")
def get_geojson(corridor_id: str | None = None) -> dict:
    corridor_meta = load_processed_outputs(corridor_id=corridor_id)[1]
    active_corridor_id = corridor_meta.get("corridor_id")
    geojson_path = PROCESSED_DIR / "stops_scored.geojson"
    if active_corridor_id:
        geojson_path = PROCESSED_DIR / "corridors" / active_corridor_id / "stops_scored.geojson"
    if not geojson_path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(geojson_path.read_text())
