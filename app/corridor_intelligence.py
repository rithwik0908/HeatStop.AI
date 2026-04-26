from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from app.llm import generate_grounded_structured_output, llm_source_label
from app.vulnerability import enrich_stops_with_vulnerability


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _risk_label(score: float) -> str:
    if score >= 85:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _pretty_driver(label: str) -> str:
    return str(label).replace("scheduled ", "").title()


def _split_contributors(raw: Any) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _display_score_columns(stops_df: pd.DataFrame) -> tuple[str, str, str, str]:
    score_col = "display_priority_score" if "display_priority_score" in stops_df.columns else "priority_score"
    rel_col = "display_relative_risk" if "display_relative_risk" in stops_df.columns else "normalized_priority_score"
    driver_col = "display_top_contributors" if "display_top_contributors" in stops_df.columns else "top_contributors"
    action_col = "display_recommended_action_summary" if "display_recommended_action_summary" in stops_df.columns else "recommended_action_summary"
    return score_col, rel_col, driver_col, action_col


def _effective_shelter_present(row: pd.Series) -> bool | None:
    if bool(row.get("display_has_field_review_override")):
        return True
    value = row.get("has_shelter")
    if pd.isna(value):
        return None
    return bool(value)


def _effective_segment_labels(stops_df: pd.DataFrame) -> pd.DataFrame:
    frame = stops_df.copy()
    order_col = "route_rank" if "route_rank" in frame.columns else ("stop_sequence" if "stop_sequence" in frame.columns else None)
    if order_col:
        frame = frame.sort_values(order_col, ascending=True).reset_index(drop=True)
    else:
        frame = frame.reset_index(drop=True)

    n = len(frame)
    frame["segment_index"] = [min(int(idx * 3 / max(n, 1)), 2) for idx in range(n)]
    lat_span = pd.to_numeric(frame["stop_lat"], errors="coerce").max() - pd.to_numeric(frame["stop_lat"], errors="coerce").min()
    lon_span = pd.to_numeric(frame["stop_lon"], errors="coerce").max() - pd.to_numeric(frame["stop_lon"], errors="coerce").min()
    orientation = "north_south" if lat_span >= lon_span else "east_west"

    segment_centers = (
        frame.groupby("segment_index")[["stop_lat", "stop_lon"]]
        .mean(numeric_only=True)
        .reset_index()
    )
    if orientation == "north_south":
        ordered = segment_centers.sort_values("stop_lat").reset_index(drop=True)
        labels = ["Southern segment", "Central segment", "Northern segment"]
    else:
        ordered = segment_centers.sort_values("stop_lon").reset_index(drop=True)
        labels = ["Western segment", "Central segment", "Eastern segment"]
    segment_label_map = {
        int(ordered.iloc[idx]["segment_index"]): labels[idx]
        for idx in range(min(len(ordered), 3))
    }
    frame["segment_label"] = frame["segment_index"].map(segment_label_map).fillna("Corridor segment")
    frame["corridor_orientation"] = orientation
    return frame


