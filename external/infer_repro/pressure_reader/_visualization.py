"""Visualization helpers — draw detection results on gauge images."""
from typing import List, Optional, Tuple

import cv2
import numpy as np


def draw_auto_result(image: np.ndarray,
                     zero_point: Tuple[float, float],
                     end_point: Tuple[float, float],
                     center_point: Tuple[float, float],
                     pointer_tip: Optional[Tuple[float, float]],
                     circle_center: Optional[Tuple[float, float]] = None,
                     circle_radius: Optional[float] = None,
                     ) -> np.ndarray:
    """Draw YOLO boxes, circle, pointer, and tick markers. Returns new image."""
    vis = image.copy()
    cx, cy = int(center_point[0]), int(center_point[1])
    cv2.circle(vis, (cx, cy), 5, (0, 0, 255), -1)

    cv2.drawMarker(vis, (int(zero_point[0]), int(zero_point[1])),
                   (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
    cv2.drawMarker(vis, (int(end_point[0]), int(end_point[1])),
                   (255, 0, 0), cv2.MARKER_CROSS, 10, 2)

    if pointer_tip is not None:
        cv2.circle(vis, (int(pointer_tip[0]), int(pointer_tip[1])),
                   5, (0, 0, 255), 2)

    if circle_center is not None and circle_radius is not None:
        cv2.circle(vis, (int(circle_center[0]), int(circle_center[1])),
                   int(circle_radius), (0, 255, 255), 2)

    return vis


def draw_manual_result(image: np.ndarray,
                       clicks: List[Tuple[float, float]],
                       center: Tuple[float, float],
                       ) -> np.ndarray:
    """Draw manual calibration points: 0=green, Max=blue, Tip=red."""
    vis = image.copy()
    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255)]
    labels = ["0", "Max", "Tip"]
    cx, cy = int(center[0]), int(center[1])

    for i, (x, y) in enumerate(clicks):
        ix, iy = int(x), int(y)
        cv2.circle(vis, (ix, iy), 6, colors[i], 2)
        cv2.putText(vis, labels[i], (ix + 8, iy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, colors[i], 2)
        cv2.line(vis, (cx, cy), (ix, iy), colors[i], 1)

    cv2.circle(vis, (cx, cy), 4, (0, 255, 255), -1)
    return vis


def draw_ocr_result(image: np.ndarray,
                    items: List[dict],
                    ) -> np.ndarray:
    """Draw OCR bounding boxes: green=classified, gray=unclassified."""
    vis = image.copy()
    for r in items:
        color = (0, 200, 100) if r.get("category") else (160, 160, 160)
        pts = np.array(r["box"], dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(vis, [pts], True, color, 2)
        if r.get("category"):
            tx, ty = int(r["box"][0][0]), int(r["box"][0][1]) - 4
            cv2.putText(vis, r["category"], (tx, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return vis
