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
    enable_pretrained_vision: bool = os.getenv("HEATSTOP_ENABLE_PRETRAINED_VISION", "1").lower() in {"1", "true", "yes"}
    pretrained_vision_model: str = os.getenv("HEATSTOP_PRETRAINED_VISION_MODEL", "google/owlvit-base-patch32")
    pretrained_vision_threshold: float = float(os.getenv("HEATSTOP_PRETRAINED_VISION_THRESHOLD", "0.12"))
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
    score_weights: dict[str, float] = field(default_factory=lambda: DEFAULT_SCORE_WEIGHTS.copy())


settings = Settings()
