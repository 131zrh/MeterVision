# -*- coding: utf-8 -*-
from __future__ import annotations

"""
batch_eval.py — 对 images/ 下所有图跑一遍自动检测流水线。
使用 pressure_reader.PressureReader，无需 GUI。

输出：
    outputs/batch_eval.csv  机读
    outputs/batch_eval.txt  人读
    outputs/<name>_batch_view.jpg  可视化

用法：
    python batch_eval.py
"""

import csv
import datetime
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from pressure_reader import PressureReader, CircleDetection
from pressure_reader._io import cv_imread, cv_imwrite
from pressure_reader._ocr import detect_range_from_ocr
from pressure_reader._visualization import draw_auto_result


BASE_DIR = Path(__file__).resolve().parent
IMG_DIR = BASE_DIR / "images"
OUT_DIR = BASE_DIR / "outputs"
WEIGHT_PATH = BASE_DIR / "weights" / "best.pt"

HEADERS = [
    "image", "yolo_n", "yolo_conf",
    "range", "unit", "method_range",
    "circle_ok", "cx", "cy", "r",
    "pointer_ok", "tip_x", "tip_y",
    "theta_pointer", "theta_range", "reading",
    "elapsed_ms", "error",
]


def _ascii_safe_name(image_path: Path) -> str:
    raw = image_path.stem
    try:
        raw.encode("ascii")
        return raw
    except UnicodeEncodeError:
        digest = hashlib.md5(str(image_path).encode("utf-8")).hexdigest()[:6]
        ascii_part = re.sub(r"[^A-Za-z0-9_.-]", "", raw) or "img"
        return f"{ascii_part}_{digest}"


def _crop_dial_roi_for_ocr(image: np.ndarray,
                           circle: CircleDetection | None,
                           max_side: int = 960
                           ) -> tuple:
    """Crop dial region for OCR, limited to max_side."""
    if circle is not None:
        r_1, cx, cy = circle.radius, circle.center_x, circle.center_y
        pad = int(0.1 * r_1)
        h, w = image.shape[:2]
        x1 = max(int(cx - r_1 - pad), 0)
        y1 = max(int(cy - r_1 - pad), 0)
        x2 = min(int(cx + r_1 + pad), w)
        y2 = min(int(cy + r_1 + pad), h)
        roi = image[y1:y2, x1:x2].copy()
        offset = (x1, y1)
    else:
        roi = image.copy()
        offset = (0, 0)

    h, w = roi.shape[:2]
    longest = max(h, w)
    if longest > max_side:
        scale = max_side / float(longest)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        roi = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return roi, offset


