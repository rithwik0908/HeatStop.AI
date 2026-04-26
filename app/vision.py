from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from app.config import IMAGES_DIR, settings


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
VISION_LABELS = ["bus stop shelter", "shade canopy", "bench"]
SHELTER_LABELS = {"bus stop shelter", "shade canopy"}


def _safe_ratio(mask: np.ndarray) -> float:
    return float(mask.mean()) if mask.size else 0.0


def _find_image_path(stop_id: str, images_dir: Path) -> Path | None:
    manifest_path = images_dir / "manifest.csv"
    if manifest_path.exists():
        manifest = pd.read_csv(manifest_path, dtype=str).fillna("")
        match = manifest.loc[manifest["stop_id"] == str(stop_id)]
        if not match.empty:
            candidate = images_dir / match.iloc[0]["file_name"]
            if candidate.exists():
                return candidate
    for extension in IMAGE_EXTENSIONS:
        candidate = images_dir / f"{stop_id}{extension}"
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def _load_pretrained_detector() -> tuple[object | None, str]:
    if not settings.enable_pretrained_vision:
        return None, "pretrained detector disabled (heuristic-only mode)"
    try:
        from transformers import pipeline

        detector = pipeline(
            task="zero-shot-object-detection",
            model=settings.pretrained_vision_model,
            device="cpu",
        )
        return detector, "ok"
    except Exception as exc:
        return None, f"pretrained detector unavailable: {exc.__class__.__name__}"


def _run_pretrained_detection(image_path: Path) -> dict:
    detector, status = _load_pretrained_detector()
    result = {
        "vision_model_name": settings.pretrained_vision_model if settings.enable_pretrained_vision else None,
        "vision_model_status": status,
        "shelter_model_detected": None,
        "shelter_model_confidence": None,
        "bench_model_detected": None,
        "bench_model_confidence": None,
        "model_detection_summary": None,
    }
    if detector is None:
        return result

    try:
        predictions = detector(str(image_path), candidate_labels=VISION_LABELS, threshold=settings.pretrained_vision_threshold)
    except Exception as exc:
        result["vision_model_status"] = f"pretrained inference failed: {exc.__class__.__name__}"
        return result

    shelter_confidence = 0.0
    bench_confidence = 0.0
    summary: list[str] = []
    for item in predictions:
        label = str(item.get("label", "")).strip().lower()
        score = float(item.get("score", 0.0))
        if label in SHELTER_LABELS:
            shelter_confidence = max(shelter_confidence, score)
        if label == "bench":
            bench_confidence = max(bench_confidence, score)
        summary.append(f"{label}:{score:.2f}")

    result.update(
        {
            "shelter_model_detected": bool(shelter_confidence >= settings.pretrained_vision_threshold),
            "shelter_model_confidence": round(shelter_confidence, 3) if shelter_confidence > 0 else None,
            "bench_model_detected": bool(bench_confidence >= settings.pretrained_vision_threshold),
            "bench_model_confidence": round(bench_confidence, 3) if bench_confidence > 0 else None,
            "model_detection_summary": ", ".join(summary) if summary else "no objects above threshold",
        }
    )
    return result


