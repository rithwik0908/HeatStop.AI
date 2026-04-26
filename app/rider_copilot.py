from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.config import settings
from app.llm import generate_grounded_structured_output, llm_source_label


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _walking_minutes(distance_m: float) -> int:
    return max(int(math.ceil(distance_m / max(settings.rider_walking_speed_m_per_min, 1.0))), 1)


def _risk_label(score: float) -> str:
    if score >= 85:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _choose_place(places: list[dict[str, Any]], preferred_kinds: set[str]) -> dict[str, Any] | None:
    filtered = [place for place in places if place.get("kind") in preferred_kinds]
    if not filtered:
        return None
    return sorted(filtered, key=lambda place: (place.get("walking_minutes", 999), place.get("distance_m", 9999)))[0]


def _top_arrival(arrivals_payload: dict[str, Any]) -> dict[str, Any] | None:
    relevant_items = arrivals_payload.get("relevant_items") or []
    if relevant_items:
        return relevant_items[0]
    items = arrivals_payload.get("items") or []
    return items[0] if items else None


def find_lower_risk_stop_candidates(selected_stop: dict[str, Any], corridor_stops: pd.DataFrame) -> list[dict[str, Any]]:
    if corridor_stops.empty:
        return []
    selected_risk = _safe_float(selected_stop.get("display_relative_risk", selected_stop.get("normalized_priority_score")))
    selected_lat = _safe_float(selected_stop.get("stop_lat"))
    selected_lon = _safe_float(selected_stop.get("stop_lon"))
    candidates: list[dict[str, Any]] = []
    for _, row in corridor_stops.iterrows():
        stop_id = str(row.get("stop_id"))
        if stop_id == str(selected_stop.get("stop_id")):
            continue
        candidate_risk = _safe_float(row.get("display_relative_risk", row.get("normalized_priority_score")))
        if candidate_risk > selected_risk - settings.lower_risk_stop_min_risk_drop:
            continue
        distance_m = _haversine_m(selected_lat, selected_lon, _safe_float(row.get("stop_lat")), _safe_float(row.get("stop_lon")))
        if distance_m > settings.lower_risk_stop_radius_m:
            continue
        candidates.append(
            {
                "stop_id": stop_id,
                "stop_name": row.get("stop_name"),
                "relative_risk": round(candidate_risk, 1),
                "distance_m": round(distance_m, 1),
                "walking_minutes": _walking_minutes(distance_m),
                "has_shelter": bool(row.get("has_shelter")) if not pd.isna(row.get("has_shelter")) else None,
                "has_nearby_seating": bool(row.get("has_nearby_seating")) if not pd.isna(row.get("has_nearby_seating")) else None,
                "route_short_name": row.get("route_short_name"),
            }
        )
    candidates.sort(key=lambda item: (item["walking_minutes"], item["relative_risk"], item["distance_m"]))
    return candidates[:3]


