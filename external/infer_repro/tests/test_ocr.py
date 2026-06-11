"""Test OCR classification — pure function, no model needed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pressure_reader._ocr import classify_ocr_text


def test_unit_detection():
    assert classify_ocr_text("MPa") == "压力单位"
    assert classify_ocr_text("kPa") == "压力单位"
    assert classify_ocr_text("psi") == "压力单位"
    assert classify_ocr_text("bar") == "压力单位"


def test_accuracy_class():
    assert classify_ocr_text("1.6级") == "精度等级"
    assert classify_ocr_text("(1.5)") == "精度等级"
    assert classify_ocr_text("0.5") == "精度等级"


def test_manufacturer():
    assert classify_ocr_text("红旗仪表公司") == "生产厂家"
    assert classify_ocr_text("WIKA Ltd") == "生产厂家"


def test_instrument_name():
    assert classify_ocr_text("压力表") == "仪器名称"
    assert classify_ocr_text("PRESSURE GAUGE") == "仪器名称"


def test_brand():
    assert classify_ocr_text("WIKA") == "品牌商标"
    assert classify_ocr_text("YOKOGAWA") == "品牌商标"


def test_integer_ignored():
    """Pure integers should be ignored (tick numbers)."""
    assert classify_ocr_text("60") is None
    assert classify_ocr_text("100") is None


if __name__ == "__main__":
    test_unit_detection()
    test_accuracy_class()
    test_manufacturer()
    test_instrument_name()
    test_brand()
    test_integer_ignored()
    print("All OCR classification tests passed.")
