"""轮廓筛选 — 从表盘图中分离刻度短线和指针候选区域。"""
from typing import List, Optional

import cv2
import numpy as np

from core_utils import Functions

from ._config import ReaderConfig, DEFAULT_CONFIG
from ._models import CircleDetection, ContourResult


def filter_contours(panel_mask: np.ndarray,
                    circle: CircleDetection,
                    config: ReaderConfig = DEFAULT_CONFIG
                    ) -> Optional[ContourResult]:
    """对表盘 mask 图做自适应阈值 + 轮廓筛选。

    Returns:
        ContourResult 若成功提取到刻度线；None 若无可用刻度区域。
    """
    r_1 = circle.radius
    cx, cy = circle.center_x, circle.center_y
    k = config.gaussian_blur_ksize

    img = cv2.GaussianBlur(panel_mask.copy(), (k, k), 0)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        ~gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
        config.adaptive_thresh_block, config.adaptive_thresh_c,
    )
    contours, _ = cv2.findContours(
        binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE,
    )

    cntset: List[np.ndarray] = []
    cntareas: List[int] = []
    needlecnt: List[np.ndarray] = []
    loc: List[float] = []

    for cnt in contours:
        (_, (w, h), _) = cv2.minAreaRect(cnt)
        w, h = int(w), int(h)
        if w == 0 or h == 0:
            continue
        a = cv2.minAreaRect(cnt)[0]
        dis = Functions.Distances((cx, cy), a)
        if config.tick_distance_low * r_1 < dis < config.tick_distance_high * r_1:
            if h / w > config.tick_aspect_ratio or w / h > config.tick_aspect_ratio:
                loc.append(dis)
                cntset.append(cnt)
                cntareas.append(w * h)
        else:
            if w > config.pointer_size_fraction * r_1 or h > config.pointer_size_fraction * r_1:
                needlecnt.append(cnt)

    if not cntareas:
        return None

    mean_area = Functions.couputeMean(np.array(cntareas))
    tick_contours = [
        c for i, c in enumerate(cntset)
        if config.tick_area_filter_low * mean_area <= cntareas[i] <= config.tick_area_filter_high * mean_area
    ]
    mean_radius = float(np.mean(loc)) if loc else 0.0

    h_img, w_img = panel_mask.shape[:2]
    pointer_mask = np.zeros((h_img, w_img), np.uint8)
    cv2.drawContours(pointer_mask, needlecnt, -1, 255, -1)
    tick_mask = np.zeros((h_img, w_img), np.uint8)
    cv2.drawContours(tick_mask, tick_contours, -1, 255, -1)

    return ContourResult(
        tick_contours=tick_contours,
        pointer_mask=pointer_mask,
        tick_mask=tick_mask,
        mean_radius=mean_radius,
    )
