from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _bucket(score: float, low_cut: float, high_cut: float) -> str:
    if score >= high_cut:
        return "High"
    if score >= low_cut:
        return "Medium"
    return "Low"


def _adverb(label: str) -> str:
    mapping = {
        "Low": "lightly",
        "Medium": "moderately",
        "High": "heavily",
    }
    return mapping.get(label, label.lower())


def _confidence_label(score: float) -> str:
    if score >= 0.66:
        return "Medium"
    return "Low"


def estimate_people_activity(
    stop: dict[str, Any],
    corridor_stops,
    rider_support: dict[str, Any],
) -> dict[str, Any]:
    relief_places = rider_support.get("nearby_relief", {}).get("items") or []
    poi_density_score = min(len(relief_places) / 6.0, 1.0)
    headway = _safe_float(stop.get("avg_headway_minutes"))
    wait_score = min(headway / 20.0, 1.0)
    risk_score = min(_safe_float(stop.get("display_relative_risk", stop.get("normalized_priority_score"))) / 100.0, 1.0)
    corridor_size_score = min(max(len(corridor_stops), 1) / 20.0, 1.0)
    route_name = str(stop.get("route_short_name") or "")
    route_importance_score = 1.0 if "SBS" in route_name else 0.65
    composite = (
        0.35 * poi_density_score
        + 0.25 * wait_score
        + 0.20 * route_importance_score
        + 0.10 * corridor_size_score
        + 0.10 * risk_score
    )
    level = _bucket(composite, 0.38, 0.68)
    explanation = (
        f"Foot activity may be {level.lower()} because this waiting point sits near {len(relief_places)} active nearby destinations, "
        f"has an average scheduled headway of {headway:.1f} minutes, and serves the {route_name or 'selected route'} corridor."
    )
    return {
        "signal_name": "people_activity",
        "label": "People near this waiting point",
        "status": "estimated",
        "evidence_tier": "Estimated",
        "confidence": _confidence_label(composite),
        "summary": explanation,
        "value": level,
        "sources": [
            "Nearby POI density",
            "GTFS scheduled headway",
            "Selected route/corridor context",
        ],
    }


def estimate_noise_level(
    stop: dict[str, Any],
    rider_support: dict[str, Any],
) -> dict[str, Any]:
    route_name = str(stop.get("route_short_name") or "")
    headway = _safe_float(stop.get("avg_headway_minutes"))
    open_sky = _safe_float(stop.get("open_sky_ratio"))
    no_shelter = 0.0 if bool(stop.get("has_shelter")) else 1.0
    relief_places = rider_support.get("nearby_relief", {}).get("items") or []
    urban_activity_score = min(len(relief_places) / 8.0, 1.0)
    transit_activity_score = 1.0 if "SBS" in route_name else min(max(12.0 - headway, 0.0) / 12.0, 1.0)
    exposure_score = min(0.6 * open_sky + 0.4 * no_shelter, 1.0)
    composite = 0.45 * transit_activity_score + 0.30 * exposure_score + 0.25 * urban_activity_score
    level = _bucket(composite, 0.34, 0.66)
    explanation = (
        f"This waiting point likely experiences {level.lower()} street noise because it sits on an active bus corridor, "
        f"has {'high' if open_sky >= 0.6 else 'some'} roadside exposure, and is surrounded by {len(relief_places)} nearby active destinations."
    )
    return {
        "signal_name": "noise_level",
        "label": "Noise level here",
        "status": "estimated",
        "evidence_tier": "Estimated",
        "confidence": _confidence_label(composite),
        "summary": explanation,
        "value": level,
        "sources": [
            "Route activity proxy",
            "Open-sky / exposure proxy",
            "Nearby POI density",
        ],
    }


