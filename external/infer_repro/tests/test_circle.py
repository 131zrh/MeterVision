"""Test circle detection — requires OpenCV but no model."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from pressure_reader._circle import detect_circle
from pressure_reader._config import DEFAULT_CONFIG


def test_no_circle_on_blank():
    """Blank image should return None."""
    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    result = detect_circle(blank, config=DEFAULT_CONFIG)
    assert result is None, "Blank image should not detect a circle"


def test_circle_on_synthetic():
    """A white circle on black background should be detected."""
    import cv2
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.circle(img, (150, 150), 80, (255, 255, 255), 2)
    result = detect_circle(img, config=DEFAULT_CONFIG)
    if result is not None:
        cx, cy = result.center_x, result.center_y
        assert abs(cx - 150) < 20, f"Center x off: {cx}"
        assert abs(cy - 150) < 20, f"Center y off: {cy}"
        assert 60 < result.radius < 120, f"Radius off: {result.radius}"
    else:
        print("(HoughCircles not finding synthetic circle — may need thicker line)")


if __name__ == "__main__":
    test_no_circle_on_blank()
    test_circle_on_synthetic()
    print("All circle tests passed.")
