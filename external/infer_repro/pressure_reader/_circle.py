"""霍夫圆检测 — 从压力表图片中定位表盘圆。"""
from typing import Optional

import cv2
import numpy as np

from ._config import ReaderConfig, DEFAULT_CONFIG
from ._models import CircleDetection


def detect_circle(image: np.ndarray,
                  config: ReaderConfig = DEFAULT_CONFIG
                  ) -> Optional[CircleDetection]:
    """在 BGR 图片上检测表盘圆。

    Returns:
        CircleDetection 若成功；None 若霍夫圆检测不到。
    """
    dst = cv2.pyrMeanShiftFiltering(
        image, config.mean_shift_sp, config.mean_shift_sr,
    )
    gray = cv2.cvtColor(dst, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT,
        config.hough_dp, config.hough_min_dist,
        param1=config.hough_param1, param2=config.hough_param2,
        minRadius=config.hough_min_radius, maxRadius=config.hough_max_radius,
    )
    if circles is None:
        return None
    c = np.uint16(np.around(circles))[0, 0]
    r_1, cx, cy = int(c[2]), int(c[0]), int(c[1])
    mask = np.ones(image.shape, dtype="uint8") * 255
    cv2.circle(mask, (cx, cy), r_1, 0, -1)
    panel_mask = cv2.bitwise_or(image, mask)
    return CircleDetection(
        radius=float(r_1), center_x=float(cx), center_y=float(cy),
        panel_mask=panel_mask,
    )
