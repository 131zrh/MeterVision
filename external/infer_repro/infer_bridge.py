"""JSON bridge for the C# MeterVision host.

This script wraps the pressure_reader package and prints one JSON object to
stdout so the WPF application can call the Python algorithm as a child process.
"""
import argparse
import json
import math
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = BASE_DIR / "weights" / "best.pt"
DEFAULT_OUTPUT = BASE_DIR / "outputs" / "bridge"


def build_parser():
    parser = argparse.ArgumentParser(description="MeterVision pressure reader bridge")
    parser.add_argument("--image", required=True, help="压力表图片路径")
    parser.add_argument("--range", dest="full_range", type=float, required=True, help="仪表量程")
    parser.add_argument("--unit", default="MPa", help="压力单位")
    parser.add_argument("--target", type=float, required=True, help="给定压力值")
    parser.add_argument("--tolerance", type=float, required=True, help="允许误差")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="YOLO 权重路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="结果图输出目录")
    return parser


def main():
    args = build_parser().parse_args()

    try:
        from pressure_reader import PressureReader
        from pressure_reader._io import cv_imread, cv_imwrite
        from pressure_reader._visualization import draw_auto_result

        image_path = Path(args.image)
        weights_path = Path(args.weights)
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not image_path.exists():
            raise FileNotFoundError(f"找不到图片：{image_path}")

        if not weights_path.exists():
            raise FileNotFoundError(f"找不到模型权重：{weights_path}")

        image = cv_imread(str(image_path))
        if image is None:
            raise RuntimeError(f"图片读取失败：{image_path}")

        reader = PressureReader(str(weights_path))
        result = reader.read(image, full_range=args.full_range, unit=args.unit)
        error = float(result.reading) - float(args.target)
        passed = math.fabs(error) <= math.fabs(args.tolerance)

        circle_center = None
        circle_radius = None
        if result.geometry.circle is not None:
            circle_center = (
                result.geometry.circle.center_x,
                result.geometry.circle.center_y,
            )
            circle_radius = result.geometry.circle.radius

        view = draw_auto_result(
            image,
            result.geometry.zero_point,
            result.geometry.end_point,
            result.geometry.center_point,
            result.geometry.pointer_tip,
            circle_center,
            circle_radius,
        )

        view_path = output_dir / f"{image_path.stem}_metervision_result.jpg"
        cv_imwrite(str(view_path), view)

        payload = {
            "success": True,
            "message": "识别成功",
            "imagePath": str(image_path),
            "resultImagePath": str(view_path),
            "reading": float(result.reading),
            "targetPressure": float(args.target),
            "error": error,
            "tolerance": float(args.tolerance),
            "passed": passed,
            "unit": args.unit,
            "pointerAngle": float(result.pointer_angle),
            "rangeAngle": float(result.range_angle),
        }
    except Exception as exc:
        payload = {
            "success": False,
            "message": str(exc),
            "imagePath": args.image,
            "resultImagePath": "",
            "reading": None,
            "targetPressure": args.target,
            "error": None,
            "tolerance": args.tolerance,
            "passed": False,
            "unit": args.unit,
        }

    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
