"""所有可调参数集中管理。"""
from dataclasses import dataclass


@dataclass
class ReaderConfig:
    """压力表读数流水线的全部可配置参数。

    每个字段对应原 gui_pyside6.py 中一处或多处硬编码魔法数字。
    修改实例属性即可调整行为，无需深入算法代码。
    """

    # ---- YOLO ----
    yolo_conf_thresholds: tuple = (0.6, 0.3, 0.15)
    yolo_imgsz: int = 640
    yolo_max_det: int = 8
    yolo_device: str = "cpu"
    yolo_min_boxes: int = 2

    # ---- 霍夫圆检测 ----
    hough_dp: float = 1.0
    hough_min_dist: int = 80
    hough_param1: float = 100.0
    hough_param2: float = 20.0
    hough_min_radius: int = 80
    hough_max_radius: int = 0
    mean_shift_sp: int = 10
    mean_shift_sr: int = 100

    # ---- 轮廓筛选 ----
    gaussian_blur_ksize: int = 3
    adaptive_thresh_block: int = 15
    adaptive_thresh_c: int = -10
    tick_aspect_ratio: float = 4.0         # h/w 或 w/h > 此值视为短线
    tick_distance_low: float = 0.6         # 距离 > 0.6*r 视为表盘内
    tick_distance_high: float = 1.0        # 距离 < 1.0*r
    tick_area_filter_low: float = 0.8      # 面积在均值 0.8-1.5 倍内保留
    tick_area_filter_high: float = 1.5
    pointer_size_fraction: float = 0.5     # 宽或高 > r/2 视为指针候选

    # ---- 圆心估计 ----
    fit_center_min_ticks: int = 6
    fit_center_cond_max: float = 500.0
    fit_center_hough_consistency: float = 0.2  # 与霍夫圆的偏移容限 (×r)
    vote_center_min_ticks: int = 4
    vote_iqr_inliers: bool = True

    # ---- 刻度点精修 ----
    refine_canny_low: int = 50
    refine_canny_high: int = 150
    refine_hough_threshold: int = 20
    refine_min_line_len: int = 12
    refine_max_line_gap: int = 4
    refine_min_length: float = 8.0
    refine_radial_cos: float = 0.85        # 线段方向与径向的余弦阈值
    refine_box_diag_ratio: float = 0.8
    refine_margin_fraction: float = 0.2

    # ---- 指针拟合 ----
    pointer_morph_ksize: int = 3
    pointer_hough_threshold: int = 100
    pointer_min_line_fraction: float = 0.5  # minLineLength = r * 此值

    # ---- 几何修正 ----
    correction_tolerance: float = 0.3       # 新圆心偏移容限 (×r)

    # ---- 安全网 ----
    safety_dist_max: float = 2.0            # 精修点距圆心 > 2r 时回退
    safety_reading_low: float = -0.5
    safety_reading_high: float = 1.05       # reading > range * 此值视为异常

    # ---- OCR ----
    ocr_conf_threshold: float = 0.3
    ocr_max_side: int = 960
    ocr_roi_pad: float = 0.1               # 表盘圆裁剪边距 (×r)

    # ---- 图像处理 ----
    max_process_side: int = 1024
    save_debug_images: bool = False


DEFAULT_CONFIG = ReaderConfig()
