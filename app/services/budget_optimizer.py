from __future__ import annotations


def budget_optimizer_extension_note() -> dict[str, str]:
    return {
        "status": "future_extension",
        "message": "Budget optimization is not yet a standalone service. The current MVP uses waiting-point action heuristics and corridor intelligence as the planning base.",
    }