def compute_corridor_features(stops_df: pd.DataFrame, meta: dict) -> dict[str, Any]:
    score_col, rel_col, driver_col, action_col = _display_score_columns(stops_df)
    working = _effective_segment_labels(stops_df)
    working["_score"] = pd.to_numeric(working[score_col], errors="coerce").fillna(0.0)
    working["_relative_risk"] = pd.to_numeric(working[rel_col], errors="coerce").fillna(0.0)
    working["_headway"] = pd.to_numeric(working.get("avg_headway_minutes"), errors="coerce")
    working["_tree_cover"] = pd.to_numeric(working.get("combined_tree_cover_score"), errors="coerce")
    working["_heat"] = pd.to_numeric(working.get("heat_burden_score"), errors="coerce").fillna(0.0)
    working["risk_category"] = working["_relative_risk"].map(_risk_label)
    working["effective_shelter_present"] = working.apply(_effective_shelter_present, axis=1)
    working["is_unsheltered_effective"] = working["effective_shelter_present"].map(lambda value: np.nan if value is None else not bool(value))

    total_burden = float(working["_score"].sum())
    top5_burden_share = 0.0
    if total_burden > 0:
        top5_burden_share = round(float(working.nlargest(5, "_score")["_score"].sum()) / total_burden * 100, 1)

    driver_counter = Counter()
    for raw in working[driver_col].fillna(""):
        driver_counter.update(_split_contributors(raw))
    dominant_drivers = [driver for driver, _ in driver_counter.most_common(3)]

    segment_stats = (
        working.groupby("segment_label", as_index=False)
        .agg(
            stop_count=("stop_id", "count"),
            avg_display_score=("_score", "mean"),
            avg_relative_risk=("_relative_risk", "mean"),
            total_burden=("_score", "sum"),
            unsheltered_stops=("is_unsheltered_effective", lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())),
            critical_stops=("risk_category", lambda s: int(pd.Series(s).isin(["Critical", "High"]).sum())),
        )
        .sort_values(["total_burden", "avg_relative_risk"], ascending=[False, False])
        .reset_index(drop=True)
    )
    if not segment_stats.empty:
        segment_stats["unsheltered_pct"] = (segment_stats["unsheltered_stops"] / segment_stats["stop_count"] * 100).round(1)
    top_segment = segment_stats.iloc[0].to_dict() if not segment_stats.empty else {}

    top_stops = []
    for _, row in working.nlargest(min(5, len(working)), "_score").iterrows():
        top_stops.append(
            {
                "stop_id": str(row["stop_id"]),
                "stop_name": row["stop_name"],
                "segment_label": row["segment_label"],
                "display_score": round(float(row["_score"]), 2),
                "relative_risk": round(float(row["_relative_risk"]), 2),
                "risk_category": row["risk_category"],
                "drivers": _split_contributors(row[driver_col])[:3],
                "action_summary": row.get(action_col),
            }
        )

    weather = meta.get("weather", {})
    features = {
        "corridor_name": meta.get("corridor_name") or meta.get("label"),
        "corridor_id": meta.get("corridor_id"),
        "route_short_name": meta.get("route_short_name"),
        "direction_id": meta.get("direction_id"),
        "stop_count": int(len(working)),
        "unsheltered_pct": round(float(pd.Series(working["is_unsheltered_effective"]).fillna(False).astype(bool).mean() * 100), 1),
        "avg_tree_cover_score": round(float(working["_tree_cover"].mean()), 3) if working["_tree_cover"].notna().any() else None,
        "avg_wait_minutes": round(float(working["_headway"].mean()), 2) if working["_headway"].notna().any() else None,
        "avg_display_score": round(float(working["_score"].mean()), 2),
        "avg_relative_risk": round(float(working["_relative_risk"].mean()), 2),
        "critical_or_high_count": int(working["risk_category"].isin(["Critical", "High"]).sum()),
        "top5_burden_share_pct": top5_burden_share,
        "dominant_drivers": dominant_drivers,
        "segment_stats": segment_stats.to_dict(orient="records"),
        "top_segment": top_segment,
        "top_stops": top_stops,
        "weather": {
            "metric_display": weather.get("metric_display"),
            "value_f": weather.get("value_f"),
            "summary": weather.get("summary"),
            "updated_at": weather.get("updated_at"),
        },
        "working_stops": working,
    }
    return features


def _vulnerability_severity(row: pd.Series) -> tuple[str, str | None]:
    proxy_points = 2 * int(bool(row.get("near_hospital"))) + 2 * int(bool(row.get("near_senior_center"))) + 1 * int(bool(row.get("near_school")))
    display_risk = _safe_float(row.get("display_relative_risk"))
    heat_factor = _safe_float(row.get("heat_burden_score"))
    heat_value_f = _safe_float(row.get("max_weather_value_f"))
    heat_active = heat_factor >= 0.35 or heat_value_f >= 85
    if proxy_points >= 2 and display_risk >= 65 and heat_active:
        return "Critical", "High heat overlaps with vulnerable nearby uses."
    if proxy_points >= 2 and display_risk >= 50:
        return "High", "Elevated stop risk overlaps with vulnerable nearby uses."
    if proxy_points >= 1 and display_risk >= 40:
        return "Medium", "Moderate stop risk overlaps with place-based vulnerability proxies."
    return "Low", None


