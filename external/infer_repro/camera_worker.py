# -*- coding: utf-8 -*-
"""摄像头采集线程（工业版）— 自动重连、帧率控制、长时间运行稳定性。"""

import time
import gc

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, QMutex


class CameraWorker(QThread):
    """QThread 封装 cv2.VideoCapture，通过信号跨线程传递帧数据。

    特性：
    - 自动重连：连续读帧失败后自动 release → reopen
    - 帧率限制：默认 15fps 预览
    - 长时间稳定性：每 30 分钟自动重启 VideoCapture 释放驱动资源
    """

    frame_ready = Signal(np.ndarray)   # BGR 帧，用于管道检测
    preview_ready = Signal(object)     # QImage，用于 UI 显示
    error_occurred = Signal(str)       # 错误消息
    reconnected = Signal()             # 自动重连成功
    fps_updated = Signal(float)        # 实时 FPS

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self._camera_index = camera_index
        self._running = False
        self._paused = False
        self._restart_needed = False
        self._mutex = QMutex()

    # ────────── 线程安全状态读写 ──────────
    def _lock_state(self):
        self._mutex.lock()

    def _unlock_state(self):
        self._mutex.unlock()

    def set_camera_index(self, index):
        self._lock_state()
        self._camera_index = index
        self._restart_needed = True
        self._unlock_state()

    def stop(self):
        self._lock_state()
        self._running = False
        self._unlock_state()
        if not self.wait(5000):
            self.terminate()
            self.wait()

    def pause(self):
        self._lock_state()
        self._paused = True
        self._unlock_state()

    def resume(self):
        self._lock_state()
        self._paused = False
        self._unlock_state()

    # ────────── 主循环 ──────────
    def run(self):
        self._running = True
        self._consecutive_failures = 0
        self._restart_needed = False
        self._last_health_check = time.time()
        cap = None

        while self._running:
            # 处理重启请求
            self._lock_state()
            should_restart = self._restart_needed
            self._restart_needed = False
            self._unlock_state()

            if should_restart or cap is None:
                if cap is not None:
                    cap.release()
                cap = self._open_camera()
                if cap is None:
                    self.error_occurred.emit("无法打开摄像头 %d，3 秒后重试..." % self._camera_index)
                    for _ in range(30):
                        if not self._running:
                            return
                        time.sleep(0.1)
                    continue
                self._consecutive_failures = 0
                self._last_health_check = time.time()

            # 暂停检查
            self._lock_state()
            paused = self._paused
            self._unlock_state()
            if paused:
                time.sleep(0.03)
                continue

            ret, frame = cap.read()
            if not ret:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 5:
                    self.error_occurred.emit("摄像头断连，尝试重连...")
                    cap.release()
                    cap = None
                continue

            self._consecutive_failures = 0

            # 帧率计算
            now = time.time()
            elapsed = now - getattr(self, '_last_frame_time', now)
            if elapsed > 0:
                self.fps_updated.emit(1.0 / elapsed)
            self._last_frame_time = now

            # 发射原始 BGR 帧（用于管道检测）
            self.frame_ready.emit(frame)

            # 转换并发射 preview QImage
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                from PySide6.QtGui import QImage
                qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
                self.preview_ready.emit(qimg)
            except Exception:
                pass

            # 长时间运行健康检查：每 30 分钟重启 VideoCapture
            if now - self._last_health_check > 1800:
                self._last_health_check = now
                cap.release()
                cap = None
                gc.collect()
                # 循环顶部会自动 reopen

            # 15fps 限速
            time.sleep(0.066)

        if cap is not None:
            cap.release()

    # ────────── 摄像头打开 ──────────
    def _open_camera(self):
        idx = self._camera_index
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            # 回退到默认后端
            cap.release()
            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                cap.release()
                return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 15)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        try:
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        except Exception:
            pass

        self.reconnected.emit()
        return cap
