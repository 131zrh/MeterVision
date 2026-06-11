"""OCR text classification and range detection helpers."""
import re
from typing import List, Optional, Tuple

import numpy as np

from ._config import ReaderConfig, DEFAULT_CONFIG
from ._models import CircleDetection, OcrResult, RangeDetection

OCR_FIELDS = ["仪器名称", "品牌商标", "生产厂家", "压力单位", "精度等级"]


def classify_ocr_text(text: str) -> Optional[str]:
    """Classify OCR text into one of 5 fields; return None if no match.

    Order: unit → accuracy class → manufacturer → instrument name → brand.
    """
    if not text:
        return None
    s = text.strip()
    s_clean = re.sub(r"[®©™\s]+", "", s)
    if not s_clean:
        return None

    # 1) pressure / temperature unit
    unit_pat = re.compile(
        r"(MPa|kPa|hPa|Pa|psi|bar|mbar|kgf/cm[2²]|mmHg|atm"
        r"|°C|℃|°F|℉)",
        re.IGNORECASE,
    )
    if unit_pat.search(s_clean) and len(s_clean) <= 8:
        return "压力单位"

    # 2) accuracy class
    if "级" in s and re.search(r"\d", s):
        return "精度等级"
    m_par = re.search(
        r"[(\(\[\{〔Ⓛ①②③④⑤]\s*(\d+(?:\.\d+)?)\s*[)\)\]\}〕]?", s,
    )
    if m_par:
        try:
            v = float(m_par.group(1))
            if 0.05 <= v <= 4.0:
                return "精度等级"
        except ValueError:
            pass
    m = re.fullmatch(r"\d+(?:\.\d+)?", s_clean)
    if m and "." in s_clean:
        try:
            v = float(s_clean)
            if 0.05 <= v <= 4.0:
                return "精度等级"
        except ValueError:
            pass
    if m:
        return None  # integer → tick number

    # 3) manufacturer
    company_kw = ("公司", "厂", "制造", "集团", "股份", "Co.", "Ltd",
                  "LIMITED", "Manufactur", "MFG", "INSTRUMENT")
    if any(kw.lower() in s.lower() for kw in company_kw) and len(s) >= 4:
        return "生产厂家"

    # 4) instrument name
    instrument_kw = ("压力表", "真空表", "压力真空表", "压力计",
                     "温度表", "温度计", "流量计", "差压表",
                     "PRESSURE", "GAUGE", "THERMO", "MANOMETER")
    for kw in instrument_kw:
        if kw.isascii():
            if kw in s.upper():
                return "仪器名称"
        elif kw in s:
            return "仪器名称"

    # 5) brand
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9\-]{1,15}", s_clean):
        return "品牌商标"
    if re.fullmatch(r"[一-鿿]{1,5}[A-Za-z][A-Za-z0-9]{1,15}", s_clean):
        return "品牌商标"
    if 2 <= len(s_clean) <= 8 and re.fullmatch(r"[一-鿿]+", s_clean):
        return "品牌商标"

    return None


def extract_dial_text(ocr_engine,
                      roi_image: np.ndarray,
                      offset_x: float = 0.0,
                      offset_y: float = 0.0,
                      conf_threshold: float = 0.3,
                      ) -> Tuple[OcrResult, List[dict]]:
    """Run OCR on a dial ROI and classify into 5 fields.

    Returns:
        (OcrResult, all_items) where all_items is a list of dicts with
        keys: text, conf, box, category (for visualization).
    """
    res, _elapse = ocr_engine(roi_image)

    fields = {k: None for k in OCR_FIELDS}
    all_items: List[dict] = []

    if not res:
        return OcrResult(), all_items

    for item in res:
        try:
            box, text, conf = item[0], item[1], float(item[2])
        except Exception:
            continue
        if conf < conf_threshold:
            continue
        box_full = [(float(p[0]) + offset_x, float(p[1]) + offset_y)
                    for p in box]
        cat = classify_ocr_text(text)
        rec = {"text": text, "conf": conf, "box": box_full, "category": cat}
        all_items.append(rec)
        if cat is not None:
            cur = fields[cat]
            if cur is None or conf > cur["conf"]:
                fields[cat] = rec

    return OcrResult(
        instrument_name=fields["仪器名称"]["text"] if fields["仪器名称"] else None,
        brand=fields["品牌商标"]["text"] if fields["品牌商标"] else None,
        manufacturer=fields["生产厂家"]["text"] if fields["生产厂家"] else None,
        pressure_unit=fields["压力单位"]["text"] if fields["压力单位"] else None,
        accuracy_class=fields["精度等级"]["text"] if fields["精度等级"] else None,
    ), all_items


def detect_range_from_ocr(ocr_result_items: List[dict],
                          end_center: Optional[Tuple[float, float]] = None,
                          ) -> Optional[RangeDetection]:
    """Find full-scale range value from OCR candidates.

    Priority: nearest number to end_center (YOLO end tick); fallback = max number.
    """
    candidates = []
    detected_unit = None

    for item in ocr_result_items:
        s = item["text"].strip()

        if detected_unit is None:
            m = re.search(
                r"(MPa|kPa|hPa|Pa|psi|bar|mbar|mmHg|atm"
                r"|°C|℃|°F|℉)",
                s, re.IGNORECASE,
            )
            if m:
                u = m.group(1)
                detected_unit = {"℃": "°C", "℉": "°F"}.get(u, u)

        num_m = re.fullmatch(r"\d+(?:\.\d+)?", s)
        if num_m:
            try:
                v = float(s)
                if v > 0 and "box" in item:
                    bx = sum(p[0] for p in item["box"]) / 4
                    by = sum(p[1] for p in item["box"]) / 4
                    candidates.append((v, (bx, by), s))
            except ValueError:
                pass

    if not candidates:
        return None

    if end_center is not None:
        ex, ey = end_center
        candidates.sort(
            key=lambda c: (c[1][0] - ex) ** 2 + (c[1][1] - ey) ** 2
        )
        return RangeDetection(
            range_value=candidates[0][0],
            unit=detected_unit,
            method="YOLO+OCR",
        )

    return RangeDetection(
        range_value=max(c[0] for c in candidates),
        unit=detected_unit,
        method="OCR最大值",
    )