def build_vulnerability_features(stops_df: pd.DataFrame, meta: dict) -> dict[str, Any]:
    corridor_id = meta.get("corridor_id")
    try:
        enriched, facilities = enrich_stops_with_vulnerability(stops_df, corridor_id=corridor_id)
    except Exception:
        enriched = stops_df.copy()
        facilities = pd.DataFrame()
        for column, default in {
            "near_hospital": False,
            "near_senior_center": False,
            "near_school": False,
            "vulnerability_proxy_count": 0,
        }.items():
            enriched[column] = default
    enriched["vulnerability_severity"] = "Low"
    enriched["vulnerability_reason"] = None
    for idx, row in enriched.iterrows():
        severity, reason = _vulnerability_severity(row)
        enriched.loc[idx, "vulnerability_severity"] = severity
        enriched.loc[idx, "vulnerability_reason"] = reason

    proxied = enriched.loc[enriched["vulnerability_proxy_count"] > 0].copy()
    escalated = enriched.loc[enriched["vulnerability_severity"].isin(["Critical", "High"])].copy()
    escalated = escalated.sort_values(["display_relative_risk", "display_priority_score"], ascending=[False, False])
    escalated_records = []
    for _, row in escalated.head(5).iterrows():
        tags = [tag for tag in ["hospital", "senior center", "school"] if row.get(f"near_{tag.replace(' ', '_')}")]
        escalated_records.append(
            {
                "stop_id": str(row["stop_id"]),
                "stop_name": row["stop_name"],
                "segment_label": row.get("segment_label"),
                "relative_risk": round(_safe_float(row.get("display_relative_risk")), 2),
                "severity": row["vulnerability_severity"],
                "reason": row["vulnerability_reason"],
                "proxy_tags": tags,
            }
        )

    features = {
        "facility_source": "NYC Facilities Database",
        "facilities_rows": int(len(facilities)),
        "near_hospital_count": int(enriched["near_hospital"].sum()) if "near_hospital" in enriched else 0,
        "near_senior_center_count": int(enriched["near_senior_center"].sum()) if "near_senior_center" in enriched else 0,
        "near_school_count": int(enriched["near_school"].sum()) if "near_school" in enriched else 0,
        "proxied_stop_count": int(len(proxied)),
        "critical_overlap_count": int((enriched["vulnerability_severity"] == "Critical").sum()),
        "high_or_critical_overlap_count": int(enriched["vulnerability_severity"].isin(["Critical", "High"]).sum()),
        "escalated_stops": escalated_records,
        "working_stops": enriched,
    }
    return features


ANALYST_SCHEMA = {
    "type": "object",
    "properties": {
        "corridor_summary": {"type": "string"},
        "dominant_drivers": {"type": "array", "items": {"type": "string"}},
        "top_segment": {"type": "string"},
        "signature_insight": {"type": "string"},
        "severity_label": {"type": "string", "enum": ["Low", "Medium", "High", "Critical"]},
    },
    "required": ["corridor_summary", "dominant_drivers", "top_segment", "signature_insight", "severity_label"],
    "additionalProperties": False,
}

VULNERABILITY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "critical_findings": {"type": "array", "items": {"type": "string"}},
        "vulnerable_segment_summary": {"type": "string"},
        "severity_label": {"type": "string", "enum": ["Low", "Medium", "High", "Critical"]},
    },
    "required": ["summary", "critical_findings", "vulnerable_segment_summary", "severity_label"],
    "additionalProperties": False,
}

