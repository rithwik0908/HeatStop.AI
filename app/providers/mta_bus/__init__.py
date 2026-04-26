from __future__ import annotations

from typing import Any


def build_bus_waiting_points(*args: Any, **kwargs: Any):
    from app.ingest import build_processed_dataset

    return build_processed_dataset(*args, **kwargs)


def build_bus_waiting_point_sets(*args: Any, **kwargs: Any):
    from app.ingest import build_processed_datasets

    return build_processed_datasets(*args, **kwargs)


def fetch_bus_arrivals(*args: Any, **kwargs: Any):
    from app.realtime_arrivals import fetch_stop_arrivals

    return fetch_stop_arrivals(*args, **kwargs)
