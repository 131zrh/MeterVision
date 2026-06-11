"""
命令行推理脚本（最小可用版）

功能：
    - 加载已训练好的 YOLO 检测模型（weights/best.pt）
    - 对指定的单张图片或目录进行推理
    - 将带检测框的结果图保存到 outputs/ 目录

用法：
    python infer_cli.py --source path/to/image.jpg
    python infer_cli.py --source path/to/folder/
    python infer_cli.py --source path/to/image.jpg --weights weights/best.pt --conf 0.6

说明：
    这里只做 YOLO 的“起始刻度 / 结束刻度”目标检测可视化，
    不做角度换算（角度换算在 GUI 脚本里，需要 OpenCV 的一整套几何流程）。
"""

import argparse
import os
from pathlib import Path

from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = BASE_DIR / "weights" / "best.pt"
DEFAULT_OUTPUT = BASE_DIR / "outputs"


def parse_args():
    parser = argparse.ArgumentParser(description="Pressure gauge YOLO inference (CLI)")
    parser.add_argument("--source", required=True, help="图片文件或文件夹路径")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="YOLO 权重路径")
    parser.add_argument("--conf", type=float, default=0.6, help="置信度阈值")
    parser.add_argument("--project", default=str(DEFAULT_OUTPUT), help="结果输出目录")
    parser.add_argument("--name", default="cli_predict", help="本次结果子目录名")
    return parser.parse_args()


def main():
    args = parse_args()

    weights = Path(args.weights)
    if not weights.exists():
        raise FileNotFoundError(f"找不到权重文件: {weights}")

    source = args.source
    if not os.path.exists(source):
        raise FileNotFoundError(f"找不到输入: {source}")

    print(f"[infer_cli] weights = {weights}")
    print(f"[infer_cli] source  = {source}")
    print(f"[infer_cli] output  = {args.project}/{args.name}")

    model = YOLO(model=str(weights), task="detect")
    results = model(
        source=source,
        conf=args.conf,
        save=True,
        project=args.project,
        name=args.name,
        exist_ok=True,
    )

    # 简单打印每张图的检测框
    for r in results:
        boxes = r.boxes
        n = 0 if boxes is None else len(boxes)
        print(f"  - {os.path.basename(r.path)}: {n} boxes, save_dir={r.save_dir}")

    print("[infer_cli] done.")


if __name__ == "__main__":
    main()
