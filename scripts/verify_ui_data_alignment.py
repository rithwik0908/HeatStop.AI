#!/usr/bin/env python3
"""Validate that key UI fields align with API scoring data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
import requests

# Keep validation offline-safe in CI/sandboxes.
os.environ.setdefault("HEATSTOP_ENABLE_PRETRAINED_VISION", "0")


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.dashboard import prepare_display_stops


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Running FastAPI base URL")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    corridors = requests.get(f"{base_url}/corridors", timeout=30).json().get("items", [])
    if not corridors:
        print("No corridors returned by API.")
        return 1

    failures: list[str] = []
    for corridor in corridors:
        corridor_id = corridor["corridor_id"]
        payload = requests.get(f"{base_url}/stops", params={"corridor_id": corridor_id}, timeout=30).json()
        stops = pd.DataFrame(payload.get("items", []))
        display_stops = prepare_display_stops(stops)

        if display_stops.empty:
            failures.append(f"{corridor_id}: no display stops")
            continue

        required_columns = {
            "stop_name",
            "display_priority_score",
            "display_top_contributors",
            "display_recommended_action_summary",
            "display_has_field_review_override",
            "priority_score",
            "score_breakdown_json",
        }
        missing = sorted(required_columns - set(display_stops.columns))
        if missing:
            failures.append(f"{corridor_id}: missing UI columns: {', '.join(missing)}")
            continue

        no_override = display_stops[~display_stops["display_has_field_review_override"].fillna(False)]
        if not no_override.empty:
            delta = (
                pd.to_numeric(no_override["display_priority_score"], errors="coerce")
                - pd.to_numeric(no_override["priority_score"], errors="coerce")
            ).abs().max()
            if pd.notna(delta) and float(delta) > 1e-6:
                failures.append(f"{corridor_id}: display_priority_score deviates from API priority_score (max delta={float(delta):.6f})")

            for _, row in no_override.iterrows():
                raw = row.get("score_breakdown_json")
                breakdown = {}
                if isinstance(raw, str) and raw:
                    try:
                        breakdown = json.loads(raw)
                    except json.JSONDecodeError:
                        failures.append(f"{corridor_id}: invalid score_breakdown_json for stop_id={row.get('stop_id')}")
                        continue
                expected = ", ".join(
                    item.get("label", "")
                    for item in sorted(breakdown.values(), key=lambda item: item.get("score", 0), reverse=True)
                    if item.get("score", 0) > 0
                )
                actual = str(row.get("display_top_contributors") or "")
                if expected != actual:
                    failures.append(
                        f"{corridor_id}: contributors mismatch for stop_id={row.get('stop_id')} (expected='{expected}' actual='{actual}')"
                    )

        print(f"[ok] {corridor_id}: {len(display_stops)} rows validated")

    if failures:
        print("\nValidation FAILED:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("\nValidation passed: UI display fields align with API data across all corridors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
