from __future__ import annotations

from typing import Any

import pandas as pd

from app.capabilities import build_capability_registry
from app.llm import generate_grounded_structured_output, llm_source_label
from app.proxy_estimates import extract_budget_amount
from app.rider_copilot import build_wait_guidance


COPILOT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "follow_up_tip": {"type": "string"},
    },
    "required": ["answer", "follow_up_tip"],
    "additionalProperties": False,
}


QUESTION_EXAMPLES = [
    "Why is this waiting point high priority?",
    "What upgrade should happen first here?",
    "My bus is late. Where can I wait nearby?",
    "Is there a lower-risk nearby stop?",
    "How many people are near this waiting point?",
    "What evidence is missing here?",
]


def _detect_intents(question: str | None) -> list[str]:
    text = str(question or "").lower().strip()
    if not text:
        return ["wait_guidance", "stop_heat_risk", "next_bus_eta"]

    intents: list[str] = []
    if any(token in text for token in ["heat risk", "how hot", "risk level", "hot here", "heat-response"]):
        intents.append("stop_heat_risk")
    if any(token in text for token in ["why", "high priority", "why is this stop", "why is this waiting point", "priority"]):
        intents.append("priority_reason")
    if any(token in text for token in ["upgrade", "improve", "fix first", "what should happen first", "intervention"]):
        intents.append("upgrade_priority")
    if "budget" in text or "$" in text or "under" in text and any(ch.isdigit() for ch in text):
        intents.append("budget_actions")
    if any(token in text for token in ["nearby place", "wait nearby", "cooler", "shade", "shaded", "water", "pharmacy", "cafe", "library", "indoor"]):
        intents.append("nearby_relief_places")
    if any(token in text for token in ["eta", "when is the bus", "next bus", "arrival", "late"]):
        intents.append("next_bus_eta")
    if any(token in text for token in ["safer stop", "lower-risk", "lower risk", "other stop", "nearby stop"]):
        intents.append("lower_risk_stop")
    if any(token in text for token in ["corridor", "segment", "pattern", "cluster", "across the route"]):
        intents.append("corridor_patterns")
    if any(token in text for token in ["vulnerab", "hospital", "senior", "school", "most affected"]):
        intents.append("vulnerability_overlap")
    if any(token in text for token in ["missing", "evidence", "unknown", "unavailable", "not measured"]):
        intents.append("missing_evidence")
    if any(token in text for token in ["how many people", "people near", "footfall", "activity around", "crowded stop"]):
        intents.append("people_activity")
    if any(token in text for token in ["noise", "loud", "sound level"]):
        intents.append("noise_level")
    if any(token in text for token in ["packed", "crowded bus", "bus crowded", "occupancy"]):
        intents.append("bus_crowding")
    if any(token in text for token in ["exposed", "exposure", "feel here", "how exposed"]):
        intents.append("exposure_feel")
    if any(token in text for token in ["stay", "move", "too hot", "what should i do", "wait here"]):
        intents.append("wait_guidance")

    if not intents:
        intents = ["wait_guidance", "stop_heat_risk"]

    ordered: list[str] = []
    seen: set[str] = set()
    for intent in intents:
        if intent not in seen:
            ordered.append(intent)
            seen.add(intent)
    return ordered


def _budget_override(capability: dict[str, Any], question: str | None) -> dict[str, Any]:
    budget_amount = extract_budget_amount(question)
    if budget_amount is None:
        return capability
    clone = dict(capability)
    actions = clone.get("value") or []
    if budget_amount < 25000:
        if isinstance(actions, list) and actions:
            chosen = [action for action in actions if action in {"Add seating", "Service review"}] or actions[:1]
        else:
            chosen = ["Lower-scope amenity fixes"]
        clone["summary"] = (
            f"HeatStop does not have a verified capital cost model. Estimated (medium confidence): with a tighter budget around "
            f"${budget_amount:,.0f}, start with {', '.join(action.lower() for action in chosen)} before larger canopy or tree projects."
        )
    elif budget_amount < 100000:
        clone["summary"] = (
            f"HeatStop does not have a verified capital cost model. Estimated (medium confidence): with a mid-range budget around "
            f"${budget_amount:,.0f}, you can likely combine one shelter or tree intervention with the top lower-scope amenity fix."
        )
    else:
        clone["summary"] = (
            f"HeatStop does not have a verified capital cost model. Estimated (medium confidence): with a larger budget around "
            f"${budget_amount:,.0f}, the current full action mix looks plausible for this waiting point."
        )
    return clone


