# -*- coding: utf-8 -*-
"""压力表实时监控窗口（工业版）— 持续检测 + 大字读数 + 自动重连。"""

import os
import gc
import datetime
import threading

import cv2
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QDialog, QFormLayout, QSpinBox, QDoubleSpinBox,
    QCheckBox, QDialogButtonBox, QStatusBar,
)
from PySide6.QtGui import QPixmap, QImage, QFont, QPainter, QColor, QPen, QBrush
from PySide6.QtCore import Qt, QTimer

from camera_worker import CameraWorker
from pressure_reader._visualization import draw_auto_result
from pressure_reader._io import cv_imwrite


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")


# =============================================================================
#                         设置对话框
# =============================================================================
class SettingsDialog(QDialog):
    """摄像头和检测参数设置。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("监控设置")
        self.setMinimumWidth(350)

        layout = QFormLayout(self)

        self.cam_index = QSpinBox()
        self.cam_index.setRange(0, 9)
        self.cam_index.setValue(parent._camera_index if parent else 0)
        layout.addRow("摄像头索引:", self.cam_index)

        self.detect_interval = QDoubleSpinBox()
        self.detect_interval.setRange(0.5, 60.0)
        self.detect_interval.setSingleStep(0.5)
        self.detect_interval.setValue(
            parent._detect_interval if parent else 2.0
        )
        self.detect_interval.setSuffix(" 秒")
        layout.addRow("检测间隔:", self.detect_interval)

        self.full_range = QDoubleSpinBox()
        self.full_range.setRange(0.1, 10000.0)
        self.full_range.setDecimals(2)
        self.full_range.setValue(
            parent._full_range if parent else 25.0
        )
        layout.addRow("量程:", self.full_range)

        self.auto_reconnect = QCheckBox()
        self.auto_reconnect.setChecked(True)
        layout.addRow("自动重连:", self.auto_reconnect)

        self.always_on_top = QCheckBox()
        self.always_on_top.setChecked(True)
        layout.addRow("窗口置顶:", self.always_on_top)

        self.save_screenshots = QCheckBox()
        self.save_screenshots.setChecked(False)
        layout.addRow("保存检测截图:", self.save_screenshots)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)


# =============================================================================
#                         监控主窗口
# =============================================================================
class CameraMonitorWindow(QMainWindow):
    """独立监控窗口：摄像头实时画面 + 持续检测 + 大字读数显示。"""

    def __init__(self, pressure_reader, parent=None):
        super().__init__(parent)
        self._reader = pressure_reader       # 复用主窗口的 PressureReader（含缓存 YOLO）
        self._worker = None
        self._current_frame = None
        self._frame_lock = threading.Lock()
        self._annotated_frame = None
        self._is_busy = False
        self._detect_count = 0
        self._running = False
        self._start_time = None

        # 默认参数
        self._camera_index = 0
        self._detect_interval = 2.0
        self._full_range = 25.0
        self._pressure_unit = "MPa"

        self._detect_timer = QTimer(self)
        self._detect_timer.timeout.connect(self._on_detect_tick)

        self._setup_ui()
        self._setup_styles()

    # ────────── UI 构建 ──────────
    def _setup_ui(self):
        self.setWindowTitle("压力表实时监控")
        self.setMinimumSize(960, 520)
        self.setAttribute(Qt.WA_DeleteOnClose)

        # 顶部工具栏
        toolbar = self.addToolBar("控制")
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar { background: #37474F; spacing: 8px; padding: 4px; }"
        )

        self._start_btn = QPushButton("启动监控")
        self._start_btn.clicked.connect(self.start_monitoring)
        toolbar.addWidget(self._start_btn)

        self._stop_btn = QPushButton("停止监控")
        self._stop_btn.clicked.connect(self.stop_monitoring)
        self._stop_btn.setEnabled(False)
        toolbar.addWidget(self._stop_btn)

        spacer = QWidget()
        spacer.setFixedWidth(20)
        toolbar.addWidget(spacer)

        self._settings_btn = QPushButton("设置")
        self._settings_btn.clicked.connect(self._open_settings)
        toolbar.addWidget(self._settings_btn)

        # 中央区域
        central = QWidget()
        self.setCentralWidget(central)
        hbox = QHBoxLayout(central)
        hbox.setSpacing(16)
        hbox.setContentsMargins(12, 12, 12, 12)

        # ── 左侧：实时画面 ──
        left_frame = QFrame()
        left_frame.setFrameShape(QFrame.StyledPanel)
        left_layout = QVBoxLayout(left_frame)

        self._video_label = QLabel("摄像头未启动")
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setMinimumSize(500, 400)
        self._video_label.setStyleSheet(
            "background-color: #1a1a1a; border: 2px solid #333;"
            " border-radius: 6px; color: #888; font-size: 16px;"
        )
        left_layout.addWidget(self._video_label)
        hbox.addWidget(left_frame, stretch=3)

        # ── 右侧：读数面板 ──
        right_frame = QFrame()
        right_frame.setFrameShape(QFrame.StyledPanel)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setSpacing(12)

        # 读数标题
        title_lbl = QLabel("实时读数")
        title_lbl.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("color: #455A64;")
        right_layout.addWidget(title_lbl)

        # 大字读数
        self._reading_value = QLabel("--")
        self._reading_value.setAlignment(Qt.AlignCenter)
        self._reading_value.setFont(QFont("Consolas", 48, QFont.Bold))
        self._reading_value.setStyleSheet(
            "background-color: #263238; color: #00E676;"
            " border: 3px solid #00E676; border-radius: 12px;"
            " padding: 20px;"
        )
        self._reading_value.setMinimumHeight(100)
        right_layout.addWidget(self._reading_value)

        # 单位
        self._reading_unit = QLabel("MPa")
        self._reading_unit.setAlignment(Qt.AlignCenter)
        self._reading_unit.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        self._reading_unit.setStyleSheet("color: #546E7A;")
        right_layout.addWidget(self._reading_unit)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #B0BEC5;")
        right_layout.addWidget(sep)

        # 详细数据
        info_font = QFont("Microsoft YaHei", 11)
        self._pointer_angle_lbl = QLabel("指针角度: --")
        self._pointer_angle_lbl.setFont(info_font)
        right_layout.addWidget(self._pointer_angle_lbl)

        self._range_angle_lbl = QLabel("量程角度: --")
        self._range_angle_lbl.setFont(info_font)
        right_layout.addWidget(self._range_angle_lbl)

        self._interval_lbl = QLabel("检测间隔: %.1f 秒" % self._detect_interval)
        self._interval_lbl.setFont(info_font)
        right_layout.addWidget(self._interval_lbl)

        self._uptime_lbl = QLabel("运行时间: --")
        self._uptime_lbl.setFont(info_font)
        right_layout.addWidget(self._uptime_lbl)

        right_layout.addStretch()

        # 手动抓拍按钮
        self._snapshot_btn = QPushButton("手动抓拍一次")
        self._snapshot_btn.clicked.connect(self._manual_snapshot)
        self._snapshot_btn.setEnabled(False)
        right_layout.addWidget(self._snapshot_btn)

        hbox.addWidget(right_frame, stretch=2)

        # ── 状态栏 ──
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_indicator = QLabel("● 未启动")
        self._status_indicator.setFont(QFont("Microsoft YaHei", 10))
        self._status_bar.addWidget(self._status_indicator)

        self._cam_status = QLabel("摄像头: --")
        self._cam_status.setFont(QFont("Microsoft YaHei", 10))
        self._status_bar.addWidget(self._cam_status)

        self._fps_label = QLabel("FPS: --")
        self._fps_label.setFont(QFont("Microsoft YaHei", 10))
        self._status_bar.addWidget(self._fps_label)

    def _setup_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #ECEFF1; }
            QPushButton {
                background-color: #546E7A; color: white; border: none;
                padding: 8px 18px; border-radius: 5px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #455A64; }
            QPushButton#startBtn { background-color: #2E7D32; }
            QPushButton#startBtn:hover { background-color: #1B5E20; }
            QPushButton#stopBtn { background-color: #C62828; }
            QPushButton#stopBtn:hover { background-color: #B71C1C; }
            QPushButton#snapshotBtn { background-color: #0277BD; }
            QPushButton#snapshotBtn:hover { background-color: #01579B; }
            QPushButton:disabled { background-color: #BDBDBD; color: #757575; }
            QFrame { background-color: #FAFAFA; border: 1px solid #CFD8DC;
                     border-radius: 8px; }
        """)
        self._start_btn.setObjectName("startBtn")
        self._stop_btn.setObjectName("stopBtn")
        self._snapshot_btn.setObjectName("snapshotBtn")

    # ────────── 公共接口 ──────────
    def set_range(self, full_range, unit="MPa"):
        self._full_range = float(full_range)
        self._pressure_unit = unit
        self._reading_unit.setText(unit)

    # ────────── 监控启停 ──────────
    def start_monitoring(self):
        if self._running:
            return

        self._start_btn.setEnabled(False)
        self._status_indicator.setText("● 正在连接...")
        self._status_indicator.setStyleSheet("color: #FF9800; font-weight: bold;")

        self._worker = CameraWorker(self._camera_index)
        self._worker.frame_ready.connect(self._on_frame_received)
        self._worker.preview_ready.connect(self._on_preview_received)
        self._worker.error_occurred.connect(self._on_camera_error)
        self._worker.fps_updated.connect(self._on_fps_updated)
        self._worker.reconnected.connect(self._on_reconnected)
        self._worker.start()

        self._running = True
        self._start_time = datetime.datetime.now()
        self._detect_count = 0
        self._stop_btn.setEnabled(True)
        self._snapshot_btn.setEnabled(True)

        # 启动定时检测
        interval_ms = int(self._detect_interval * 1000)
        self._detect_timer.start(interval_ms)

        self._status_indicator.setText("● 运行中")
        self._status_indicator.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self._cam_status.setText("摄像头: 连接中...")

    def stop_monitoring(self):
        self._running = False
        self._detect_timer.stop()

        if self._worker is not None:
            self._worker.stop()
            self._worker = None

        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._snapshot_btn.setEnabled(False)

        self._status_indicator.setText("● 已停止")
        self._status_indicator.setStyleSheet("color: #9E9E9E; font-weight: bold;")
        self._cam_status.setText("摄像头: 已关闭")
        self._fps_label.setText("FPS: --")

    # ────────── Worker 信号槽 ──────────
    def _on_frame_received(self, frame_bgr):
        with self._frame_lock:
            self._current_frame = frame_bgr.copy()

    def _on_preview_received(self, qimg):
        if self._annotated_frame is not None:
            return  # 显示检测标注图，不覆盖
        pm = QPixmap.fromImage(qimg).scaled(
            self._video_label.width(), self._video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._video_label.setPixmap(pm)
        self._video_label.setText("")

    def _on_camera_error(self, msg):
        self._status_indicator.setText("● 摄像头异常")
        self._status_indicator.setStyleSheet("color: #F44336; font-weight: bold;")
        self._cam_status.setText("摄像头: 断连")
        # 标记 annotated_frame 过期
        self._annotated_frame = None

    def _on_reconnected(self):
        self._status_indicator.setText("● 运行中")
        self._status_indicator.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self._cam_status.setText("摄像头: 已重连")
        self._annotated_frame = None

    def _on_fps_updated(self, fps):
        self._fps_label.setText("FPS: %.1f" % fps)
        self._cam_status.setText("摄像头: 已连接")

    # ────────── 检测逻辑 ──────────
    def _on_detect_tick(self):
        if self._is_busy:
            return

        with self._frame_lock:
            frame = self._current_frame.copy() if self._current_frame is not None else None

        if frame is None:
            return

        try:
            self._is_busy = True
            self._run_pipeline_on_frame(frame)
        except RuntimeError:
            pass  # 单帧检测失败不中断监控
        except Exception:
            pass
        finally:
            self._is_busy = False
            self._detect_count += 1
            if self._detect_count % 100 == 0:
                gc.collect()

        # 更新运行时间
        if self._start_time:
            elapsed = datetime.datetime.now() - self._start_time
            h = int(elapsed.total_seconds() // 3600)
            m = int((elapsed.total_seconds() % 3600) // 60)
            s = int(elapsed.total_seconds() % 60)
            self._uptime_lbl.setText("运行时间: %dh %dm %ds" % (h, m, s))

    def _run_pipeline_on_frame(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        max_side = 1024
        if max(h, w) > max_side:
            scale = max_side / max(h, w)
            frame_bgr = cv2.resize(
                frame_bgr, (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )

        result = self._reader.read(frame_bgr, self._full_range, unit=self._pressure_unit)

        g = result.geometry
        circle_ctr = (
            (float(g.circle.center_x), float(g.circle.center_y))
            if g.circle else None
        )
        circle_r = float(g.circle.radius) if g.circle else None

        vis = draw_auto_result(
            frame_bgr, g.zero_point, g.end_point, g.center_point,
            g.pointer_tip, circle_ctr, circle_r,
        )
        self._annotated_frame = vis

        # 更新视频显示
        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        pm = QPixmap.fromImage(qimg).scaled(
            self._video_label.width(), self._video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._video_label.setPixmap(pm)
        self._video_label.setText("")

        # 更新读数
        self._reading_value.setText(str(result.reading))
        self._reading_unit.setText(result.unit)
        self._pointer_angle_lbl.setText(
            "指针角度: %.1f°" % result.pointer_angle
        )
        self._range_angle_lbl.setText(
            "量程角度: %.1f°" % result.range_angle
        )

        # 保存截图（可选）
        if hasattr(self, '_save_screenshots') and self._save_screenshots:
            self._save_frame()

        # 写入主窗口日志
        self._log_to_parent(result)

    def _manual_snapshot(self):
        with self._frame_lock:
            frame = self._current_frame.copy() if self._current_frame is not None else None
        if frame is None:
            return
        try:
            self._is_busy = True
            self._run_pipeline_on_frame(frame)
        except Exception:
            pass
        finally:
            self._is_busy = False

    # ────────── 保存截图 ──────────
    def _save_frame(self):
        if self._annotated_frame is None:
            return
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(OUTPUT_DIR, "camera_%s.jpg" % ts)
        cv_imwrite(path, self._annotated_frame)

    # ────────── 日志 ──────────
    def _log_to_parent(self, result):
        parent = self.parent()
        if parent is None:
            return
        try:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            txt_path = getattr(parent, "txt_path", None)
            if not txt_path:
                return
            with open(txt_path, "a", encoding="utf-8") as f:
                f.write(now + "\n[监控] 量程: %.2f %s\n" % (self._full_range, self._pressure_unit))
                f.write("指针角度: %.1f°\n" % result.pointer_angle)
                f.write("量程角度: %.1f°\n" % result.range_angle)
                f.write("读数: %s %s\n\n" % (str(result.reading), result.unit))
            parent._refresh_log()
        except Exception:
            pass

    # ────────── 设置对话框 ──────────
    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        new_index = dlg.cam_index.value()
        new_interval = dlg.detect_interval.value()
        new_range = dlg.full_range.value()
        always_on_top = dlg.always_on_top.isChecked()
        self._save_screenshots = dlg.save_screenshots.isChecked()

        self._camera_index = new_index
        self._detect_interval = new_interval
        self._full_range = new_range
        self._interval_lbl.setText("检测间隔: %.1f 秒" % new_interval)

        self.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)

        if self._detect_timer.isActive():
            self._detect_timer.setInterval(int(new_interval * 1000))

        # 如果索引变了，重启 worker
        if self._worker is not None:
            self._worker.set_camera_index(new_index)

    # ────────── 窗口关闭 ──────────
    def closeEvent(self, event):
        self.stop_monitoring()
        gc.collect()
        event.accept()
