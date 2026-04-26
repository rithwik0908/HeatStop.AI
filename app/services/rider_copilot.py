from app.rider_copilot import build_wait_guidance, build_waiting_guidance, find_lower_risk_stop_candidates


def find_lower_exposure_waiting_points(*args, **kwargs):
    return find_lower_risk_stop_candidates(*args, **kwargs)


__all__ = [
    "build_wait_guidance",
    "build_waiting_guidance",
    "find_lower_exposure_waiting_points",
    "find_lower_risk_stop_candidates",
]
