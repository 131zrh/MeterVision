"""刻度点精修 — 用 YOLO 框内边缘检测 + 线与圆交点精修零/满刻度点。"""
import math
from typing import Optional, Tuple

import cv2
import numpy as np

from ._config import ReaderConfig, DEFAULT_CONFIG
from ._models import CircleDetection


def refine_tick_point(image: np.ndarray,
                      circle: CircleDetection,
                      box_xyxy: np.ndarray,
                      config: ReaderConfig = DEFAULT_CONFIG
                      ) -> Optional[Tuple[float, float]]:
    """在 YOLO 框内做 Canny + HoughLinesP，求线段与表盘圆的交点。

    保守校验：精修点必须在框对角线 0.8 倍范围内，否则退回 None。
    """
    r_circle = circle.radius
    cx_c = circle.center_x
    cy_c = circle.center_y
    h, w = image.shape[:2]

    x1, y1, x2, y2 = [float(v) for v in box_xyxy[:4]]
    box_cx = (x1 + x2) / 2.0
    box_cy = (y1 + y2) / 2.0
    box_diag = math.hypot(x2 - x1, y2 - y1)
    if box_diag < 5:
        return None

    bw, bh = x2 - x1, y2 - y1
    margin_x = max(10, int(config.refine_margin_fraction * bw))
    margin_y = max(10, int(config.refine_margin_fraction * bh))
    crop_x1 = max(0, int(x1) - margin_x)
    crop_y1 = max(0, int(y1) - margin_y)
    crop_x2 = min(w, int(x2) + margin_x)
    crop_y2 = min(h, int(y2) + margin_y)
    if crop_x2 - crop_x1 < 5 or crop_y2 - crop_y1 < 5:
        return None

    crop = image[crop_y1:crop_y2, crop_x1:crop_x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, config.refine_canny_low, config.refine_canny_high)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, config.refine_hough_threshold,
        minLineLength=config.refine_min_line_len,
        maxLineGap=config.refine_max_line_gap,
    )
    if lines is None or len(lines) == 0:
        return None

    candidates = []
    for line in lines:
        lx1, ly1, lx2, ly2 = line[0]
        gx1 = float(lx1 + crop_x1)
        gy1 = float(ly1 + crop_y1)
        gx2 = float(lx2 + crop_x1)
        gy2 = float(ly2 + crop_y1)
        length = math.hypot(gx2 - gx1, gy2 - gy1)
        if length < config.refine_min_length:
            continue
        mx = (gx1 + gx2) / 2.0
        my = (gy1 + gy2) / 2.0
        radial_dx = cx_c - mx
        radial_dy = cy_c - my
        radial_len = math.hypot(radial_dx, radial_dy)
        if radial_len < 1e-6:
            continue
        cos_angle = abs(
            ((gx2 - gx1) * radial_dx + (gy2 - gy1) * radial_dy)
            / (length * radial_len)
        )
        if cos_angle < config.refine_radial_cos:
            continue
        candidates.append((length, gx1, gy1, gx2, gy2))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)

    best_pt = None
    best_dist = float("inf")
    for cand in candidates[:3]:
        gx1, gy1, gx2, gy2 = cand[1], cand[2], cand[3], cand[4]
        dx = gx2 - gx1
        dy = gy2 - gy1
        A = dx * dx + dy * dy
        if A < 1e-6:
            continue
        B = 2.0 * (dx * (gx1 - cx_c) + dy * (gy1 - cy_c))
        C_ = (gx1 - cx_c) ** 2 + (gy1 - cy_c) ** 2 - r_circle * r_circle
        disc = B * B - 4.0 * A * C_
        if disc < 0:
            continue
        sqrt_disc = math.sqrt(disc)
        for t in ((-B + sqrt_disc) / (2.0 * A), (-B - sqrt_disc) / (2.0 * A)):
            ix = gx1 + t * dx
            iy = gy1 + t * dy
            d = math.hypot(ix - box_cx, iy - box_cy)
            if d < best_dist:
                best_dist = d
                best_pt = (float(ix), float(iy))

    if best_pt is None:
        return None
    if best_dist > config.refine_box_diag_ratio * box_diag:
        return None
    return best_pt
