from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
IMAGES_DIR = RAW_DIR / "stop_images"

DEFAULT_SCORE_WEIGHTS = {
    "no_shelter": 0.35,
    "low_tree_cover": 0.25,
    "heat_burden": 0.15,
    "wait_burden": 0.15,
    "no_bench": 0.10,
}


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    city_name: str = os.getenv("HEATSTOP_CITY_NAME", "New York City")
    route_short_name: str = os.getenv("HEATSTOP_ROUTE_SHORT_NAME", "M15")
    direction_id: int = int(os.getenv("HEATSTOP_DIRECTION_ID", "0"))
    stop_limit: int = int(os.getenv("HEATSTOP_STOP_LIMIT", "20"))
    service_date: str = os.getenv("HEATSTOP_SERVICE_DATE", "")
    headway_window_start: str = os.getenv("HEATSTOP_WINDOW_START", "12:00:00")
    headway_window_end: str = os.getenv("HEATSTOP_WINDOW_END", "18:00:00")
    shelter_match_radius_ft: float = float(os.getenv("HEATSTOP_SHELTER_MATCH_RADIUS_FT", "65"))
    seating_match_radius_ft: float = float(os.getenv("HEATSTOP_SEATING_MATCH_RADIUS_FT", "65"))
    tree_buffer_radius_ft: float = float(os.getenv("HEATSTOP_TREE_BUFFER_RADIUS_FT", "100"))
    weather_horizon_hours: int = int(os.getenv("HEATSTOP_WEATHER_HORIZON_HOURS", "8"))
    enable_public_imagery: bool = os.getenv("HEATSTOP_ENABLE_PUBLIC_IMAGERY", "1").lower() in {"1", "true", "yes"}
    public_imagery_radius_m: float = float(os.getenv("HEATSTOP_PUBLIC_IMAGERY_RADIUS_M", "35"))
    mapillary_access_token: str = os.getenv("HEATSTOP_MAPILLARY_ACCESS_TOKEN", "")
    use_mapillary_demo_token: bool = os.getenv("HEATSTOP_USE_MAPILLARY_DEMO_TOKEN", "1").lower() in {"1", "true", "yes"}
    enable_pretrained_vision: bool = os.getenv("HEATSTOP_ENABLE_PRETRAINED_VISION", "0").lower() in {"1", "true", "yes"}
    pretrained_vision_model: str = os.getenv("HEATSTOP_PRETRAINED_VISION_MODEL", "google/owlvit-base-patch32")
    pretrained_vision_threshold: float = float(os.getenv("HEATSTOP_PRETRAINED_VISION_THRESHOLD", "0.12"))
    enable_community_uploads: bool = os.getenv("HEATSTOP_ENABLE_COMMUNITY_UPLOADS", "1").lower() in {"1", "true", "yes"}
    cors_allow_origins: list[str] = field(
        default_factory=lambda: _csv_env(
            "HEATSTOP_CORS_ALLOW_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        )
    )
    cors_allow_credentials: bool = os.getenv("HEATSTOP_CORS_ALLOW_CREDENTIALS", "0").lower() in {"1", "true", "yes"}
    backend_host: str = os.getenv("HEATSTOP_BACKEND_HOST", "0.0.0.0")
    backend_port: int = int(os.getenv("HEATSTOP_BACKEND_PORT", "8000"))
    api_url: str = os.getenv("HEATSTOP_API_URL", "http://localhost:8000")
    llm_provider: str = os.getenv("HEATSTOP_LLM_PROVIDER", "openai")
    openai_api_key: str = os.getenv("HEATSTOP_OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("HEATSTOP_OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("HEATSTOP_LLM_MODEL", "gpt-4.1-mini")
    llm_timeout_seconds: int = int(os.getenv("HEATSTOP_LLM_TIMEOUT_SECONDS", "20"))
    gemini_api_key: str = os.getenv("HEATSTOP_GEMINI_API_KEY", "")
    gemini_base_url: str = os.getenv("HEATSTOP_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    gemini_model: str = os.getenv("HEATSTOP_GEMINI_MODEL", "gemini-2.0-flash")
    mta_bus_time_api_key: str = os.getenv("HEATSTOP_MTA_BUS_TIME_API_KEY", "")
    mta_bus_time_base_url: str = os.getenv(
        "HEATSTOP_MTA_BUS_TIME_BASE_URL",
        "https://bustime.mta.info/api/siri/stop-monitoring.json",
    )
    relief_places_base_url: str = os.getenv(
        "HEATSTOP_RELIEF_PLACES_BASE_URL",
        "https://overpass-api.de/api/interpreter",
    )
    relief_search_radius_m: int = int(os.getenv("HEATSTOP_RELIEF_SEARCH_RADIUS_M", "400"))
    relief_max_results: int = int(os.getenv("HEATSTOP_RELIEF_MAX_RESULTS", "8"))
    rider_walking_speed_m_per_min: float = float(os.getenv("HEATSTOP_RIDER_WALKING_SPEED_M_PER_MIN", "80"))
    lower_risk_stop_radius_m: int = int(os.getenv("HEATSTOP_LOWER_RISK_STOP_RADIUS_M", "500"))
    lower_risk_stop_min_risk_drop: float = float(os.getenv("HEATSTOP_LOWER_RISK_STOP_MIN_RISK_DROP", "12"))
    score_weights: dict[str, float] = field(default_factory=lambda: DEFAULT_SCORE_WEIGHTS.copy())


settings = Settings()