def build_wait_guidance(
    selected_stop: dict[str, Any],
    corridor_stops: pd.DataFrame,
    arrivals_payload: dict[str, Any],
    relief_payload: dict[str, Any],
) -> dict[str, Any]:
    risk_score = _safe_float(selected_stop.get("display_relative_risk", selected_stop.get("normalized_priority_score")))
    risk_label = _risk_label(risk_score)
    next_arrival = _top_arrival(arrivals_payload)
    eta_minutes = next_arrival.get("eta_minutes") if next_arrival else None
    relief_places = relief_payload.get("items") or []
    lower_risk_candidates = find_lower_risk_stop_candidates(selected_stop, corridor_stops)

    indoor_place = _choose_place(relief_places, {"indoor_public_space", "indoor_service", "indoor_seating"})
    shaded_place = _choose_place(relief_places, {"outdoor_shade", "indoor_public_space", "indoor_seating"})
    utility_place = indoor_place or shaded_place or (relief_places[0] if relief_places else None)
    lower_risk_stop = lower_risk_candidates[0] if lower_risk_candidates else None

    decision_mode = "stay_near_stop"
    headline = "Stay near the stop for now."
    summary = "The current evidence does not justify moving away from the stop."
    reasoning: list[str] = []
    steps: list[str] = []

    if eta_minutes is None:
        decision_mode = "arrival_unavailable"
        headline = "Live arrivals are unavailable right now."
        summary = (
            f"This stop is currently rated {risk_label.lower()} heat risk, so use nearby shade or indoor relief if you expect a longer wait."
        )
        reasoning.append("Real-time bus arrival data is unavailable, so the copilot is grounding advice in stop heat risk and nearby relief options only.")
        if risk_label in {"Critical", "High"} and utility_place:
            decision_mode = "seek_relief_without_eta"
            headline = "Use a safer nearby waiting place while monitoring arrivals."
            summary = (
                f"This stop is {risk_label.lower()} risk and the best nearby option is {utility_place['name']} "
                f"({utility_place['walking_minutes']} min walk, {utility_place['category'].lower()})."
            )
            steps.append(f"Move to {utility_place['name']} if you expect the bus to be delayed.")
        elif risk_label in {"Critical", "High"} and lower_risk_stop:
            decision_mode = "use_lower_risk_stop_without_eta"
            headline = "A lower-exposure nearby stop is the safest fallback."
            summary = (
                f"{lower_risk_stop['stop_name']} is about {lower_risk_stop['walking_minutes']} minutes away and carries lower HeatStop risk."
            )
            steps.append(f"Consider walking to {lower_risk_stop['stop_name']} if you can still catch your route safely.")
        else:
            steps.append("Stay alert for bus updates and minimize direct sun exposure near the current stop.")
    elif eta_minutes <= 5:
        reasoning.append(f"The next bus is expected in about {eta_minutes} minutes.")
        if risk_label == "Critical" and lower_risk_stop and lower_risk_stop["walking_minutes"] <= 3:
            decision_mode = "move_to_lower_risk_stop"
            headline = "A nearby lower-exposure stop is worth the short walk."
            summary = (
                f"The next bus is close, but {lower_risk_stop['stop_name']} is only {lower_risk_stop['walking_minutes']} minutes away "
                f"and has meaningfully lower heat risk."
            )
            steps.append(f"Walk to {lower_risk_stop['stop_name']} now if you can do it without missing the bus.")
        else:
            summary = (
                f"The next bus is close enough that staying near {selected_stop['stop_name']} is the practical choice."
            )
            steps.append("Stay close to the stop and keep to the smallest shaded edge available.")
    elif eta_minutes <= 12:
        reasoning.append(f"The next bus is expected in about {eta_minutes} minutes.")
        if risk_label == "Critical" and lower_risk_stop and lower_risk_stop["walking_minutes"] <= 5:
            decision_mode = "move_to_lower_risk_stop"
            headline = "Switch to a lower-exposure nearby stop."
            summary = (
                f"With a {eta_minutes}-minute wait at a critical-risk stop, {lower_risk_stop['stop_name']} is the safer nearby option."
            )
            steps.append(f"Walk {lower_risk_stop['walking_minutes']} minutes to {lower_risk_stop['stop_name']}.")
        elif shaded_place:
            decision_mode = "wait_at_relief_place"
            headline = "Use a nearby shaded or seated waiting option."
            summary = (
                f"You have enough time to step to {shaded_place['name']} "
                f"({shaded_place['walking_minutes']} min walk) and return before the bus."
            )
            steps.append(f"Wait at {shaded_place['name']} for a few minutes, then return before the bus is due.")
        else:
            summary = "There is some wait time, but no stronger nearby relief option was found."
            steps.append("Stay near the stop and reduce direct sun exposure as much as possible.")
    else:
        reasoning.append(f"The next bus is expected in about {eta_minutes} minutes.")
        if indoor_place:
            decision_mode = "wait_indoor"
            headline = "Use a nearby indoor waiting option."
            summary = (
                f"With a longer wait, {indoor_place['name']} is the best nearby relief option "
                f"({indoor_place['walking_minutes']} min walk, {indoor_place['category'].lower()})."
            )
            steps.append(f"Wait at {indoor_place['name']} and return closer to the bus arrival time.")
        elif lower_risk_stop:
            decision_mode = "move_to_lower_risk_stop"
            headline = "A lower-exposure nearby stop is preferable for this wait."
            summary = (
                f"The bus is not close, and {lower_risk_stop['stop_name']} offers a lower-risk waiting alternative."
            )
            steps.append(f"Walk to {lower_risk_stop['stop_name']} if you want a cooler wait without leaving the corridor.")
        elif shaded_place:
            decision_mode = "wait_at_relief_place"
            headline = "Move to a nearby lower-exposure waiting spot."
            summary = f"{shaded_place['name']} is the closest relief option for a wait of more than 12 minutes."
            steps.append(f"Use {shaded_place['name']} while you wait, then return before the bus arrives.")
        else:
            summary = "The bus is still a while away, but no safer nearby place was found in the configured categories."
            steps.append("If possible, create shade, hydrate, and limit direct sun exposure while staying near the stop.")

    if utility_place and decision_mode in {"stay_near_stop", "arrival_unavailable"}:
        reasoning.append(f"The nearest relief option found is {utility_place['name']} ({utility_place['walking_minutes']} min walk).")
    if lower_risk_stop:
        reasoning.append(
            f"{lower_risk_stop['stop_name']} is a nearby lower-risk stop at {lower_risk_stop['walking_minutes']} minutes on foot."
        )
    if risk_label in {"Critical", "High"}:
        reasoning.append(f"HeatStop currently rates this stop as {risk_label.lower()} risk.")

    if not steps:
        steps.append("Keep the bus in view if possible and minimize direct sun while waiting.")

    return {
        "decision_mode": decision_mode,
        "risk_label": risk_label,
        "risk_score": round(risk_score, 1),
        "headline": headline,
        "summary": summary,
        "reasoning": reasoning,
        "steps": steps,
        "next_arrival": next_arrival,
        "nearby_relief_place": utility_place,
        "lower_risk_stop": lower_risk_stop,
        "lower_risk_candidates": lower_risk_candidates,
        "relief_places": relief_places,
        "arrivals_status": arrivals_payload.get("status"),
        "relief_status": relief_payload.get("status"),
    }