def main():
    OUT_DIR.mkdir(exist_ok=True)
    if not WEIGHT_PATH.exists():
        print(f"找不到权重: {WEIGHT_PATH}", file=sys.stderr)
        sys.exit(1)

    images = sorted([
        p for p in IMG_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
    ])
    print(f"[batch_eval] 共 {len(images)} 张图")

    # 加载模型
    print("[batch_eval] 加载 YOLO + RapidOCR ...")
    from ultralytics import YOLO
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
    reader = PressureReader(str(WEIGHT_PATH))

    rows = []
    for i, p in enumerate(images, 1):
        t0 = time.time()
        print(f"[{i}/{len(images)}] {p.name} ... ", end="", flush=True)
        rec = {h: "" for h in HEADERS}
        rec["image"] = p.name

        try:
            image = cv_imread(str(p))
            if image is None:
                rec["error"] = "图片读取失败"
                rec["elapsed_ms"] = int((time.time() - t0) * 1000)
                rows.append(rec)
                print("READ_FAIL")
                continue

            # 先用 PressureReader 做完整几何检测（包含 YOLO + 圆心 + 指针）
            result = reader.read(image, 25.0, unit="MPa")
            g = result.geometry

            # 填充 CSV 列
            rec["yolo_n"] = 2  # read() 至少需要 2 个框才能成功
            rec["yolo_conf"] = ""
            rec["circle_ok"] = g.circle is not None
            if g.circle is not None:
                rec["cx"] = round(g.circle.center_x, 2)
                rec["cy"] = round(g.circle.center_y, 2)
                rec["r"] = int(g.circle.radius)
            rec["pointer_ok"] = g.pointer_tip is not None
            if g.pointer_tip is not None:
                rec["tip_x"] = round(g.pointer_tip[0], 2)
                rec["tip_y"] = round(g.pointer_tip[1], 2)

            # OCR 量程识别
            roi, (ox, oy) = _crop_dial_roi_for_ocr(image, g.circle)
            res_ocr, _ = ocr_engine(roi)
            ocr_items = []
            for item in (res_ocr or []):
                try:
                    box, text, conf = item[0], item[1], float(item[2])
                except Exception:
                    continue
                if conf < 0.3:
                    continue
                box_full = [(float(p[0]) + ox, float(p[1]) + oy) for p in box]
                ocr_items.append({"text": text, "conf": conf, "box": box_full})

            end_center = g.end_point if g.end_point is not None else None
            range_det = detect_range_from_ocr(ocr_items, end_center)
            if range_det is not None:
                rec["range"] = range_det.range_value
                rec["unit"] = range_det.unit or ""
                rec["method_range"] = range_det.method
                rng = range_det.range_value
                unit = range_det.unit or "MPa"
            else:
                rng = 25.0
                unit = "MPa"

            # 用实际量程重新计算
            theta = result.pointer_angle
            theta2 = result.range_angle
            if theta2 > 0 and rng > 0:
                rec["reading"] = round((rng / theta2) * theta, 3)
            rec["theta_pointer"] = theta
            rec["theta_range"] = theta2

            print("rd={} {} (rng={}, theta={}, theta2={})".format(
                rec["reading"], rec["unit"], rec["range"],
                rec["theta_pointer"], rec["theta_range"],
            ))

            # 可视化
            try:
                circle_ctr = (float(g.circle.center_x), float(g.circle.center_y)) if g.circle else None
                circle_r = float(g.circle.radius) if g.circle else None
                vis = draw_auto_result(
                    image, g.zero_point, g.end_point, g.center_point,
                    g.pointer_tip, circle_ctr, circle_r,
                )
                txt = "rd={} {}({})".format(rec["reading"],
                                            rec["unit"],
                                            rec["method_range"])
                cv2.putText(vis, txt, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                safe_name = _ascii_safe_name(p)
                out_path = OUT_DIR / f"{safe_name}_batch_view.jpg"
                cv_imwrite(str(out_path), vis)
            except Exception:
                pass

        except Exception as e:
            import traceback
            traceback.print_exc()
            rec["error"] = str(e)
            print(f"FAILED: {e}")

        rec["elapsed_ms"] = int((time.time() - t0) * 1000)
        rows.append(rec)

    # CSV
    csv_path = OUT_DIR / "batch_eval.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[batch_eval] CSV: {csv_path}")

    # TXT
    txt_path = OUT_DIR / "batch_eval.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"批量评测 {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"共 {len(rows)} 张\n\n")
        for r in rows:
            f.write(f"== {r['image']} ==\n")
            f.write(f"  YOLO: {r['yolo_n']} 框 (conf={r['yolo_conf']})\n")
            f.write(f"  量程: {r['range']} {r['unit']}  方法: {r['method_range']}\n")
            f.write(f"  圆: ok={r['circle_ok']} center=({r['cx']},{r['cy']}) r={r['r']}\n")
            f.write(f"  指针: ok={r['pointer_ok']} tip=({r['tip_x']},{r['tip_y']})\n")
            f.write(f"  角度: 指针={r['theta_pointer']}  量程={r['theta_range']}\n")
            f.write(f"  读数: {r['reading']} {r['unit']}\n")
            if r["error"]:
                f.write(f"  ERROR: {r['error']}\n")
            f.write(f"  耗时: {r['elapsed_ms']}ms\n\n")
    print(f"[batch_eval] TXT: {txt_path}")

    # 统计
    n = len(rows)
    n_circle = sum(1 for r in rows if r["circle_ok"] is True)
    n_pointer = sum(1 for r in rows if r["pointer_ok"] is True)
    n_reading = sum(1 for r in rows if r["reading"] != "")
    print(
        f"\n[batch_eval] 统计: "
        f"霍夫圆 {n_circle}/{n}, "
        f"指针 {n_pointer}/{n}, "
        f"出读数 {n_reading}/{n}"
    )


if __name__ == "__main__":
    main()
