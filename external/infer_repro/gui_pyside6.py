# -*- coding: utf-8 -*-
"""
PySide6 压力表读数识别 GUI（干净版 + 手动校准 + 中文 OCR）

- 所有路径基于本文件所在目录，开箱即跑
- 支持自动检测（YOLO + OpenCV）
- 支持手动校准（点 3 下：0 刻度、满刻度、指针尖，得精确读数）
- 支持表盘文字识别（RapidOCR-onnxruntime，识别中文 + 数字）
"""

import math
import os
import sys
import gc
import datetime
from math import sqrt
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QTextEdit, QInputDialog, QFrame, QGroupBox, QLineEdit,
    QMessageBox, QDialog,
)
from PySide6.QtGui import (
    QPixmap, QFont, QImage, QPainter, QPen, QDoubleValidator,
)
from PySide6.QtCore import Qt

from core_utils import Functions
from pressure_reader._circle import detect_circle
from pressure_reader._contours import filter_contours
from pressure_reader._refine import refine_tick_point
from pressure_reader._center import scale_line_vote_center, fit_center_from_ticks
from pressure_reader._pointer import fit_pointer_line
from pressure_reader._correction import correct_center
from pressure_reader._models import CircleDetection
from pressure_reader._pipeline import PressureReader
from pressure_reader._ocr import classify_ocr_text, extract_dial_text, detect_range_from_ocr, OCR_FIELDS
from pressure_reader._visualization import draw_auto_result, draw_manual_result, draw_ocr_result
from pressure_reader._config import DEFAULT_CONFIG


BASE_DIR = Path(__file__).resolve().parent
WEIGHT_PATH = BASE_DIR / "weights" / "best.pt"
OUTPUT_DIR = BASE_DIR / "outputs"
RESULT_TXT = BASE_DIR / "Result_pressure_pointer_4yolo_pose.txt"