PLANNING_SCHEMA = {
    "type": "object",
    "properties": {
        "top_actions": {"type": "array", "items": {"type": "string"}},
        "priority_segment": {"type": "string"},
        "intervention_mix": {"type": "array", "items": {"type": "string"}},
        "planner_memo": {"type": "string"},
    },
    "required": ["top_actions", "priority_segment", "intervention_mix", "planner_memo"],
    "additionalProperties": False,
}


def _analyst_payload(corridor: dict[str, Any]) -> dict[str, Any]:
    return {
        "corridor_name": corridor["corridor_name"],
        "stop_count": corridor["stop_count"],
        "unsheltered_pct": corridor["unsheltered_pct"],
        "avg_relative_risk": corridor["avg_relative_risk"],
        "critical_or_high_count": corridor["critical_or_high_count"],
        "top5_burden_share_pct": corridor["top5_burden_share_pct"],
        "dominant_drivers": corridor["dominant_drivers"],
        "segment_stats": corridor["segment_stats"],
        "top_stops": corridor["top_stops"],
        "weather": corridor["weather"],
    }


def _analyst_fallback(corridor: dict[str, Any]) -> dict[str, Any]:
    top_segment = corridor.get("top_segment") or {}
    dominant = [_pretty_driver(item) for item in corridor.get("dominant_drivers", [])]
    unsheltered_pct = corridor.get("unsheltered_pct", 0.0)
    top5_share = corridor.get("top5_burden_share_pct", 0.0)
    segment = top_segment.get("segment_label", "corridor core")
    critical_count = corridor.get("critical_or_high_count", 0)
    severity = _risk_label(_safe_float(corridor.get("avg_relative_risk")))
    summary = (
        f"{unsheltered_pct:.0f}% of scored stops are effectively unsheltered, and "
        f"{critical_count} stops currently sit in the high or critical band."
    )
    signature = (
        f"The top 5 stops account for {top5_share:.0f}% of total corridor priority burden, "
        f"with the strongest concentration in the {segment.lower()}."
    )
    return {
        "corridor_summary": summary,
        "dominant_drivers": dominant or ["Mixed corridor drivers"],
        "top_segment": f"{segment} carries the highest total display burden in the current corridor view.",
        "signature_insight": signature,
        "severity_label": severity,
        "source": llm_source_label(),
    }


def _vulnerability_payload(corridor: dict[str, Any], vulnerability: dict[str, Any], analyst: dict[str, Any]) -> dict[str, Any]:
    return {
        "corridor_name": corridor["corridor_name"],
        "weather": corridor["weather"],
        "analyst_summary": analyst,
        "proxied_stop_count": vulnerability["proxied_stop_count"],
        "near_hospital_count": vulnerability["near_hospital_count"],
        "near_senior_center_count": vulnerability["near_senior_center_count"],
        "near_school_count": vulnerability["near_school_count"],
        "critical_overlap_count": vulnerability["critical_overlap_count"],
        "high_or_critical_overlap_count": vulnerability["high_or_critical_overlap_count"],
        "escalated_stops": vulnerability["escalated_stops"],
    }


def _vulnerability_fallback(corridor: dict[str, Any], vulnerability: dict[str, Any], analyst: dict[str, Any]) -> dict[str, Any]:
    critical_overlap = vulnerability["critical_overlap_count"]
    high_overlap = vulnerability["high_or_critical_overlap_count"]
    escalated = vulnerability["escalated_stops"]
    segment_counts = Counter(item["segment_label"] for item in escalated if item.get("segment_label"))
    vulnerable_segment = segment_counts.most_common(1)[0][0] if segment_counts else (corridor.get("top_segment") or {}).get("segment_label", "corridor")

    if critical_overlap > 0:
        summary = f"{critical_overlap} stops reach a critical vulnerability overlap under current heat and display risk conditions."
        severity = "Critical"
    elif high_overlap > 0:
        summary = f"{high_overlap} stops pair elevated corridor risk with nearby vulnerable uses."
        severity = "High"
    elif vulnerability["proxied_stop_count"] > 0:
        summary = f"{vulnerability['proxied_stop_count']} stops sit near schools, senior centers, or hospitals, but current heat overlap is limited."
        severity = "Medium"
    else:
        summary = "No scored stops currently overlap the selected vulnerability proxies within the configured walking-distance thresholds."
        severity = "Low"

    findings = []
    for record in escalated[:3]:
        tags = ", ".join(record["proxy_tags"])
        findings.append(
            f"{record['stop_name']} is {record['severity'].lower()} because it pairs {record['relative_risk']:.1f} corridor risk with nearby {tags}."
        )
    if not findings:
        findings.append("No stop currently meets the app's high heat plus high vulnerability escalation threshold.")

    segment_summary = f"The {vulnerable_segment.lower()} has the strongest concentration of vulnerability-linked priority stops."
    return {
        "summary": summary,
        "critical_findings": findings,
        "vulnerable_segment_summary": segment_summary,
        "severity_label": severity,
        "source": llm_source_label(),
    }


