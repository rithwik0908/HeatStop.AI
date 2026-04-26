from __future__ import annotations

from typing import Any

import pandas as pd

from app.proxy_estimates import (
    estimate_budget_actions,
    estimate_bus_crowding,
    estimate_exposure_feel,
    estimate_noise_level,
    estimate_people_activity,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _make_capability(
    signal_name: str,
    label: str,
    status: str,
    evidence_tier: str,
    summary: str,
    *,
    value: Any = None,
    confidence: str | None = None,
    sources: list[str] | None = None,
    closest_available_signal: str | None = None,
) -> dict[str, Any]:
    return {
        "signal_name": signal_name,
        "label": label,
        "status": status,
        "evidence_tier": evidence_tier,
        "summary": summary,
        "value": value,
        "confidence": confidence,
        "sources": sources or [],
        "closest_available_signal": closest_available_signal,
    }


def _missing_evidence_summary(stop: dict[str, Any], rider_support: dict[str, Any]) -> tuple[str, list[str]]:
    missing: list[str] = []
    if not (stop.get("image_provider") or stop.get("display_image_provider")):
        missing.append("No verified waiting-point photo is currently available.")
    arrivals = rider_support.get("arrivals", {})
    if not (arrivals.get("next_arrival") or {}).get("eta_minutes"):
        missing.append("Live bus ETA is unavailable right now.")
    missing.append("HeatStop does not currently measure verified live people counts.")
    missing.append("HeatStop does not currently measure verified live noise levels.")
    missing.append("HeatStop does not currently have a verified bus occupancy feed.")
    return " ".join(missing[:3]), missing


def build_capability_registry(
    stop: dict[str, Any],
    corridor_stops: pd.DataFrame,
    rider_support: dict[str, Any],
    corridor_intelligence: dict[str, Any] | None,
    guidance: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    route_name = str(stop.get("route_short_name") or "")
    risk_score = _safe_float(stop.get("display_relative_risk", stop.get("normalized_priority_score")))
    risk_label = guidance.get("risk_label") or ("Critical" if risk_score >= 85 else "High" if risk_score >= 65 else "Medium" if risk_score >= 40 else "Low")
    weather_value = stop.get("max_weather_value_f")
    weather_metric = stop.get("weather_metric_display") or stop.get("weather_metric_used") or "corridor heat snapshot"
    arrivals = rider_support.get("arrivals", {})
    nearby_relief = rider_support.get("nearby_relief", {})
    next_arrival = arrivals.get("next_arrival") or {}
    lower_risk_stop = guidance.get("lower_risk_stop")
    display_top_contributors = str(stop.get("display_top_contributors") or stop.get("top_contributors") or "No dominant drivers listed")
    recommendation = str(stop.get("display_recommended_action_summary") or stop.get("recommended_action_summary") or stop.get("recommended_intervention") or "No recommendation available")
    planner_note = str(stop.get("display_planner_note") or stop.get("planner_note") or "No planner note available")
    corridor_evidence = (corridor_intelligence or {}).get("evidence", {})
    analyst = (corridor_intelligence or {}).get("analyst", {})
    vulnerability = (corridor_intelligence or {}).get("vulnerability", {})

    missing_summary, missing_items = _missing_evidence_summary(stop, rider_support)

    registry: dict[str, dict[str, Any]] = {
        "stop_heat_risk": _make_capability(
            "stop_heat_risk",
            "Waiting-point heat risk",
            "verified",
            "Verified",
            (
                f"This waiting point is currently in the {risk_label.lower()} HeatStop risk band at {risk_score:.1f}. "
                f"The active weather input is {weather_metric.lower()}"
                + (f" at {float(weather_value):.1f}°F." if weather_value is not None else ".")
            ),
            value={"risk_score": round(risk_score, 1), "risk_label": risk_label},
            confidence="High",
            sources=["Transparent HeatStop waiting-point scoring", "NWS / weather.gov"],
        ),
        "priority_reason": _make_capability(
            "priority_reason",
            "Why this waiting point is high priority",
            "verified",
            "Verified",
            f"HeatStop ranks this waiting point highly because of {display_top_contributors.lower()}. {planner_note}",
            value=display_top_contributors,
            confidence="High",
            sources=["Transparent HeatStop score breakdown", "Planner note"],
        ),
        "upgrade_priority": _make_capability(
            "upgrade_priority",
            "Upgrade that should happen first",
            "verified",
            "Verified",
            f"The current leading intervention is {recommendation.lower()}.",
            value=recommendation,
            confidence="High",
            sources=["HeatStop recommended action"],
        ),
        "budget_actions": estimate_budget_actions(stop, None),
        "corridor_patterns": _make_capability(
            "corridor_patterns",
            "Corridor-level risk patterns",
            "verified",
            "Verified",
            (
                f"{analyst.get('corridor_summary', 'Corridor summary unavailable.')} "
                f"Priority segment: {corridor_evidence.get('top_segment') or 'n/a'}. "
                f"Dominant drivers: {', '.join(corridor_evidence.get('dominant_drivers', [])) or 'n/a'}."
            ),
            value={
                "top_segment": corridor_evidence.get("top_segment"),
                "unsheltered_pct": corridor_evidence.get("unsheltered_pct"),
                "top5_burden_share_pct": corridor_evidence.get("top5_burden_share_pct"),
            },
            confidence="High",
            sources=["Transparent HeatStop scoring pipeline", "Corridor Intelligence evidence"],
        ),
        "vulnerability_overlap": _make_capability(
            "vulnerability_overlap",
            "Vulnerability proxy overlap",
            "verified",
            "Verified",
            (
                f"{vulnerability.get('summary', 'No vulnerability overlap summary is currently available.')} "
                f"{vulnerability.get('vulnerable_segment_summary', '')}".strip()
            ),
            value={
                "critical_overlap_count": corridor_evidence.get("critical_overlap_count"),
                "vulnerability_overlap_count": corridor_evidence.get("vulnerability_overlap_count"),
            },
            confidence="High",
            sources=["NYC Facilities Database", "Corridor Intelligence vulnerability layer"],
        ),
        "missing_evidence": _make_capability(
            "missing_evidence",
            "What evidence is missing",
            "verified",
            "Verified",
            missing_summary or "Core waiting-point evidence is currently available.",
            value=missing_items,
            confidence="High",
            sources=["Capability status checker"],
        ),
        "people_activity": estimate_people_activity(stop, corridor_stops, rider_support),
        "noise_level": estimate_noise_level(stop, rider_support),
        "bus_crowding": estimate_bus_crowding(stop, rider_support, corridor_intelligence),
        "exposure_feel": estimate_exposure_feel(stop),
    }

    if next_arrival.get("eta_minutes") is not None:
        registry["next_bus_eta"] = _make_capability(
            "next_bus_eta",
            "Next bus ETA",
            "verified",
            "Live",
            (
                f"The next {next_arrival.get('route') or route_name or 'bus'} "
                f"{'to ' + str(next_arrival.get('destination')) if next_arrival.get('destination') else ''} "
                f"is expected in about {int(next_arrival.get('eta_minutes'))} minutes."
            ).replace("  ", " "),
            value=next_arrival,
            confidence="High",
            sources=[arrivals.get("source_label", "MTA Bus Time / SIRI StopMonitoring")],
        )
    else:
        registry["next_bus_eta"] = _make_capability(
            "next_bus_eta",
            "Next bus ETA",
            "unavailable",
            "Unavailable",
            arrivals.get("message") or "Live bus ETA is not available right now.",
            confidence=None,
            sources=[arrivals.get("source_label", "MTA Bus Time / SIRI StopMonitoring")],
            closest_available_signal="Average scheduled headway",
        )

    relief_places = nearby_relief.get("items") or []
    if relief_places:
        top_place = relief_places[0]
        registry["nearby_relief_places"] = _make_capability(
            "nearby_relief_places",
            "Nearby safer waiting places",
            "verified",
            "Verified",
            (
                f"{len(relief_places)} nearby relief places were found. The closest practical option is "
                f"{top_place['name']} ({top_place['walking_minutes']} min walk, {str(top_place['category']).lower()})."
            ),
            value=relief_places,
            confidence="High",
            sources=[nearby_relief.get("source_label", "OpenStreetMap / Overpass API")],
        )
    else:
        registry["nearby_relief_places"] = _make_capability(
            "nearby_relief_places",
            "Nearby safer waiting places",
            "unavailable",
            "Unavailable",
            nearby_relief.get("message") or "No nearby relief places are available from the configured open categories right now.",
            confidence=None,
            sources=[nearby_relief.get("source_label", "OpenStreetMap / Overpass API")],
            closest_available_signal="Heat-aware waiting guidance",
        )

    if lower_risk_stop:
        registry["lower_risk_stop"] = _make_capability(
            "lower_risk_stop",
            "Lower-risk nearby bus stop",
            "verified",
            "Verified",
            (
                f"{lower_risk_stop['stop_name']} is a lower-exposure option about {lower_risk_stop['walking_minutes']} minutes away, "
                f"with relative risk {lower_risk_stop['relative_risk']}."
            ),
            value=lower_risk_stop,
            confidence="High",
            sources=["Existing HeatStop stop scoring", "Walk-distance filter"],
        )
    else:
        registry["lower_risk_stop"] = _make_capability(
            "lower_risk_stop",
            "Lower-risk nearby bus stop",
            "unavailable",
            "Unavailable",
            "No nearby stop on this corridor met the current walk-distance and risk-drop thresholds.",
            confidence=None,
            sources=["Existing HeatStop stop scoring"],
            closest_available_signal="Current waiting-point risk",
        )

    registry["wait_guidance"] = _make_capability(
        "wait_guidance",
        "Heat-aware waiting guidance",
        "verified" if guidance.get("arrivals_status") == "ok" else "estimated",
        "Live" if guidance.get("arrivals_status") == "ok" else "Estimated",
        f"{guidance.get('headline')} {guidance.get('summary')}",
        value={"decision_mode": guidance.get("decision_mode"), "steps": guidance.get("steps")},
        confidence="High" if guidance.get("arrivals_status") == "ok" else "Medium",
        sources=["HeatStop waiting-point risk", arrivals.get("source_label", "MTA Bus Time / SIRI StopMonitoring"), nearby_relief.get("source_label", "OpenStreetMap / Overpass API")],
    )

    return registry
