"""Windows 中文路径安全的图像读写。"""
import os

import numpy as np
import cv2


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
