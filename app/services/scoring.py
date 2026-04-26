from app.scoring import score_stops


def score_waiting_points(*args, **kwargs):
    return score_stops(*args, **kwargs)


__all__ = ["score_stops", "score_waiting_points"]
