from __future__ import annotations

from typing import Any


def attach_waiting_point_amenities(*args: Any, **kwargs: Any):
    from app.ingest import attach_spatial_features

    return attach_spatial_features(*args, **kwargs)


def fetch_tree_subset(*args: Any, **kwargs: Any):
    from app.ingest import fetch_tree_subset as _fetch_tree_subset

    return _fetch_tree_subset(*args, **kwargs)


def enrich_waiting_points_with_vulnerability(*args: Any, **kwargs: Any):
    from app.vulnerability import enrich_stops_with_vulnerability

    return enrich_stops_with_vulnerability(*args, **kwargs)
