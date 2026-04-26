from app.corridor_intelligence import (
    build_vulnerability_features,
    compute_corridor_features,
    generate_corridor_intelligence,
)


def generate_waiting_zone_intelligence(*args, **kwargs):
    return generate_corridor_intelligence(*args, **kwargs)


__all__ = [
    "build_vulnerability_features",
    "compute_corridor_features",
    "generate_corridor_intelligence",
    "generate_waiting_zone_intelligence",
]
