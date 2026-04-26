from __future__ import annotations

from typing import Iterable

from app.llm import generate_grounded_planner_note


def recommend_action_labels(row: dict) -> list[str]:
    actions: list[str] = []
    if row.get("shelter_present_effective") == False:
        actions.append("Shade canopy")
    if row.get("bench_present_effective") == False:
        actions.append("Add seating")
    if (row.get("combined_tree_cover_score") or 0) < 0.35:
        actions.append("Increase tree cover")
    if (row.get("wait_burden_value") or 0) > 0.65:
        actions.append("Service review")
    if not actions:
        actions.append("Monitor")
    return actions


def recommend_intervention(row: dict) -> str:
    interventions: list[str] = []
    if row.get("shelter_present_effective") == False:
        interventions.append("install a modular shade canopy")
    if row.get("bench_present_effective") == False:
        interventions.append("add seating")
    if (row.get("combined_tree_cover_score") or 0) < 0.35:
        interventions.append("increase tree cover near the curb")
    if (row.get("wait_burden_value") or 0) > 0.65:
        interventions.append("review service spacing or stop consolidation")
    if not interventions:
        interventions.append("monitor heat exposure and maintain existing amenities")
    return ", ".join(interventions[:3]).capitalize() + "."


def recommend_action_summary(row: dict) -> str:
    return " | ".join(recommend_action_labels(row)[:3])


def summarize_contributors(labels: Iterable[str]) -> str:
    labels = [label for label in labels if label]
    if not labels:
        return "overall corridor heat burden"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{labels[0]}, {labels[1]}, and {labels[2]}"


def planner_note_payload(row: dict, top_contributors: list[str]) -> dict:
    return {
        "stop_name": row.get("stop_name"),
        "corridor_name": row.get("corridor_name"),
        "route_short_name": row.get("route_short_name"),
        "direction_id": row.get("direction_id"),
        "priority_score": row.get("priority_score"),
        "relative_corridor_risk": row.get("normalized_priority_score"),
        "shelter_present": row.get("shelter_present_effective"),
        "nearby_seating": row.get("bench_present_effective"),
        "tree_cover_proxy": row.get("combined_tree_cover_score"),
        "open_sky_ratio": row.get("open_sky_ratio"),
        "heat_burden_score": row.get("heat_burden_value", row.get("heat_burden_score")),
        "weather_metric": row.get("weather_metric_display") or row.get("weather_metric_used"),
        "weather_value_f": row.get("max_weather_value_f"),
        "avg_headway_minutes": row.get("avg_headway_minutes"),
        "top_contributors": top_contributors,
        "recommended_action_labels": recommend_action_labels(row),
    }


def _urgency_from_row(row: dict) -> str:
    score = float(row.get("normalized_priority_score") or row.get("priority_score") or 0.0)
    if score >= 85:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _fallback_planner_note(row: dict, top_contributors: list[str]) -> dict:
    contributor_text = summarize_contributors(top_contributors)
    intervention = recommend_intervention(row).rstrip(".")
    if intervention:
        intervention = intervention[0].lower() + intervention[1:]
    current_heat = row.get("max_weather_value_f")
    heat_context = ""
    if current_heat is not None and (row.get("heat_burden_value", row.get("heat_burden_score")) or 0) > 0:
        metric_name = row.get("weather_metric_display") or row.get("weather_metric_used") or "heat snapshot"
        heat_context = f" under the current {metric_name.lower()} of {current_heat:.1f}°F"

    reason = f"This stop is a {_urgency_from_row(row).lower()} priority because it combines {contributor_text}{heat_context}."
    recommendation = f"The most practical near-term intervention is to {intervention}."
    return {
        "planner_note": f"{reason} {recommendation}",
        "planner_note_reason": reason,
        "planner_note_recommendation": recommendation,
        "planner_note_urgency": _urgency_from_row(row),
        "planner_note_source": "Deterministic fallback",
    }


def build_planner_note(row: dict, top_contributors: list[str], mode: str = "fallback") -> dict:
    if mode == "auto":
        payload = planner_note_payload(row, top_contributors)
        llm_result = generate_grounded_planner_note(payload)
        if llm_result:
            planner_note = f"{llm_result['reason']} {llm_result['recommendation']}"
            return {
                "planner_note": planner_note,
                "planner_note_reason": llm_result["reason"],
                "planner_note_recommendation": llm_result["recommendation"],
                "planner_note_urgency": llm_result["urgency"],
                "planner_note_source": llm_result["source"],
            }
    return _fallback_planner_note(row, top_contributors)