def _planning_payload(corridor: dict[str, Any], vulnerability: dict[str, Any], analyst_output: dict[str, Any], vulnerability_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "corridor_name": corridor["corridor_name"],
        "analyst_output": analyst_output,
        "vulnerability_output": vulnerability_output,
        "top_stops": corridor["top_stops"],
        "top_segment": corridor["top_segment"],
        "recommended_actions": Counter(
            action.strip()
            for raw in [stop.get("action_summary", "") for stop in corridor["top_stops"]]
            for action in str(raw).split("|")
            if action.strip()
        ).most_common(6),
    }


def _planning_fallback(corridor: dict[str, Any], vulnerability: dict[str, Any], analyst_output: dict[str, Any], vulnerability_output: dict[str, Any]) -> dict[str, Any]:
    action_counts = Counter(
        action.strip()
        for raw in [stop.get("action_summary", "") for stop in corridor["top_stops"]]
        for action in str(raw).split("|")
        if action.strip()
    )
    top_actions = [action for action, _ in action_counts.most_common(3)] or ["Monitor corridor conditions"]
    top_segment = (corridor.get("top_segment") or {}).get("segment_label", "corridor")
    intervention_mix = top_actions
    memo = (
        f"Prioritize {', '.join(action.lower() for action in top_actions[:2])} in the {top_segment.lower()} first, "
        f"because that segment carries the strongest display burden and aligns with {analyst_output['dominant_drivers'][0].lower()}."
    )
    if vulnerability["high_or_critical_overlap_count"] > 0:
        memo += f" Vulnerability overlap indicates {vulnerability['high_or_critical_overlap_count']} stops deserve escalated field attention during current heat conditions."
    return {
        "top_actions": top_actions,
        "priority_segment": top_segment,
        "intervention_mix": intervention_mix,
        "planner_memo": memo,
        "source": llm_source_label(),
    }


def _run_corridor_analyst_agent(corridor: dict[str, Any]) -> dict[str, Any]:
    payload = _analyst_payload(corridor)
    system_prompt = (
        "You are the Corridor Analyst Agent for a transit heat resilience tool. "
        "Reason only from the provided structured corridor evidence. "
        "Do not invent counts, percentages, segments, or amenities. "
        "Return concise planner-facing JSON. "
        "Top segment should identify the segment with the strongest burden pattern. "
        "Signature insight should be a memorable one-sentence quantified finding."
    )
    llm_output = generate_grounded_structured_output(
        payload,
        system_prompt=system_prompt,
        schema_name="corridor_analyst_agent",
        schema=ANALYST_SCHEMA,
        max_completion_tokens=320,
    )
    if llm_output:
        return llm_output
    return _analyst_fallback(corridor)


