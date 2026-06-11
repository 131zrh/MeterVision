"""圆心估计 — 最小二乘 + 刻度线投票两种策略。"""
import math
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ._config import ReaderConfig, DEFAULT_CONFIG
from ._models import CircleDetection


def scale_line_vote_center(tick_contours: List[np.ndarray],
                           image_shape: Tuple[int, int],
                           config: ReaderConfig = DEFAULT_CONFIG
                           ) -> Optional[Tuple[float, float]]:
    """霍夫圆失败时的 fallback：用刻度短线的 fitLine 两两交点投票出圆心。

    Returns:
        (cx, cy) 或 None。
    """
    if not tick_contours or len(tick_contours) < config.vote_center_min_ticks:
        return None

    h, w = image_shape
    line_set = []
    for cnt in tick_contours:
        out = cv2.fitLine(cnt, 2, 0, 0.001, 0.001)
        vx, vy, x0, y0 = float(out[0]), float(out[1]), float(out[2]), float(out[3])
        if abs(vx) < 1e-6:
            vx = 1e-6
        k = vy / vx
        b = y0 - k * x0
        line_set.append((k, b))

    xs, ys = [], []
    n = len(line_set)
    half = n // 2
    group1 = line_set[:half]
    group2 = line_set[half:2 * half] if half > 0 else []
    if not group1 or not group2:
        group1, group2 = line_set, line_set

    for (k1, b1) in group1:
        for (k2, b2) in group2:
            dk = k1 - k2
            if abs(dk) < 1e-5:
                continue
            x = (b2 - b1) / dk
            y = k1 * x + b1
            if 0 <= x <= w and 0 <= y <= h:
                xs.append(x)
                ys.append(y)

    if len(xs) < 3:
        return None

    xs_arr = np.array(xs)
    ys_arr = np.array(ys)
    qx1, qx3 = np.percentile(xs_arr, [25, 75])
    qy1, qy3 = np.percentile(ys_arr, [25, 75])
    mask = ((xs_arr >= qx1) & (xs_arr <= qx3) &
            (ys_arr >= qy1) & (ys_arr <= qy3))
    if mask.sum() < 2:
        return float(np.mean(xs_arr)), float(np.mean(ys_arr))
    return float(np.mean(xs_arr[mask])), float(np.mean(ys_arr[mask]))


def fit_center_from_ticks(tick_contours: List[np.ndarray],
                          image_shape: Tuple[int, int],
                          circle: Optional[CircleDetection],
                          config: ReaderConfig = DEFAULT_CONFIG
                          ) -> Optional[Tuple[float, float]]:
    """用所有刻度线 fitLine 的最小二乘圆心估计（保守版）。

    包含条件数检查、IQR 离群线过滤、霍夫圆一致性检查。
    """
    if not tick_contours or len(tick_contours) < config.fit_center_min_ticks:
        return None

    h, w = image_shape
    A_rows = []
    b_rows = []
    for cnt in tick_contours:
        if len(cnt) < 2:
            continue
        out = cv2.fitLine(cnt, cv2.DIST_L2, 0, 0.001, 0.001)
        vx = float(out[0])
        vy = float(out[1])
        x0 = float(out[2])
        y0 = float(out[3])
        A_rows.append([vy, -vx])
        b_rows.append(vy * x0 - vx * y0)

    if len(A_rows) < config.fit_center_min_ticks:
        return None

    A = np.array(A_rows, dtype=np.float64)
    b = np.array(b_rows, dtype=np.float64)

    try:
        _, sv, _ = np.linalg.svd(A, full_matrices=False)
        cond = sv[0] / max(sv[-1], 1e-12)
        if cond > config.fit_center_cond_max:
            return None
    except Exception:
        return None

    try:
        sol, residuals, rank, _ = np.linalg.lstsq(A, b, rcond=None)
    except Exception:
        return None

    cx0, cy0 = float(sol[0]), float(sol[1])
    if not (0 <= cx0 <= w and 0 <= cy0 <= h):
        return None

    # IQR 过滤离群线
    res = np.abs(A @ sol - b)
    q1, q3 = np.percentile(res, [25, 75])
    iqr = q3 - q1
    upper = q3 + 1.2 * iqr
    inliers = np.where(res <= upper)[0]
    if len(inliers) >= config.fit_center_min_ticks:
        A_in = A[inliers]
        b_in = b[inliers]
        try:
            sol2, _, _, _ = np.linalg.lstsq(A_in, b_in, rcond=None)
        except Exception:
            sol2 = sol
        cx1, cy1 = float(sol2[0]), float(sol2[1])
        if 0 <= cx1 <= w and 0 <= cy1 <= h:
            cx0, cy0 = cx1, cy1

    # 霍夫圆一致性检查
    if circle is not None:
        r_c = circle.radius
        hx = circle.center_x
        hy = circle.center_y
        if math.hypot(cx0 - hx, cy0 - hy) > config.fit_center_hough_consistency * r_c:
            return None

    return (cx0, cy0)
