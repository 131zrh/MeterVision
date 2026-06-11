"""Pointer line fitting from pointer mask."""
import math
from typing import Optional, Tuple

import cv2
import numpy as np

from ._config import ReaderConfig, DEFAULT_CONFIG


def fit_pointer_line(pointer_mask: np.ndarray,
                     center_point: Tuple[float, float],
                     mean_radius: float,
                     config: ReaderConfig = DEFAULT_CONFIG
                     ) -> Optional[Tuple[float, float]]:
    """Fit the longest Hough line segment from pointer mask.

    Returns:
        (far_x, far_y) — the endpoint farthest from center, or None.
    """
    if mean_radius == 0:
        return None

    cx, cy = center_point
    k = config.pointer_morph_ksize
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    img_proc = cv2.morphologyEx(pointer_mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    min_len = int(config.pointer_min_line_fraction * mean_radius)
    lines = cv2.HoughLinesP(
        img_proc, 1, np.pi / 180, config.pointer_hough_threshold,
        minLineLength=max(1, min_len), maxLineGap=2,
    )
    if lines is None:
        return None

    dmax = 0.0
    best_line = None
    for line in lines:
        x1, y1, x2, y2 = line[0]
        d = math.hypot(float(x2) - float(x1), float(y2) - float(y1))
        if d > dmax:
            dmax = d
            best_line = (float(x1), float(y1), float(x2), float(y2))

    if best_line is None:
        return None

    x1, y1, x2, y2 = best_line
    d1 = math.hypot(x1 - cx, y1 - cy)
    d2 = math.hypot(x2 - cx, y2 - cy)
    return (x1, y1) if d1 > d2 else (x2, y2)
