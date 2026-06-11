# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Pressure gauge reading recognition system. YOLO detects start/end tick marks, OpenCV extracts dial geometry (circle center, pointer line), and a clockwise-angle formula computes the pressure reading. PySide6 GUI is the primary entry point.

## Commands

```bash
# Main GUI (recommended)
python gui_pyside6.py

# CLI — YOLO visualization only, no pressure reading
python infer_cli.py --source images

# Batch evaluation — runs full pipeline on all images/ and outputs CSV
python batch_eval.py

# Syntax check (single attempt; if interrupted use ReadLints instead)
python -m py_compile gui_pyside6.py
```

## Architecture

```
YOLO (start/end tick boxes) → OpenCV (circle + contour + pointer fitting)
                            → clockwise-angle formula → reading

Manual calibration bypasses YOLO/OpenCV entirely:
  user clicks 3 points → circumcircle center → same angle formula
```

### Entry points

| File | Role |
|------|------|
| `gui_pyside6.py` | Primary GUI: auto-detect, OCR, manual calibration, logging |
| `gui_pyqt5.py` | Legacy GUI: simpler, no OCR, no auto-range, fixed FULL_RANGE=10.0 |
| `infer_cli.py` | CLI: YOLO inference + box visualization only |
| `batch_eval.py` | Headless batch runner: reuses ImageDetection methods via stub object |

### Core pipeline (in `gui_pyside6.py`)

1. **`_detect_yolo_boxes()`** — cached YOLO inference with adaptive confidence `0.6 → 0.3 → 0.15`, params: `imgsz=640, max_det=8, device="cpu"`. Boxes sorted by x-coordinate: leftmost = zero tick, rightmost = end tick.
2. **`_img_cut_circle()`** — `pyrMeanShiftFiltering` → `HoughCircles` → circle mask. Result stored in `self.cirleData = [r, cx, cy]`.
3. **`_contours_filter()`** — Adaptive threshold → contours → filter by distance-to-center and aspect ratio. Produces `self.new_cntset` (tick marks), `self.poniterMask` (pointer), `self.numLineMask`.
4. **Center determination** (priority order): `_fit_center_from_ticks()` least-squares → Hough circle → `_scale_line_vote_center()` → image center fallback.
5. **`_fit_pointer_line()`** — Morphological close → `HoughLinesP` → longest segment → endpoint farthest from center = pointer tip.
6. **Geometric self-consistency correction** — Intersection of chord perpendicular bisector (zero–end) and pointer axis; accepted if offset ≤ 0.3× radius.
7. **Reading formula**: `reading = full_range / θ2 * θ1` where both angles are clockwise from zero-direction using `Functions.GetClockAngle()`.

### Utility module

`core_utils.py` — No Qt dependency. Three static methods:
- `Functions.GetClockAngle(v1, v2)` — clockwise angle 0–360° via cross/dot product
- `Functions.Distances(a, b)` — Euclidean distance
- `Functions.couputeMean(deg)` — IQR outlier removal then mean

### Busy-lock pattern

All heavy operations in `gui_pyside6.py` follow this pattern to prevent concurrent execution:

```python
def operation(self):
    if self.is_busy:
        self._set_status("当前任务尚未结束，请稍后再操作", True)
        return
    try:
        self._set_busy(True, "status message...")
        self._operation_impl()
    finally:
        self._set_busy(False)
        self._cleanup_after_task()  # gc.collect() + QApplication.processEvents()
```

Operations with this pattern: `load_image`, `read_value`, `auto_detect_range`, `recognize_text`, `manual_calibrate`.

### Image processing safeguards

- **`cv_imread`/`cv_imwrite`** — numpy-based Unicode-safe I/O (Windows `cv2.imread` fails on non-ASCII paths)
- **`_resize_for_processing()`** — caps images to `self.max_process_side` (1024px) before processing
- **`_crop_dial_roi()`** — crops to dial circle region for OCR, also capped to `self.max_ocr_side` (960px)
- **YOLO model caching** — `_ensure_yolo_model()` lazy-loads once into `self.yolo_model`
- **YOLO result caching** — `self.last_yolo_boxes` avoids re-inference on same image
- **Debug images gated** — `self.save_debug_images = False` skips intermediate image saves
- **`load_image()`** — reads original, saves shape, resizes for processing, releases original immediately with `gc.collect()`
- **New image load** clears all cached arrays (`panMask`, `poniterMask`, `numLineMask`, `new_cntset`, `cirleData`, center/pointer/zero/end points, `last_yolo_boxes`)

### OCR

`RapidOCR` (rapidocr-onnxruntime), lazy-loaded. Classifies text into 5 fields: instrument name, brand, manufacturer, pressure unit, accuracy class. `_classify_ocr_text()` uses regex rules; order matters (unit → accuracy → manufacturer → instrument → brand).

### Batch evaluation

`batch_eval.py` creates a stub object mimicking `ImageDetection` attributes, then calls the same pipeline methods (`_img_cut_circle`, `_contours_filter`, etc.) as free functions. Outputs `outputs/batch_eval.csv` and `outputs/batch_eval.txt`.