def estimate_bus_crowding(
    stop: dict[str, Any],
    rider_support: dict[str, Any],
    corridor_intelligence: dict[str, Any] | None,
) -> dict[str, Any]:
    next_arrival = rider_support.get("arrivals", {}).get("next_arrival") or {}
    eta = _safe_float(next_arrival.get("eta_minutes"))
    headway = _safe_float(stop.get("avg_headway_minutes"))
    corridor_burden = _safe_float((corridor_intelligence or {}).get("evidence", {}).get("top5_burden_share_pct"))
    people_level = 0.55
    if corridor_burden >= 45:
        people_level += 0.15
    wait_score = min(headway / 20.0, 1.0)
    eta_score = min(eta / 15.0, 1.0) if eta > 0 else 0.0
    route_bonus = 1.0 if "SBS" in str(stop.get("route_short_name") or "") else 0.6
    composite = 0.35 * wait_score + 0.25 * eta_score + 0.20 * route_bonus + 0.20 * people_level
    level = _bucket(composite, 0.38, 0.68)
    eta_phrase = f"current next-bus spacing of about {eta:.0f} minutes" if eta > 0 else "available scheduled headway patterns"
    explanation = (
        f"The next bus may be {_adverb(level)} crowded based on {eta_phrase}, the stop's {headway:.1f}-minute average headway, "
        f"and the corridor's overall demand intensity signals. HeatStop does not currently have a verified live occupancy feed."
    )
    return {
        "signal_name": "bus_crowding",
        "label": "Is the bus packed?",
        "status": "estimated",
        "evidence_tier": "Estimated",
        "confidence": _confidence_label(composite),
        "summary": explanation,
        "value": level,
        "sources": [
            "MTA arrival spacing",
            "GTFS scheduled headway",
            "Corridor burden share",
        ],
    }


def estimate_exposure_feel(stop: dict[str, Any]) -> dict[str, Any]:
    risk = _safe_float(stop.get("display_relative_risk", stop.get("normalized_priority_score"))) / 100.0
    open_sky = _safe_float(stop.get("open_sky_ratio"))
    tree_cover = _safe_float(stop.get("combined_tree_cover_score"))
    no_shelter = 0.0 if bool(stop.get("has_shelter")) else 1.0
    visible_tree = _safe_float(stop.get("visible_tree_ratio"))
    composite = 0.35 * risk + 0.25 * open_sky + 0.20 * no_shelter + 0.10 * (1 - tree_cover) + 0.10 * (1 - visible_tree)
    level = _bucket(composite, 0.34, 0.66)
    confidence = "Medium" if stop.get("image_provider") or stop.get("display_image_provider") else "Low"
    explanation = (
        f"This waiting point likely feels {level.lower()}ly exposed because shelter coverage is "
        f"{'present' if bool(stop.get('has_shelter')) else 'limited'}, open-sky exposure is {open_sky:.2f}, "
        f"and nearby tree cover remains constrained."
    )
    return {
        "signal_name": "exposure_feel",
        "label": "How exposed the waiting point feels",
        "status": "estimated",
        "evidence_tier": "Estimated",
        "confidence": confidence,
        "summary": explanation,
        "value": level,
        "sources": [
            "HeatStop shelter/tree evidence",
            "Image openness proxy" if confidence == "Medium" else "Stop-level spatial evidence",
        ],
    }


def extract_budget_amount(question: str | None) -> float | None:
    if not question:
        return None
    match = re.search(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", question.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def estimate_budget_actions(stop: dict[str, Any], budget_amount: float | None) -> dict[str, Any]:
    actions = [item.strip() for item in str(stop.get("display_recommended_action_summary") or stop.get("recommended_action_summary") or "").split("|") if item.strip()]
    if not actions:
        actions = ["Monitor"]
    tight_budget_actions = [action for action in actions if action in {"Add seating", "Service review"}]
    medium_budget_actions = [action for action in actions if action in {"Shade canopy", "Increase tree cover"}]
    if budget_amount is None:
        summary = (
            "HeatStop does not have a verified capital cost model. Estimated (medium confidence): start with lower-scope actions like seating or service review first, "
            "then move to canopy or tree-cover work if more budget is available."
        )
    elif budget_amount < 25000:
        chosen = tight_budget_actions or actions[:1]
        summary = (
            f"With a tighter budget around ${budget_amount:,.0f}, the most practical first moves are "
            f"{', '.join(action.lower() for action in chosen)}. Larger canopy or tree projects likely require more capital."
        )
    elif budget_amount < 100000:
        chosen = (tight_budget_actions + medium_budget_actions)[:2] or actions[:2]
        summary = (
            f"With a mid-range budget around ${budget_amount:,.0f}, this waiting point could reasonably start with "
            f"{', '.join(action.lower() for action in chosen)}."
        )
    else:
        chosen = actions[:3]
        summary = (
            f"With a larger budget around ${budget_amount:,.0f}, the waiting point could address the full current action mix: "
            f"{', '.join(action.lower() for action in chosen)}."
        )
    return {
        "signal_name": "budget_actions",
        "label": "Budget-aware action plan",
        "status": "estimated",
        "evidence_tier": "Estimated",
        "confidence": "Medium",
        "summary": summary,
        "value": actions[:3],
        "sources": [
            "Current HeatStop recommended actions",
            "Planning heuristic cost tiers",
        ],
    }
