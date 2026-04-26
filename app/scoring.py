from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from app.config import DEFAULT_SCORE_WEIGHTS
from app.planner import build_planner_note, recommend_action_summary, recommend_intervention


FEATURE_LABELS = {
    "no_shelter": "no shelter",
    "low_tree_cover": "low tree cover",
    "heat_burden": "high heat burden",
    "wait_burden": "long scheduled wait exposure",
    "no_bench": "nearby seating gap",
}


def _normalize(values: pd.Series, lower: float | None = None, upper: float | None = None) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce")
    if lower is None:
        lower = float(series.min()) if series.notna().any() else 0.0
    if upper is None:
        upper = float(series.max()) if series.notna().any() else 1.0
    if upper == lower:
        return pd.Series(np.where(series.notna(), 0.5, np.nan), index=series.index, dtype=float)
    return ((series - lower) / (upper - lower)).clip(0, 1)


def score_stops(
    stops_df: pd.DataFrame,
    weights: dict[str, float] | None = None,
    planner_mode: str = "fallback",
) -> pd.DataFrame:
    weights = weights or DEFAULT_SCORE_WEIGHTS.copy()
    df = stops_df.copy()

    df["shelter_present_effective"] = df["has_shelter"].where(df["has_shelter"].notna(), df["shelter_image_estimate"])
    df["bench_present_effective"] = df["has_nearby_seating"].where(df["has_nearby_seating"].notna(), df["bench_image_estimate"])

    municipal_tree_score = (pd.to_numeric(df["nearby_tree_count"], errors="coerce") / 6.0).clip(0, 1)
    if "visible_tree_ratio" in df:
        image_tree_score = pd.to_numeric(df["visible_tree_ratio"], errors="coerce").clip(0, 1)
        df["combined_tree_cover_score"] = pd.concat([municipal_tree_score, image_tree_score], axis=1).mean(axis=1, skipna=True)
    else:
        df["combined_tree_cover_score"] = municipal_tree_score

    df["no_shelter_value"] = df["shelter_present_effective"].map(
        lambda value: np.nan if pd.isna(value) else float(not bool(value))
    )
    df["no_bench_value"] = df["bench_present_effective"].map(
        lambda value: np.nan if pd.isna(value) else float(not bool(value))
    )
    df["low_tree_cover_value"] = 1.0 - pd.to_numeric(df["combined_tree_cover_score"], errors="coerce").clip(0, 1)
    df["heat_burden_value"] = pd.to_numeric(df["heat_burden_score"], errors="coerce").clip(0, 1)
    df["wait_burden_value"] = _normalize(pd.to_numeric(df["avg_headway_minutes"], errors="coerce"), lower=5, upper=25)

    value_columns = {
        "no_shelter": "no_shelter_value",
        "low_tree_cover": "low_tree_cover_value",
        "heat_burden": "heat_burden_value",
        "wait_burden": "wait_burden_value",
        "no_bench": "no_bench_value",
    }

    breakdowns: list[str] = []
    top_contributors: list[list[str]] = []
    raw_scores: list[float] = []

    for _, row in df.iterrows():
        available = {
            feature: weights[feature]
            for feature, column in value_columns.items()
            if pd.notna(row[column])
        }
        weight_sum = float(sum(available.values()))
        if weight_sum == 0:
            raw_scores.append(0.0)
            breakdowns.append(json.dumps({}))
            top_contributors.append([])
            continue

        breakdown: dict[str, Any] = {}
        for feature, base_weight in available.items():
            column = value_columns[feature]
            normalized_weight = base_weight / weight_sum
            component_score = round(float(row[column]) * normalized_weight * 100, 2)
            breakdown[feature] = {
                "label": FEATURE_LABELS[feature],
                "value": round(float(row[column]), 3),
                "weight": round(normalized_weight, 3),
                "score": component_score,
            }

        ordered = sorted(breakdown.items(), key=lambda item: item[1]["score"], reverse=True)
        top_labels = [item[1]["label"] for item in ordered[:3] if item[1]["score"] > 0]
        score_total = round(sum(item["score"] for item in breakdown.values()), 2)
        raw_scores.append(score_total)
        breakdowns.append(json.dumps(breakdown))
        top_contributors.append(top_labels)

    df["priority_score"] = raw_scores
    if df["priority_score"].nunique(dropna=False) <= 1:
        df["normalized_priority_score"] = df["priority_score"].round(2)
    else:
        df["normalized_priority_score"] = (_normalize(df["priority_score"]) * 100).round(2)

    df["score_breakdown_json"] = breakdowns
    df["top_contributors"] = [", ".join(labels) for labels in top_contributors]
    df["recommended_intervention"] = [recommend_intervention(row) for _, row in df.iterrows()]
    df["recommended_action_summary"] = [recommend_action_summary(row) for _, row in df.iterrows()]

    planner_records = [
        build_planner_note(row.to_dict(), labels, mode=planner_mode) for (_, row), labels in zip(df.iterrows(), top_contributors)
    ]
    df["planner_note"] = [record["planner_note"] for record in planner_records]
    df["planner_note_reason"] = [record["planner_note_reason"] for record in planner_records]
    df["planner_note_recommendation"] = [record["planner_note_recommendation"] for record in planner_records]
    df["planner_note_urgency"] = [record["planner_note_urgency"] for record in planner_records]
    df["planner_note_source"] = [record["planner_note_source"] for record in planner_records]
    return df.sort_values(["priority_score", "avg_headway_minutes"], ascending=[False, False]).reset_index(drop=True)
