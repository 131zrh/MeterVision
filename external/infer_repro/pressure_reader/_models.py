"""算法流水线中所有结构化数据容器。"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class CircleDetection:
    """霍夫圆检测结果。"""
    radius: float
    center_x: float
    center_y: float
    panel_mask: np.ndarray  # 圆形 mask 后的表盘图 (panMask)


@dataclass
class ContourResult:
    """轮廓筛选结果。"""
    tick_contours: List[np.ndarray]  # new_cntset — 过滤后的刻度短线轮廓
    pointer_mask: np.ndarray          # poniterMask — 指针候选二值掩码
    tick_mask: np.ndarray             # numLineMask — 刻度线二值掩码
    mean_radius: float                # r — 刻度线到圆心的平均距离


@dataclass
class GeometryResult:
    """单张图片提取的全部几何基元。"""
    zero_point: Tuple[float, float]
    end_point: Tuple[float, float]
    center_point: Tuple[float, float]
    pointer_tip: Optional[Tuple[float, float]]
    circle: Optional[CircleDetection] = None
    contours: Optional[ContourResult] = None


@dataclass
class ReadingResult:
    """流水线最终输出。"""
    geometry: GeometryResult
    pointer_angle: float      # theta — 指针顺时针角度
    range_angle: float        # theta2 — 量程顺时针角度
    reading: float
    unit: str


@dataclass
class OcrResult:
    """结构化 OCR 字段。"""
    instrument_name: Optional[str] = None
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    pressure_unit: Optional[str] = None
    accuracy_class: Optional[str] = None


@dataclass
class RangeDetection:
    """自动量程识别结果。"""
    range_value: float
    unit: Optional[str]
    method: str  # "YOLO+OCR", "OCR最大值" 等