RIDER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "follow_up_tip": {"type": "string"},
    },
    "required": ["answer", "follow_up_tip"],
    "additionalProperties": False,
}


def _fallback_copilot_response(question: str | None, guidance: dict[str, Any]) -> dict[str, str]:
    next_arrival = guidance.get("next_arrival") or {}
    eta_minutes = next_arrival.get("eta_minutes")
    question_text = str(question or "").lower().strip()
    arrival_text = (
        f"Next bus arrives in about {eta_minutes} minutes. "
        if eta_minutes is not None
        else "Live arrival timing is unavailable right now. "
    )
    relief_place = guidance.get("nearby_relief_place") or {}
    lower_risk_stop = guidance.get("lower_risk_stop") or {}
    relief_places = guidance.get("relief_places") or []

    if any(token in question_text for token in ["water", "hydrate", "drink"]):
        water_places = [place for place in relief_places if place.get("kind") in {"water_access", "indoor_service"}]
        if water_places:
            place = sorted(water_places, key=lambda item: (item.get("walking_minutes", 999), item.get("distance_m", 9999)))[0]
            answer = (
                f"{arrival_text}The closest useful water-access option is {place['name']} "
                f"({place['walking_minutes']} min walk, {place['category'].lower()})."
            )
            tip = f"Go there now if you need water, then come back before the bus is due."
            return {"answer": answer, "follow_up_tip": tip, "source": "Deterministic fallback"}

    if any(token in question_text for token in ["lower-risk", "safer stop", "another stop", "other stop"]):
        if lower_risk_stop:
            answer = (
                f"{arrival_text}{lower_risk_stop['stop_name']} is the best lower-exposure nearby stop option "
                f"({lower_risk_stop['walking_minutes']} min walk, risk {lower_risk_stop['relative_risk']})."
            )
            tip = "Only switch stops if you can make the walk without missing the next bus."
        else:
            answer = f"{arrival_text}No nearby stop on this corridor met the current lower-risk threshold."
            tip = guidance["steps"][0] if guidance.get("steps") else "Minimize direct sun while you wait."
        return {"answer": answer, "follow_up_tip": tip, "source": "Deterministic fallback"}

    if any(token in question_text for token in ["indoor", "inside", "cooler", "shade", "shaded", "wait nearby", "where can i wait"]):
        if relief_place:
            answer = (
                f"{arrival_text}{relief_place['name']} is the best nearby waiting option right now "
                f"({relief_place['walking_minutes']} min walk, {relief_place['category'].lower()})."
            )
            tip = guidance["steps"][0] if guidance.get("steps") else f"Use {relief_place['name']} while you wait."
        else:
            answer = f"{arrival_text}{guidance['headline']} {guidance['summary']}"
            tip = guidance["steps"][0] if guidance.get("steps") else "Minimize direct sun while you wait."
        return {"answer": answer, "follow_up_tip": tip, "source": "Deterministic fallback"}

    if any(token in question_text for token in ["stay", "leave", "move", "what should i do", "too hot"]):
        answer = f"{arrival_text}{guidance['headline']} {guidance['summary']}"
        tip = guidance["steps"][0] if guidance.get("steps") else "Minimize direct sun while you wait."
        return {"answer": answer, "follow_up_tip": tip, "source": "Deterministic fallback"}

    answer = f"{arrival_text}{guidance['headline']} {guidance['summary']}"
    tip = guidance["steps"][0] if guidance.get("steps") else "Minimize direct sun while you wait."
    return {"answer": answer, "follow_up_tip": tip, "source": "Deterministic fallback"}


