WAITING_POINT_FEATURE_LABELS = {
    "no_shelter": "no shelter",
    "low_tree_cover": "low tree cover",
    "heat_burden": "high heat burden",
    "wait_burden": "long scheduled wait exposure",
    "no_bench": "nearby seating gap",
}


def waiting_point_priority_label(score: float) -> str:
    if score >= 85:
        return "Critical exposure priority"
    if score >= 65:
        return "High exposure priority"
    if score >= 40:
        return "Elevated resilience concern"
    return "Lower immediate urgency"