def _run_vulnerability_agent(corridor: dict[str, Any], vulnerability: dict[str, Any], analyst_output: dict[str, Any]) -> dict[str, Any]:
    payload = _vulnerability_payload(corridor, vulnerability, analyst_output)
    system_prompt = (
        "You are the Vulnerability Agent for a transit heat resilience tool. "
        "Use only the provided vulnerability proxy evidence and corridor facts. "
        "Do not invent hospitals, schools, senior centers, or severity levels. "
        "Escalate to Critical only when the provided structured inputs justify high heat plus high vulnerability overlap."
    )
    llm_output = generate_grounded_structured_output(
        payload,
        system_prompt=system_prompt,
        schema_name="vulnerability_agent",
        schema=VULNERABILITY_SCHEMA,
        max_completion_tokens=360,
    )
    if llm_output:
        return llm_output
    return _vulnerability_fallback(corridor, vulnerability, analyst_output)


def _run_action_planning_agent(
    corridor: dict[str, Any],
    vulnerability: dict[str, Any],
    analyst_output: dict[str, Any],
    vulnerability_output: dict[str, Any],
) -> dict[str, Any]:
    payload = _planning_payload(corridor, vulnerability, analyst_output, vulnerability_output)
    system_prompt = (
        "You are the Action Planning Agent for a transit heat resilience tool. "
        "Use only the provided corridor evidence, analyst findings, vulnerability findings, and stop actions. "
        "Do not invent budgets, interventions, or segments. "
        "Recommend a concise, ordered action mix and a short planner memo."
    )
    llm_output = generate_grounded_structured_output(
        payload,
        system_prompt=system_prompt,
        schema_name="action_planning_agent",
        schema=PLANNING_SCHEMA,
        max_completion_tokens=360,
    )
    if llm_output:
        return llm_output
    return _planning_fallback(corridor, vulnerability, analyst_output, vulnerability_output)


def generate_corridor_intelligence(stops_df: pd.DataFrame, meta: dict) -> dict[str, Any]:
    corridor = compute_corridor_features(stops_df, meta)
    vulnerability = build_vulnerability_features(corridor["working_stops"], meta)

    try:
        analyst_output = _run_corridor_analyst_agent(corridor)
    except Exception:
        analyst_output = _analyst_fallback(corridor)
    try:
        vulnerability_output = _run_vulnerability_agent(corridor, vulnerability, analyst_output)
    except Exception:
        vulnerability_output = _vulnerability_fallback(corridor, vulnerability, analyst_output)
    try:
        planning_output = _run_action_planning_agent(corridor, vulnerability, analyst_output, vulnerability_output)
    except Exception:
        planning_output = _planning_fallback(corridor, vulnerability, analyst_output, vulnerability_output)

    evidence = {
        "stop_count": corridor["stop_count"],
        "unsheltered_pct": corridor["unsheltered_pct"],
        "top5_burden_share_pct": corridor["top5_burden_share_pct"],
        "dominant_drivers": [_pretty_driver(item) for item in corridor["dominant_drivers"]],
        "top_segment": corridor.get("top_segment", {}).get("segment_label"),
        "high_or_critical_stops": corridor["critical_or_high_count"],
        "vulnerability_overlap_count": vulnerability["high_or_critical_overlap_count"],
        "critical_overlap_count": vulnerability["critical_overlap_count"],
        "facility_source": vulnerability["facility_source"],
    }

    return {
        "corridor_id": meta.get("corridor_id"),
        "corridor_name": corridor["corridor_name"],
        "waiting_zone_id": meta.get("corridor_id"),
        "waiting_zone_name": corridor["corridor_name"],
        "waiting_zone_type": "corridor",
        "source_of_truth": "Transparent waiting-point scoring pipeline",
        "reasoning_mode": analyst_output.get("source", llm_source_label()),
        "evidence": evidence,
        "analyst": analyst_output,
        "vulnerability": vulnerability_output,
        "planning": planning_output,
        "vulnerability_evidence": vulnerability,
        "corridor_features": {
            "segment_stats": corridor["segment_stats"],
            "top_stops": corridor["top_stops"],
        },
    }


def generate_waiting_zone_intelligence(stops_df: pd.DataFrame, meta: dict) -> dict[str, Any]:
    return generate_corridor_intelligence(stops_df, meta)