@lru_cache(maxsize=256)
def _analyze_image_cached(image_path_str: str, modified_at: float) -> dict:
    image_path = Path(image_path_str)
    image = cv2.imread(str(image_path))
    if image is None:
        return {
            "image_available": False,
            "image_path": str(image_path),
            "vision_error": "OpenCV could not read the image.",
            "vision_model_name": settings.pretrained_vision_model if settings.enable_pretrained_vision else None,
            "vision_model_status": "image unreadable (OpenCV failed)",
            "shelter_model_detected": None,
            "shelter_model_confidence": None,
            "bench_model_detected": None,
            "bench_model_confidence": None,
            "model_detection_summary": None,
        }

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    height, width = rgb.shape[:2]

    green_mask = cv2.inRange(hsv, (30, 30, 20), (95, 255, 255)) > 0
    upper_half = hsv[: max(height // 2, 1), :]

    sky_mask = cv2.inRange(upper_half, (80, 10, 80), (140, 160, 255)) > 0
    bright_open_mask = cv2.inRange(upper_half, (0, 0, 170), (180, 55, 255)) > 0
    open_sky_ratio = min(1.0, _safe_ratio(sky_mask) + 0.5 * _safe_ratio(bright_open_mask))
    tree_ratio = _safe_ratio(green_mask)

    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 80, 180)
    top_edges = edges[: max(int(height * 0.45), 1), :]
    lower_edges = edges[int(height * 0.5) :, :]

    shelter_lines = cv2.HoughLinesP(top_edges, 1, np.pi / 180, threshold=45, minLineLength=max(width // 6, 25), maxLineGap=12)
    bench_lines = cv2.HoughLinesP(lower_edges, 1, np.pi / 180, threshold=25, minLineLength=max(width // 8, 20), maxLineGap=10)

    horizontal_shelter_lines = 0
    if shelter_lines is not None:
        for line in shelter_lines[:, 0]:
            x1, y1, x2, y2 = line
            if abs(y2 - y1) <= 6:
                horizontal_shelter_lines += 1

    horizontal_bench_lines = 0
    if bench_lines is not None:
        for line in bench_lines[:, 0]:
            x1, y1, x2, y2 = line
            if abs(y2 - y1) <= 5:
                horizontal_bench_lines += 1

    shelter_heuristic_score = min(1.0, 0.55 * (horizontal_shelter_lines / 8.0) + 0.45 * max(0.0, 0.75 - open_sky_ratio))
    bench_heuristic_score = min(1.0, horizontal_bench_lines / 10.0)
    model_result = _run_pretrained_detection(image_path)

    shelter_model_detected = model_result.get("shelter_model_detected")
    bench_model_detected = model_result.get("bench_model_detected")
    shelter_model_confidence = model_result.get("shelter_model_confidence")
    bench_model_confidence = model_result.get("bench_model_confidence")

    shelter_estimate = (
        bool(shelter_model_detected)
        if shelter_model_detected is not None
        else bool(shelter_heuristic_score >= 0.55)
    )
    bench_estimate = (
        bool(bench_model_detected)
        if bench_model_detected is not None
        else bool(bench_heuristic_score >= 0.45)
    )

    shelter_confidence = shelter_model_confidence if shelter_model_confidence is not None else round(float(shelter_heuristic_score), 3)
    bench_confidence = bench_model_confidence if bench_model_confidence is not None else round(float(bench_heuristic_score), 3)

    method = "Pretrained zero-shot detector + OpenCV heuristics"
    if str(model_result.get("vision_model_status")) != "ok":
        method = "OpenCV color-mask and edge-line heuristics"

    return {
        "image_available": True,
        "image_path": str(image_path),
        "visible_tree_ratio": round(tree_ratio, 3),
        "open_sky_ratio": round(open_sky_ratio, 3),
        "shelter_image_estimate": shelter_estimate,
        "shelter_image_confidence": shelter_confidence,
        "bench_image_estimate": bench_estimate,
        "bench_image_confidence": bench_confidence,
        "shelter_heuristic_estimate": bool(shelter_heuristic_score >= 0.55),
        "shelter_heuristic_confidence": round(float(shelter_heuristic_score), 3),
        "bench_heuristic_estimate": bool(bench_heuristic_score >= 0.45),
        "bench_heuristic_confidence": round(float(bench_heuristic_score), 3),
        "vision_method": method,
        "vision_model_name": model_result.get("vision_model_name"),
        "vision_model_status": model_result.get("vision_model_status"),
        "shelter_model_detected": shelter_model_detected,
        "shelter_model_confidence": shelter_model_confidence,
        "bench_model_detected": bench_model_detected,
        "bench_model_confidence": bench_model_confidence,
        "model_detection_summary": model_result.get("model_detection_summary"),
        "vision_error": None,
    }


def analyze_image(image_path: Path) -> dict:
    stat = image_path.stat()
    return _analyze_image_cached(str(image_path), stat.st_mtime)


def analyze_stop_images(stops_df: pd.DataFrame, images_dir: Path | None = None) -> pd.DataFrame:
    images_dir = images_dir or IMAGES_DIR
    rows = []
    for stop in stops_df.to_dict(orient="records"):
        stop_id = str(stop["stop_id"])
        explicit_path = stop.get("resolved_image_path")
        image_path = Path(explicit_path) if explicit_path and Path(explicit_path).exists() else _find_image_path(stop_id, images_dir)
        if image_path is None:
            rows.append(
                {
                    "stop_id": stop_id,
                    "image_available": False,
                    "image_path": None,
                    "visible_tree_ratio": None,
                    "open_sky_ratio": None,
                    "shelter_image_estimate": None,
                    "shelter_image_confidence": None,
                    "bench_image_estimate": None,
                    "bench_image_confidence": None,
                    "shelter_heuristic_estimate": None,
                    "shelter_heuristic_confidence": None,
                    "bench_heuristic_estimate": None,
                    "bench_heuristic_confidence": None,
                    "shelter_model_detected": None,
                    "shelter_model_confidence": None,
                    "bench_model_detected": None,
                    "bench_model_confidence": None,
                    "model_detection_summary": None,
                    "vision_method": None,
                    "vision_model_name": settings.pretrained_vision_model if settings.enable_pretrained_vision else None,
                    "vision_model_status": "image unavailable (heuristic analysis skipped)",
                    "vision_error": "image unavailable",
                }
            )
            continue
        result = analyze_image(image_path)
        result["stop_id"] = stop_id
        rows.append(result)
    return pd.DataFrame(rows)