def _section_from_capability(capability: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": capability["label"],
        "signal_name": capability["signal_name"],
        "tier": capability["evidence_tier"],
        "confidence": capability.get("confidence") or "n/a",
        "status": capability["status"],
        "summary": capability["summary"],
        "sources": capability.get("sources") or [],
    }


def _deterministic_answer(question: str | None, sections: list[dict[str, Any]]) -> tuple[str, str]:
    if not sections:
        return (
            "No grounded HeatStop signal matched that question closely enough.",
            "Try asking about stop heat risk, bus ETA, nearby safer places, corridor patterns, or missing evidence.",
        )
    primary = sections[0]
    tier = primary["tier"]
    confidence = primary.get("confidence", "n/a")
    answer = f"{tier}: {primary['summary']}"
    if tier == "Estimated" and confidence != "n/a":
        answer += f" Confidence: {confidence}."
    if tier == "Unavailable":
        answer += " HeatStop is surfacing the closest grounded signal instead of guessing."

    if len(sections) > 1:
        extras = ", ".join(section["title"] for section in sections[1:3])
        tip = f"I also checked {extras.lower()} for this question."
    else:
        sources = primary.get("sources") or []
        source_text = ", ".join(sources[:2]) if sources else "HeatStop evidence"
        tip = f"Source: {source_text}."
    return answer, tip


def _llm_polish(question: str | None, sections: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, str] | None:
    payload = {
        "question": question,
        "sections": sections,
        "context": context,
        "instructions": {
            "must_preserve_tiers": True,
            "must_preserve_estimated_labels": True,
            "must_preserve_unavailable_labels": True,
        },
    }
    system_prompt = (
        "You are HeatStop Copilot, a stop and corridor assistant. "
        "Use only the structured section records provided. "
        "Never invent feeds, places, ETAs, budgets, crowding, or counts. "
        "If a section is Estimated, explicitly say it is estimated or proxy-based. "
        "If a section is Unavailable, explicitly say it is unavailable and mention the closest available related signal when present. "
        "Return JSON with answer and follow_up_tip only."
    )
    result = generate_grounded_structured_output(
        payload,
        system_prompt=system_prompt,
        schema_name="heatstop_copilot_answer",
        schema=COPILOT_RESPONSE_SCHEMA,
        temperature=0.2,
        max_completion_tokens=260,
    )
    if not result:
        return None
    return {
        "answer": str(result.get("answer", "")).strip(),
        "follow_up_tip": str(result.get("follow_up_tip", "")).strip(),
        "source": result.get("source", llm_source_label()),
    }


def answer_heatstop_copilot(
    question: str | None,
    stop: dict[str, Any],
    corridor_stops: pd.DataFrame,
    rider_support: dict[str, Any],
    corridor_intelligence: dict[str, Any] | None,
) -> dict[str, Any]:
    guidance = build_wait_guidance(stop, corridor_stops, rider_support.get("arrivals", {}), rider_support.get("nearby_relief", {}))
    capabilities = build_capability_registry(stop, corridor_stops, rider_support, corridor_intelligence, guidance)
    intents = _detect_intents(question)

    sections: list[dict[str, Any]] = []
    for intent in intents:
        capability = capabilities.get(intent)
        if capability is None:
            continue
        if intent == "budget_actions":
            capability = _budget_override(capability, question)
        sections.append(_section_from_capability(capability))

    if not sections:
        sections.append(_section_from_capability(capabilities["wait_guidance"]))

    deterministic_answer, deterministic_tip = _deterministic_answer(question, sections)
    llm_result = _llm_polish(
        question,
        sections,
        {
            "stop_name": stop.get("stop_name"),
            "route_short_name": stop.get("route_short_name"),
            "guidance": {
                "headline": guidance.get("headline"),
                "summary": guidance.get("summary"),
            },
        },
    )

    primary = sections[0]
    answer = llm_result["answer"] if llm_result else deterministic_answer
    follow_up_tip = llm_result["follow_up_tip"] if llm_result else deterministic_tip
    source = llm_result["source"] if llm_result else "Deterministic capability router"

    available_related = [
        {
            "label": record["label"],
            "tier": record["evidence_tier"],
            "status": record["status"],
        }
        for key, record in capabilities.items()
        if key not in {section["signal_name"] for section in sections}
        and record["status"] != "unavailable"
    ][:6]

    return {
        "question": question or "What should I do here right now?",
        "answer": answer,
        "follow_up_tip": follow_up_tip,
        "source": source,
        "primary_tier": primary["tier"],
        "primary_confidence": primary["confidence"],
        "sections": sections,
        "related_signals": available_related,
        "intents": intents,
        "examples": QUESTION_EXAMPLES,
        "guidance": guidance,
        "capabilities": capabilities,
    }