def build_rider_copilot_response(question: str | None, guidance: dict[str, Any], selected_stop: dict[str, Any]) -> dict[str, str]:
    if not question:
        return _fallback_copilot_response(question, guidance)

    payload = {
        "question": question,
        "stop_name": selected_stop.get("stop_name"),
        "route_short_name": selected_stop.get("route_short_name"),
        "risk_label": guidance.get("risk_label"),
        "risk_score": guidance.get("risk_score"),
        "deterministic_headline": guidance.get("headline"),
        "deterministic_summary": guidance.get("summary"),
        "next_arrival": guidance.get("next_arrival"),
        "recommended_relief_place": guidance.get("nearby_relief_place"),
        "recommended_lower_risk_stop": guidance.get("lower_risk_stop"),
        "supporting_steps": guidance.get("steps"),
        "reasoning": guidance.get("reasoning"),
    }
    llm_result = generate_grounded_structured_output(
        payload,
        system_prompt=(
            "You are HeatStop Nearby Relief Copilot. "
            "Answer only from the structured inputs provided. "
            "Do not invent bus ETAs, stop conditions, or nearby places. "
            "Keep the answer concise, practical, and focused on heat-aware waiting guidance. "
            "If live arrivals are unavailable, say so. "
            "Return JSON only with keys answer and follow_up_tip."
        ),
        schema_name="rider_copilot_response",
        schema=RIDER_RESPONSE_SCHEMA,
        temperature=0.2,
        max_completion_tokens=260,
    )
    if not llm_result:
        return _fallback_copilot_response(question, guidance)
    return {
        "answer": llm_result["answer"],
        "follow_up_tip": llm_result["follow_up_tip"],
        "source": llm_source_label(),
    }