# Windows 下 cv2.imread/imwrite 不支持非 ASCII 路径，统一用 numpy + cv2.imdecode/imencode
def cv_imread(path):
    """Unicode 安全的 cv2.imread。失败返回 None。"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def cv_imwrite(path, img):
    """Unicode 安全的 cv2.imwrite。失败返回 False。"""
    try:
        ext = os.path.splitext(path)[1] or ".jpg"
        ok, buf = cv2.imencode(ext, img)
        if not ok:
            return False
        buf.tofile(path)
        return True
    except Exception:
        return False


# =============================================================================
#                         手动校准对话框
# =============================================================================
class ManualCalibDialog(QDialog):
    """在大图上依次点击 0 刻度、满刻度、指针尖 3 个点，算出精确读数。"""

    def __init__(self, image_bgr, full_range=25.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("手动校准 - 依次点击 0 刻度、满刻度、指针尖")
        self.image_bgr = image_bgr
        self.full_range = float(full_range)
        self.clicks = []
        self.prompts = [
            "第 1 步：请点击 【0 刻度】 的位置",
            "第 2 步：请点击 【满刻度】 的位置",
            "第 3 步：请点击 【指针尖】 的位置",
        ]
        self.result_value = None
        self.result_theta = 0.0
        self.result_theta2 = 0.0
        self.result_center = (0.0, 0.0)

        # 显示尺寸：限制最大 800x600，便于点击
        h, w = image_bgr.shape[:2]
        max_w, max_h = 800, 600
        scale = min(max_w / w, max_h / h, 1.0)
        self.disp_w = int(w * scale)
        self.disp_h = int(h * scale)
        self.scale = scale  # 原图坐标 = 显示坐标 / scale

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.disp_w, self.disp_h),
                             interpolation=cv2.INTER_AREA)
        qimg = QImage(resized.data, self.disp_w, self.disp_h,
                      3 * self.disp_w, QImage.Format_RGB888).copy()
        self.base_pixmap = QPixmap.fromImage(qimg)

        self.setFixedSize(self.disp_w + 40, self.disp_h + 140)
        layout = QVBoxLayout(self)
        self.prompt_label = QLabel(self.prompts[0])
        self.prompt_label.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        self.prompt_label.setStyleSheet("color: #2196F3; padding: 5px;")
        layout.addWidget(self.prompt_label)

        self.image_label = QLabel()
        self.image_label.setFixedSize(self.disp_w, self.disp_h)
        self.image_label.setPixmap(self.base_pixmap)
        self.image_label.mousePressEvent = self._on_click
        layout.addWidget(self.image_label)

        btn_row = QHBoxLayout()
        self.reset_btn = QPushButton("重新校准")
        self.reset_btn.clicked.connect(self._reset)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def _on_click(self, event):
        if len(self.clicks) >= 3:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        dx, dy = pos.x(), pos.y()
        ox, oy = dx / self.scale, dy / self.scale
        self.clicks.append((ox, oy))
        self._redraw()
        if len(self.clicks) < 3:
            self.prompt_label.setText(self.prompts[len(self.clicks)])
        else:
            self._compute_and_finish()

    def _redraw(self):
        pm = self.base_pixmap.copy()
        painter = QPainter(pm)
        colors = [Qt.green, Qt.blue, Qt.red]
        labels = ["0", "Max", "Tip"]
        for i, (ox, oy) in enumerate(self.clicks):
            dx, dy = ox * self.scale, oy * self.scale
            pen = QPen(colors[i])
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawEllipse(int(dx - 6), int(dy - 6), 12, 12)
            painter.drawText(int(dx + 8), int(dy - 8), labels[i])
        painter.end()
        self.image_label.setPixmap(pm)

    def _reset(self):
        self.clicks = []
        self.image_label.setPixmap(self.base_pixmap)
        self.prompt_label.setText(self.prompts[0])

    def _compute_and_finish(self):
        # 圆心 = 3 个点的外接圆圆心（纯几何，完全由用户点击决定）
        x1, y1 = self.clicks[0]
        x2, y2 = self.clicks[1]
        x3, y3 = self.clicks[2]
        D = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(D) > 1e-6:
            s1 = x1 * x1 + y1 * y1
            s2 = x2 * x2 + y2 * y2
            s3 = x3 * x3 + y3 * y3
            cx = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / D
            cy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / D
        else:
            # 三点共线极端情况：退化为 0-Max 中点
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0

        v_zero = [x1 - cx, y1 - cy]
        v_tip = [x3 - cx, y3 - cy]
        v_max = [x2 - cx, y2 - cy]
        theta = Functions.GetClockAngle(v_zero, v_tip)
        theta2 = Functions.GetClockAngle(v_zero, v_max)
        if theta2 <= 0:
            QMessageBox.warning(self, "错误", "量程角度为 0，请重新校准。")
            self._reset()
            return
        reading = round((self.full_range / theta2) * theta, 2)
        self.result_value = reading
        self.result_theta = round(theta, 2)
        self.result_theta2 = round(theta2, 2)
        self.result_center = (cx, cy)
        self.accept()


# =============================================================================
#                         主窗口
# =============================================================================
class ImageDetection(QWidget):
    def __init__(self):
        super().__init__()
        self.before_imagepath = None
        self.result_string = None
        self.model_path = str(WEIGHT_PATH)
        self.txt_path = str(RESULT_TXT)
        self.outputPath = str(OUTPUT_DIR) + os.sep
        self.image = None
        self.imageName = None
        self.panMask = None
        self.poniterMask = None
        self.numLineMask = None
        self.centerPoint = None
        self.farPoint = None
        self.zeroPoint = None
        self.endPoint = None
        self.r = None
        self.cirleData = None
        self.lineSet = None
        self.pressure_range = 25.0
        self.pressure_unit = "MPa"
        self.image_width = 400
        self.image_height = 300
        # OCR 引擎（懒加载：首次点击「表盘文字识别」时才初始化）
        self.ocr_engine = None
        self.yolo_model = None
        self.last_yolo_boxes = None
        self.last_ocr_results = []
        self.is_busy = False
        self.max_process_side = 1024
        self.max_ocr_side = 960
        self.save_debug_images = False
        self._reader = PressureReader(str(WEIGHT_PATH))

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._setup_styles()
        self._init_ui()

    # -------------------------- UI --------------------------
    def _setup_styles(self):
        self.setStyleSheet("""
            QWidget { background-color: #f5f5f5; font-family: 'Microsoft YaHei', 'Segoe UI'; }
            QLabel { color: #333; padding: 5px; }
            QPushButton { background-color: #4CAF50; color: white; border: none;
                padding: 10px 20px; border-radius: 6px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #45a049; }
            QPushButton#detectButton { background-color: #2196F3; }
            QPushButton#detectButton:hover { background-color: #1976D2; }
            QPushButton#calibButton { background-color: #9C27B0; }
            QPushButton#calibButton:hover { background-color: #7B1FA2; }
            QPushButton#ocrButton { background-color: #009688; }
            QPushButton#ocrButton:hover { background-color: #00796B; }
            QPushButton#autoRangeButton { background-color: #607D8B; }
            QPushButton#autoRangeButton:hover { background-color: #455A64; }
            QPushButton#modifyButton { background-color: #FF9800; }
            QPushButton#modifyButton:hover { background-color: #F57C00; }
            QPushButton#clearButton { background-color: #f44336; }
            QPushButton#clearButton:hover { background-color: #d32f2f; }
            QPushButton#monitorButton { background-color: #00BCD4; }
            QPushButton#monitorButton:hover { background-color: #0097A7; }
            QTextEdit { background-color: white; border: 2px solid #ddd;
                border-radius: 8px; padding: 8px; font-size: 13px; }
            QGroupBox { font-weight: bold; font-size: 15px; margin-top: 10px;
                border: 2px solid #ccc; border-radius: 8px; padding: 10px;
                background-color: rgba(255,255,255,0.8); }
            QGroupBox::title { subcontrol-origin: margin; left: 10px;
                padding: 0 8px; color: #2c3e50; }
            QLineEdit { background-color: white; border: 2px solid #ddd;
                border-radius: 6px; padding: 6px; font-size: 13px; }
            QLineEdit:focus { border-color: #2196F3; }
        """)

    def _init_ui(self):
        self.setWindowTitle("压力表读数智能检测系统")
        self.setGeometry(100, 100, 1300, 820)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("压力表读数检测识别系统")
        title.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "background-color: #87CEEB; color: black; padding: 10px;"
        )
        main_layout.addWidget(title)

        # 内容：左、中、右三列
        content = QHBoxLayout()
        content.setSpacing(20)
        content.addWidget(self._build_left_panel())
        content.addWidget(self._build_mid_panel())
        content.addWidget(self._build_right_panel())
        main_layout.addLayout(content)

        # 状态栏
        self.status_label = QLabel("系统就绪 - 请导入压力表图片")
        self.status_label.setFont(QFont("Microsoft YaHei", 10))
        self.status_label.setStyleSheet(
            "background-color: #ecf0f1; border: 1px solid #bdc3c7;"
            " border-radius: 5px; padding: 8px; color: #2c3e50;"
        )
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

    def _build_left_panel(self):
        group = QGroupBox("图像输入区域")
        layout = QVBoxLayout()

        range_row = QHBoxLayout()
        self.range_input_label = QLabel("压力表量程 (MPa):")
        range_row.addWidget(self.range_input_label)
        self.range_input = QLineEdit("25.0")
        self.range_input.setPlaceholderText("如：25")
        self.range_input.setValidator(QDoubleValidator(0.1, 10000.0, 3))
        range_row.addWidget(self.range_input)
        range_row.addStretch()
        layout.addLayout(range_row)

        self.image_label1 = QLabel("未导入图片")
        self.image_label1.setAlignment(Qt.AlignCenter)
        self.image_label1.setFixedSize(self.image_width, self.image_height)
        self.image_label1.setStyleSheet(
            "background-color: white; border: 3px dashed #bdc3c7;"
            " border-radius: 10px; color: #7f8c8d; font-size: 15px;"
        )
        layout.addWidget(self.image_label1)

        btn_load = QPushButton("导入压力表图片")
        btn_load.setToolTip("只加载图片，不自动执行耗时识别，避免界面卡死")
        btn_load.clicked.connect(self.load_image)
        layout.addWidget(btn_load)

        btn_detect = QPushButton("自动检测读数")
        btn_detect.setObjectName("detectButton")
        btn_detect.clicked.connect(self.read_value)
        btn_detect.setToolTip("按当前量程执行 YOLO + OpenCV 自动读数")
        layout.addWidget(btn_detect)

        btn_range = QPushButton("自动识别量程")
        btn_range.setObjectName("autoRangeButton")
        btn_range.clicked.connect(self.auto_detect_range)
        btn_range.setToolTip("使用 OCR 识别表盘满量程；较耗时，请按需点击")
        layout.addWidget(btn_range)

        btn_ocr = QPushButton("识别表盘文字")
        btn_ocr.setObjectName("ocrButton")
        btn_ocr.clicked.connect(self.recognize_text)
        btn_ocr.setToolTip("识别表盘文字；首次加载 OCR 模型会较慢")
        layout.addWidget(btn_ocr)

        btn_calib = QPushButton("手动校准 (点3下)")
        btn_calib.setObjectName("calibButton")
        btn_calib.clicked.connect(self.manual_calibrate)
        btn_calib.setToolTip("自动检测不准时使用：依次点击 0 刻度、满刻度、指针尖")
        layout.addWidget(btn_calib)

        btn_monitor = QPushButton("启动实时监控")
        btn_monitor.setObjectName("monitorButton")
        btn_monitor.clicked.connect(self.open_monitor)
        btn_monitor.setToolTip("连接外接 USB 摄像头，持续监控压力表实时读数")
        layout.addWidget(btn_monitor)

        layout.addStretch()
        group.setLayout(layout)
        return group

    def _build_mid_panel(self):
        group = QGroupBox("检测结果展示")
        layout = QVBoxLayout()
        self.image_label2 = QLabel("检测后图片")
        self.image_label2.setAlignment(Qt.AlignCenter)
        self.image_label2.setFixedSize(self.image_width, self.image_height)
        self.image_label2.setStyleSheet(
            "background-color: white; border: 3px dashed #bdc3c7;"
            " border-radius: 10px; color: #7f8c8d; font-size: 15px;"
        )
        layout.addWidget(self.image_label2)

        btn_ok = QPushButton("确认读数")
        btn_ok.clicked.connect(self.confirm)
        layout.addWidget(btn_ok)

        btn_mod = QPushButton("修改读数")
        btn_mod.setObjectName("modifyButton")
        btn_mod.clicked.connect(self.modify_reading)
        layout.addWidget(btn_mod)

        layout.addStretch()
        group.setLayout(layout)
        return group

    def _build_right_panel(self):
        group = QGroupBox("检测信息与历史记录")
        layout = QVBoxLayout()

        self.range_label = QLabel(
            "当前量程: {} {}".format(self.pressure_range, self.pressure_unit)
        )
        self.time_label = QLabel("检测时间: 等待检测...")
        self.angle1_label = QLabel("指针角度: --")
        self.angle2_label = QLabel("量程角度: --")
        self.reading_label = QLabel("压力表读数: --")
        for lb in (self.range_label, self.time_label, self.angle1_label,
                   self.angle2_label):
            lb.setFont(QFont("Microsoft YaHei", 12))
        self.reading_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.reading_label.setStyleSheet("color: #e74c3c;")

        frame = QFrame()
        frame.setStyleSheet(
            "background-color: white; border: 2px solid #bdc3c7;"
            " border-radius: 8px; padding: 10px;"
        )
        fl = QVBoxLayout(frame)
        for lb in (self.range_label, self.time_label, self.angle1_label,
                   self.angle2_label, self.reading_label):
            fl.addWidget(lb)

        layout.addWidget(frame)

        # OCR 结果显示区（紧凑，可读）
        layout.addWidget(QLabel("表盘文字识别结果"))
        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setMinimumHeight(130)
        self.ocr_text.setMaximumHeight(170)
        self.ocr_text.setStyleSheet(
            "background-color: #fafafa; border: 2px solid #009688;"
            " border-radius: 8px; padding: 6px; font-size: 12px;"
        )
        self.ocr_text.setPlaceholderText("点「识别表盘文字」按钮触发 OCR")
        layout.addWidget(self.ocr_text)

        layout.addWidget(QLabel("检测历史记录"))
        self.text_edit = QTextEdit()
        self.text_edit.setMinimumHeight(160)
        layout.addWidget(self.text_edit)

        btn_clear = QPushButton("清除历史记录")
        btn_clear.setObjectName("clearButton")
        btn_clear.clicked.connect(self.clear_log)
        layout.addWidget(btn_clear)
        group.setLayout(layout)
        return group

    # -------------------------- 工具 --------------------------
    def _set_status(self, msg, is_err=False):
        if is_err:
            self.status_label.setStyleSheet(
                "background-color: #ffebee; border: 1px solid #ef5350;"
                " border-radius: 5px; padding: 8px; color: #c62828;"
            )
        else:
            self.status_label.setStyleSheet(
                "background-color: #e8f5e8; border: 1px solid #4caf50;"
                " border-radius: 5px; padding: 8px; color: #2e7d32;"
            )
        self.status_label.setText(msg)

    def _get_range(self):
        try:
            rng = float(self.range_input.text().strip() or "25")
            if rng <= 0:
                raise ValueError
            return rng
        except ValueError:
            self._set_status("请输入有效的量程数字", True)
            return None

    def _ensure_yolo_model(self):
        """懒加载并缓存 YOLO 模型，避免每次点击都重新加载权重。"""
        if self.yolo_model is not None:
            return self.yolo_model
        if not WEIGHT_PATH.exists():
            raise FileNotFoundError("找不到权重文件: " + str(WEIGHT_PATH))
        self._set_status("正在加载 YOLO 模型，首次加载会稍慢...")
        QApplication.processEvents()
        self.yolo_model = YOLO(model=self.model_path, task="detect")
        return self.yolo_model

    def _detect_yolo_boxes(self, min_boxes=2):
        """复用同一张图片的 YOLO 检测结果，减少重复推理。"""
        if self.last_yolo_boxes is not None and len(self.last_yolo_boxes) >= min_boxes:
            return self.last_yolo_boxes, None
        model = self._ensure_yolo_model()
        data = None
        used_conf = None
        for conf_try in (0.6, 0.3, 0.15):
            result = model(
                source=self.image,
                conf=conf_try,
                imgsz=640,
                max_det=8,
                device="cpu",
                verbose=False,
            )
            d = result[0].boxes.xyxy.cpu().numpy()
            result = None
            if d.shape[0] >= min_boxes:
                data = d
                used_conf = conf_try
                break
        if data is not None:
            self.last_yolo_boxes = data
        return data, used_conf

    def _resize_for_processing(self, img, max_side=None):
        """限制进入识别流程的图片尺寸，降低内存占用和长时间卡顿风险。"""
        max_side = max_side or self.max_process_side
        h, w = img.shape[:2]
        longest = max(h, w)
        if longest <= max_side:
            return img
        scale = max_side / float(longest)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def _set_busy(self, busy, msg=None):
        self.is_busy = busy
        if msg:
            self._set_status(msg)
        QApplication.processEvents()

    def _cleanup_after_task(self):
        gc.collect()
        QApplication.processEvents()

    # -------------------------- 按钮回调 --------------------------
    def load_image(self):
        if self.is_busy:
            self._set_status("当前任务尚未结束，请稍后再操作", True)
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择压力表图片", "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path:
            return
        self.before_imagepath = path
        original_image = cv_imread(path)
        if original_image is None:
            self._set_status("图片读取失败（路径含中文或文件损坏？）", True)
            return
        original_shape = original_image.shape[:2]
        self.image = self._resize_for_processing(original_image)
        original_image = None
        gc.collect()
        if self.image.shape[:2] != original_shape:
            self._set_status("图片较大，已自动压缩后再处理以避免卡顿。")
        # 如果原始文件名含中文/特殊字符，后续 cv2.imwrite 会出问题——
        # 使用 ASCII safe 的昵称作为外部输出文件名（原始保留在状态栏）
        raw_name = os.path.splitext(os.path.basename(path))[0]
        try:
            raw_name.encode("ascii")
            self.imageName = raw_name
        except UnicodeEncodeError:
            import re as _re, hashlib as _hl
            digest = _hl.md5(path.encode("utf-8")).hexdigest()[:6]
            ascii_part = _re.sub(r"[^A-Za-z0-9_.-]", "", raw_name) or "img"
            self.imageName = ascii_part + "_" + digest
        rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        pm = QPixmap.fromImage(qimg).scaled(
            self.image_width, self.image_height,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self.image_label1.setPixmap(pm)
        self.image_label1.setText("")
        self.image_label2.clear()
        self.image_label2.setText("检测后图片")
        self.cirleData = None
        self.centerPoint = None
        self.farPoint = None
        self.zeroPoint = None
        self.endPoint = None
        self.panMask = None
        self.poniterMask = None
        self.numLineMask = None
        self.new_cntset = []
        self.last_yolo_boxes = None
        self.ocr_text.clear()
        gc.collect()
        QApplication.processEvents()
        self._set_status("图片加载成功。请按需点击「自动检测读数」「自动识别量程」或「识别表盘文字」。")

    def confirm(self):
        with open(self.txt_path, "a", encoding="utf-8") as f:
            f.write("The reading is correct.\n")
        self._refresh_log()
        self._set_status("读数已确认")

    def modify_reading(self):
        dlg = QInputDialog(self)
        dlg.setWindowTitle("修改读数")
        dlg.setLabelText("请输入修正后的读数：")
        dlg.setTextValue(self.result_string or "")
        if dlg.exec():
            val = dlg.textValue()
            with open(self.txt_path, "a", encoding="utf-8") as f:
                f.write("The corrected reading is: " + val + "\n")
            self._refresh_log()
            self._set_status("读数已修正为: " + val)

    def clear_log(self):
        with open(self.txt_path, "w", encoding="utf-8") as f:
            f.write("")
        self.text_edit.setText("")
        self._set_status("历史记录已清除")

    def _refresh_log(self):
        try:
            # 用 errors='replace' 容错读取，避免历史遗留的非 UTF-8 编码让整个流程崩溃
            with open(self.txt_path, "r", encoding="utf-8", errors="replace") as f:
                self.text_edit.setText(f.read())
        except FileNotFoundError:
            self.text_edit.setText("")
        except Exception:
            self.text_edit.setText("")

    # -------------------------- 手动校准 --------------------------
    def manual_calibrate(self):
        if self.is_busy:
            self._set_status("当前任务尚未结束，请稍后再操作", True)
            return
        if self.image is None:
            self._set_status("请先导入图片", True)
            return
        rng = self._get_range()
        if rng is None:
            return
        try:
            self._set_busy(True, "正在手动校准...")
            dlg = ManualCalibDialog(self.image, full_range=rng, parent=self)
            if dlg.exec() != QDialog.Accepted or dlg.result_value is None:
                return
            r1 = dlg.result_value
            t1 = dlg.result_theta
            t2 = dlg.result_theta2
            cx, cy = dlg.result_center
            self.result_string = str(r1)
            self.pressure_range = rng

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            u = self.pressure_unit
            self.range_label.setText("当前量程: " + str(rng) + " " + u)
            self.time_label.setText("检测时间: " + now + " (手动校准)")
            self.angle1_label.setText("指针角度: " + str(t1) + "°")
            self.angle2_label.setText("量程角度: " + str(t2) + "°")
            self.reading_label.setText("压力表读数: " + str(r1) + " " + u + " (手动)")

            with open(self.txt_path, "a", encoding="utf-8") as f:
                f.write(now + "\n[手动校准] 量程: " + str(rng) + " " + u + "\n")
                f.write("指针角度: " + str(t1) + "\n")
                f.write("量程角度: " + str(t2) + "\n")
                f.write("读数: " + str(r1) + " " + u + "\n\n")
            self._refresh_log()

            vis = draw_manual_result(
                self.image, dlg.clicks, (cx, cy),
            )
            out_path = os.path.join(
                self.outputPath, (self.imageName or "manual") + "_manual_view.jpg"
            )
            cv_imwrite(out_path, vis)
            pix = QPixmap(out_path).scaled(
                self.image_width, self.image_height,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self.image_label2.setPixmap(pix)
            self.image_label2.setText("")
            self._set_status("手动读数完成: " + str(r1) + " " + self.pressure_unit)
        finally:
            self._set_busy(False)
            self._cleanup_after_task()

    # -------------------------- 摄像头实时监控 --------------------------
    def open_monitor(self):
        if self.is_busy:
            self._set_status("当前任务尚未结束，请稍后再操作", True)
            return
        from camera_monitor import CameraMonitorWindow
        rng = self._get_range()
        if rng is None:
            rng = 25.0
        self._monitor = CameraMonitorWindow(self._reader, parent=self)
        self._monitor.set_range(rng, self.pressure_unit)
        self._monitor.show()

    # -------------------------- 自动识别量程 --------------------------
    def _apply_range_unit(self, rng, unit):
        """统一更新量程 / 单位到所有 UI 控件。"""
        self.pressure_range = rng
        if unit:
            self.pressure_unit = unit
        # 量程数字保留两位小数写回输入框（如 1.60、0.90）
        rng_text = ("{:.2f}".format(rng))
        self.range_input.setText(rng_text)
        self.range_input_label.setText(
            "压力表量程 ({}):".format(self.pressure_unit)
        )
        self.range_label.setText(
            "当前量程: " + rng_text + " " + self.pressure_unit
        )

    def _auto_detect_range_impl(self):
        """用 YOLO + OCR 识别表盘量程数字 + 单位。
        策略：YOLO 找 End Line 中心 → 取 OCR 中离它最近的数字 → 量程值。
        若 YOLO 失败则退化为「OCR 数字最大值」（注意：可能误把精度等级当量程）。
        """
        if self.image is None:
            self._set_status("请先导入图片", True)
            return
        self._set_status("正在自动识别量程...")
        QApplication.processEvents()

        # 1) YOLO 找 End Line 中心（自适应置信度）
        end_center = None
        try:
            data, _ = self._detect_yolo_boxes(min_boxes=2)
            if data is not None:
                d = data[np.argsort(data[:, 0])]
                box = d[-1]  # 最右 = End Line
                end_center = (
                    float((box[0] + box[2]) / 2.0),
                    float((box[1] + box[3]) / 2.0),
                )
        except Exception:
            pass

        # 2) OCR
        try:
            self._ensure_ocr_engine()
        except ImportError as e:
            self._set_status(str(e), True)
            return
        try:
            roi_img, (ox, oy) = self._crop_dial_roi()
            res, _ = self.ocr_engine(roi_img)
        except Exception as e:
            self._set_status("OCR 失败: " + str(e), True)
            return

        # 将 OCR 原始结果转为统一格式
        ocr_items = []
        for item in (res or []):
            try:
                box, text, conf = item[0], item[1], float(item[2])
            except Exception:
                continue
            if conf < 0.3:
                continue
            box_full = [(float(p[0]) + ox, float(p[1]) + oy) for p in box]
            ocr_items.append({"text": text, "conf": conf, "box": box_full})

        range_det = detect_range_from_ocr(ocr_items, end_center)
        if range_det is None:
            self._set_status("OCR 未识别到任何数字，无法判断量程", True)
            return
        self._apply_range_unit(range_det.range_value, range_det.unit)
        self._set_status(
            "已自动识别量程: " + ("{:.2f}".format(range_det.range_value)) + " " +
            self.pressure_unit + " (方法: " + range_det.method + ")"
        )
        self._cleanup_after_task()

    def auto_detect_range(self):
        if self.is_busy:
            self._set_status("当前任务尚未结束，请稍后再操作", True)
            return
        try:
            self._set_busy(True, "正在自动识别量程...")
            self._auto_detect_range_impl()
        finally:
            self._set_busy(False)
            self._cleanup_after_task()

    # -------------------------- 表盘文字识别 (OCR) --------------------------
    # classify_ocr_text / OCR_FIELDS 已迁移到 pressure_reader._ocr
    def _ensure_ocr_engine(self):
        """懒加载 RapidOCR 引擎；失败抛 ImportError。"""
        if self.ocr_engine is not None:
            return
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:
            raise ImportError(
                "未安装 rapidocr_onnxruntime，请在终端运行：\n"
                "  pip install rapidocr-onnxruntime"
            ) from e
        self.ocr_engine = RapidOCR()

    def _crop_dial_roi(self):
        """优先返回表盘圆区域（带边距）；霍夫圆未跑过或失败时返回整张图。"""
        if self.image is None:
            return None, (0, 0)
        # 若已经跑过自动检测且霍夫圆成功，使用圆形 ROI
        if self.cirleData is not None:
            r_1, cx, cy = self.cirleData
            pad = int(0.1 * r_1)
            h, w = self.image.shape[:2]
            x1 = max(int(cx - r_1 - pad), 0)
            y1 = max(int(cy - r_1 - pad), 0)
            x2 = min(int(cx + r_1 + pad), w)
            y2 = min(int(cy + r_1 + pad), h)
            roi = self.image[y1:y2, x1:x2].copy()
            return self._resize_for_processing(roi, self.max_ocr_side), (x1, y1)
        return self._resize_for_processing(self.image.copy(), self.max_ocr_side), (0, 0)

    def _recognize_text_impl(self):
        if self.image is None:
            self._set_status("请先导入图片", True)
            return
        self._set_status("正在识别表盘文字（首次会加载模型）...")
        QApplication.processEvents()  # 刷新 UI 让用户看到状态
        try:
            self._ensure_ocr_engine()
        except ImportError as e:
            self._set_status(str(e), True)
            return
        try:
            roi_img, (ox, oy) = self._crop_dial_roi()
            res, _elapse = self.ocr_engine(roi_img)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_status("OCR 失败: " + str(e), True)
            return

        ocr_result, all_items = extract_dial_text(
            self.ocr_engine, roi_img, offset_x=ox, offset_y=oy,
        )

        # 转为旧格式 fields dict 以保持兼容
        fields = {
            "仪器名称": None, "品牌商标": None, "生产厂家": None,
            "压力单位": None, "精度等级": None,
        }
        # 从 all_items 回填 fields（与 extract_dial_text 结果一致）
        for rec in all_items:
            cat = rec["category"]
            if cat is not None and cat in fields:
                if fields[cat] is None or rec["conf"] > fields[cat]["conf"]:
                    fields[cat] = rec
        self.last_ocr_results = fields

        # 右侧 OCR 文本框
        ocr_lines = [
            "仪器名称: " + (ocr_result.instrument_name or "—"),
            "品牌商标: " + (ocr_result.brand or "—"),
            "生产厂家: " + (ocr_result.manufacturer or "—"),
            "压力单位: " + (ocr_result.pressure_unit or "—"),
            "精度等级: " + (ocr_result.accuracy_class or "—"),
        ]
        self.ocr_text.setText("\n".join(ocr_lines))

        # 写日志
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.txt_path, "a", encoding="utf-8") as f:
            f.write(now + "\n[OCR] 表盘文字识别:\n")
            for name in OCR_FIELDS:
                v = getattr(ocr_result, {
                    "仪器名称": "instrument_name",
                    "品牌商标": "brand",
                    "生产厂家": "manufacturer",
                    "压力单位": "pressure_unit",
                    "精度等级": "accuracy_class",
                }[name])
                f.write("  " + name + ": " + (str(v) if v else "—") + "\n")
            f.write("\n")
        self._refresh_log()

        # 可视化
        try:
            vis = draw_ocr_result(self.image, all_items)
            out_path = os.path.join(
                self.outputPath,
                (self.imageName or "ocr") + "_ocr_view.jpg"
            )
            cv_imwrite(out_path, vis)
            pix = QPixmap(out_path).scaled(
                self.image_width, self.image_height,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self.image_label2.setPixmap(pix)
            self.image_label2.setText("")
        except Exception:
            pass

        n_hit = sum(1 for v in fields.values() if v is not None)
        self._set_status(
            "OCR 完成，命中 {}/{} 字段".format(n_hit, len(self.OCR_FIELDS))
        )
        self._cleanup_after_task()

    def recognize_text(self):
        if self.is_busy:
            self._set_status("当前任务尚未结束，请稍后再操作", True)
            return
        try:
            self._set_busy(True, "正在识别表盘文字...")
            self._recognize_text_impl()
        finally:
            self._set_busy(False)
            self._cleanup_after_task()

    # -------------------------- 自动检测流程（OpenCV 几何） --------------------------
    def _img_cut_circle(self):
        result = detect_circle(self.image, config=DEFAULT_CONFIG)
        if result is None:
            self.cirleData = None
            self.panMask = self.image.copy()
            return
        self.cirleData = [result.radius, result.center_x, result.center_y]
        self.panMask = result.panel_mask
        if self.save_debug_images:
            cv_imwrite(self.outputPath + self.imageName + "_1_imgCutCircle.jpg",
                       self.panMask)

    def _contours_filter(self):
        if self.cirleData is None:
            self.new_cntset = []
            self.poniterMask = np.zeros(self.image.shape[:2], np.uint8)
            self.r = 0
            return
        circle = CircleDetection(
            radius=self.cirleData[0],
            center_x=self.cirleData[1],
            center_y=self.cirleData[2],
            panel_mask=self.panMask,
        )
        result = filter_contours(self.panMask, circle, config=DEFAULT_CONFIG)
        if result is None:
            self.new_cntset = []
            self.r = 0
            self.poniterMask = np.zeros(self.image.shape[:2], np.uint8)
            return
        self.new_cntset = result.tick_contours
        self.poniterMask = result.pointer_mask
        self.numLineMask = result.tick_mask
        self.r = result.mean_radius
        if self.save_debug_images:
            cv_imwrite(self.outputPath + self.imageName + "_3_poniterMask.jpg",
                       self.poniterMask)

    def _scale_line_vote_center(self):
        cntset = getattr(self, "new_cntset", None)
        return scale_line_vote_center(
            cntset, self.image.shape[:2], config=DEFAULT_CONFIG,
        )

    def _refine_tick_point(self, box_xyxy):
        if self.cirleData is None or self.image is None:
            return None
        circle = CircleDetection(
            radius=self.cirleData[0],
            center_x=self.cirleData[1],
            center_y=self.cirleData[2],
            panel_mask=self.panMask if self.panMask is not None
            else np.zeros(self.image.shape[:2], np.uint8),
        )
        return refine_tick_point(
            self.image, circle, box_xyxy, config=DEFAULT_CONFIG,
        )

    def _fit_center_from_ticks(self):
        cntset = getattr(self, "new_cntset", None)
        circle = None
        if self.cirleData is not None:
            circle = CircleDetection(
                radius=self.cirleData[0],
                center_x=self.cirleData[1],
                center_y=self.cirleData[2],
                panel_mask=self.panMask if self.panMask is not None
                else np.zeros(self.image.shape[:2], np.uint8),
            )
        return fit_center_from_ticks(
            cntset, self.image.shape[:2], circle, config=DEFAULT_CONFIG,
        )

    def _fit_pointer_line(self):
        if self.poniterMask is None or self.r == 0:
            self.farPoint = None
            return
        result = fit_pointer_line(
            self.poniterMask, self.centerPoint, self.r, config=DEFAULT_CONFIG,
        )
        self.farPoint = list(result) if result is not None else None

    def _read_value_impl(self):
        if self.image is None or self.before_imagepath is None:
            self._set_status("请先导入图片", True)
            return
        rng = self._get_range()
        if rng is None:
            return
        try:
            self._set_status("正在自动检测读数...")
            u = self.pressure_unit
            result = self._reader.read(self.image, rng, unit=u)

            # 同步回 self.* 属性（保持向后兼容）
            g = result.geometry
            self.zeroPoint = list(g.zero_point)
            self.endPoint = list(g.end_point)
            self.centerPoint = list(g.center_point)
            self.farPoint = (list(g.pointer_tip) if g.pointer_tip is not None
                             else None)
            if g.circle is not None:
                self.cirleData = [g.circle.radius, g.circle.center_x,
                                  g.circle.center_y]
                self.panMask = g.circle.panel_mask
            else:
                self.cirleData = None
            if g.contours is not None:
                self.new_cntset = g.contours.tick_contours
                self.poniterMask = g.contours.pointer_mask
                self.numLineMask = g.contours.tick_mask
                self.r = g.contours.mean_radius
            self.last_yolo_boxes = None  # 缓存失效，确保下次重新推理

            reading = result.reading
            theta = result.pointer_angle
            theta2 = result.range_angle
            self.result_string = str(reading)
            self.pressure_range = rng

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.range_label.setText("当前量程: " + str(rng) + " " + u)
            self.time_label.setText("检测时间: " + now + " (自动)")
            self.angle1_label.setText("指针角度: " + str(theta) + "°")
            self.angle2_label.setText("量程角度: " + str(theta2) + "°")
            self.reading_label.setText("压力表读数: " + str(reading) + " " + u)
            with open(self.txt_path, "a", encoding="utf-8") as f:
                f.write(now + "\n[自动] 量程: " + str(rng) + " " + u + "\n")
                f.write("指针角度: " + str(theta) + "\n")
                f.write("量程角度: " + str(theta2) + "\n")
                f.write("读数: " + str(reading) + " " + u + "\n\n")
            self._refresh_log()

            # 可视化
            circle_ctr = (float(g.circle.center_x), float(g.circle.center_y)) if g.circle else None
            circle_r = float(g.circle.radius) if g.circle else None
            vis = draw_auto_result(
                self.image, g.zero_point, g.end_point, g.center_point,
                g.pointer_tip, circle_ctr, circle_r,
            )
            out_path = os.path.join(
                self.outputPath, self.imageName + "_result_view.jpg"
            )
            cv_imwrite(out_path, vis)
            pix = QPixmap(out_path).scaled(
                self.image_width, self.image_height,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self.image_label2.setPixmap(pix)
            self.image_label2.setText("")
            self._set_status("自动检测完成: " + str(reading) + " " + u)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_status("检测失败: " + str(e), True)
        finally:
            self._cleanup_after_task()

    def read_value(self):
        if self.is_busy:
            self._set_status("当前任务尚未结束，请稍后再操作", True)
            return
        try:
            self._set_busy(True, "正在自动检测读数...")
            self._read_value_impl()
        finally:
            self._set_busy(False)
            self._cleanup_after_task()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ImageDetection()
    win.show()
    sys.exit(app.exec())
