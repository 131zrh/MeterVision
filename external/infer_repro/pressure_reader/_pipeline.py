"""Pipeline orchestrator — stateless per-inference, holds cached models."""
import math
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from ultralytics import YOLO

from core_utils import Functions

from ._config import ReaderConfig, DEFAULT_CONFIG
from ._models import (
    CircleDetection, ContourResult, GeometryResult, ReadingResult,
)
from ._circle import detect_circle
from ._contours import filter_contours
from ._refine import refine_tick_point
from ._center import scale_line_vote_center, fit_center_from_ticks
from ._pointer import fit_pointer_line
from ._correction import correct_center
from ._angle import compute_reading


class PressureReader:
    """YOLO + OpenCV pressure gauge reading pipeline.

    Holds cached YOLO model and config.  Call .read() per image.
    """

    def __init__(self,
                 model_path: str,
                 config: ReaderConfig = DEFAULT_CONFIG):
        self.model_path = str(model_path)
        self.config = config
        self._yolo: Optional[YOLO] = None

    def _ensure_yolo(self) -> YOLO:
        if self._yolo is not None:
            return self._yolo
        self._yolo = YOLO(model=self.model_path, task="detect")
        return self._yolo

    def _detect_boxes(self, image: np.ndarray,
                      ) -> Tuple[Optional[np.ndarray], Optional[float]]:
        """YOLO detection with adaptive confidence. Returns (boxes_Nx4, conf_used)."""
        model = self._ensure_yolo()
        cfg = self.config
        for conf_try in cfg.yolo_conf_thresholds:
            result = model(
                source=image,
                conf=conf_try,
                imgsz=cfg.yolo_imgsz,
                max_det=cfg.yolo_max_det,
                device=cfg.yolo_device,
                verbose=False,
            )
            d = result[0].boxes.xyxy.cpu().numpy()
            result = None
            if d.shape[0] >= cfg.yolo_min_boxes:
                return d, conf_try
        return None, None

    def read(self, image: np.ndarray, full_range: float,
             unit: str = "MPa") -> ReadingResult:
        """Run full pipeline on one image.

        Raises:
            RuntimeError: if YOLO detects <2 boxes or pointer not found
                or reading is out of safe range.
        """
        cfg = self.config

        # 1) YOLO
        data, used_conf = self._detect_boxes(image)
        if data is None:
            raise RuntimeError(
                "YOLO did not detect >= {} start/end tick boxes".format(
                    cfg.yolo_min_boxes)
            )

        sorted_idx = np.argsort(data[:, 0])
        ds = data[sorted_idx]
        left_box = ds[0][:4]
        right_box = ds[-1][:4]
        x1l, y1l, x2l, y2l = left_box
        x1r, y1r, x2r, y2r = right_box
        zero_point = (float((x1l + x2l) / 2.0),
                      float((y1l + y2l) / 2.0))
        end_point = (float((x1r + x2r) / 2.0),
                     float((y1r + y2r) / 2.0))

        # 2) Circle
        circle = detect_circle(image, config=cfg)

        # 3) Contours
        contours = None
        if circle is not None:
            contours = filter_contours(circle.panel_mask, circle, config=cfg)

        # 4) Refine tick points
        if circle is not None:
            refined_z = refine_tick_point(image, circle, left_box, config=cfg)
            if refined_z is not None:
                zero_point = refined_z
            refined_e = refine_tick_point(image, circle, right_box, config=cfg)
            if refined_e is not None:
                end_point = refined_e

        # 5) Center
        tick_contours = contours.tick_contours if contours is not None else []
        h, w = image.shape[:2]
        ticks_center = fit_center_from_ticks(
            tick_contours, (h, w), circle, config=cfg,
        )
        if ticks_center is not None:
            center_point = (float(ticks_center[0]), float(ticks_center[1]))
        elif circle is not None:
            center_point = (circle.center_x, circle.center_y)
        else:
            vote = scale_line_vote_center(tick_contours, (h, w), config=cfg)
            if vote is not None:
                center_point = (float(vote[0]), float(vote[1]))
            else:
                center_point = (w / 2.0, h / 2.0)

        # 6) Safety: revert refined points if too far from circle center
        if circle is not None:
            d_z = math.hypot(zero_point[0] - circle.center_x,
                             zero_point[1] - circle.center_y)
            d_e = math.hypot(end_point[0] - circle.center_x,
                             end_point[1] - circle.center_y)
            if d_z > cfg.safety_dist_max * circle.radius:
                zero_point = (float((x1l + x2l) / 2.0),
                              float((y1l + y2l) / 2.0))
            if d_e > cfg.safety_dist_max * circle.radius:
                end_point = (float((x1r + x2r) / 2.0),
                             float((y1r + y2r) / 2.0))

        # 7) Pointer
        pointer_mask = contours.pointer_mask if contours is not None else np.zeros((h, w), np.uint8)
        mean_radius = contours.mean_radius if contours is not None else 0.0
        pointer_tip = fit_pointer_line(
            pointer_mask, center_point, mean_radius, config=cfg,
        )
        if pointer_tip is None:
            raise RuntimeError("Failed to detect pointer")

        # 8) Geometric correction
        try:
            center_point = correct_center(
                zero_point, end_point, pointer_tip,
                center_point, circle, config=cfg,
            )
        except Exception:
            pass

        # 9) Angle + reading
        theta, theta2, reading = compute_reading(
            zero_point, end_point, center_point, pointer_tip, full_range,
        )
        if reading < cfg.safety_reading_low or reading > full_range * cfg.safety_reading_high:
            raise RuntimeError(
                "Reading ({:.2f}) out of safe range".format(reading)
            )

        geom = GeometryResult(
            zero_point=zero_point,
            end_point=end_point,
            center_point=center_point,
            pointer_tip=pointer_tip,
            circle=circle,
            contours=contours,
        )
        return ReadingResult(
            geometry=geom,
            pointer_angle=theta,
            range_angle=theta2,
            reading=reading,
            unit=unit,
        )
