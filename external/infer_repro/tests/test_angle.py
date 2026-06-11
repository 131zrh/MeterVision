"""Test angle calculation — pure function, no I/O or model needed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pressure_reader._angle import compute_reading


def test_near_zero():
    """Pointer slightly clockwise from zero → reading near 0."""
    center = (0.0, 0.0)
    zero = (0.0, -100.0)
    end = (100.0, 0.0)
    # barely clockwise from zero
    tip = (2.0, -99.0)
    theta, theta2, reading = compute_reading(zero, end, center, tip, 10.0)
    assert reading < 1.0, f"Expected near-zero, got {reading}"


def test_near_full_scale():
    """Pointer near end tick → reading near full scale."""
    center = (0.0, 0.0)
    zero = (0.0, -100.0)
    end = (100.0, 0.0)
    # just before end in clockwise direction
    tip = (99.0, -2.0)
    theta, theta2, reading = compute_reading(zero, end, center, tip, 10.0)
    assert reading > 8.0, f"Expected near-full, got {reading}"


def test_range_angle_consistency():
    """Range angle should be roughly 90 degrees for zero=(up), end=(right)."""
    center = (0.0, 0.0)
    zero = (0.0, -100.0)
    end = (100.0, 0.0)
    tip = (70.7, -70.7)  # roughly 45 degrees
    theta, theta2, reading = compute_reading(zero, end, center, tip, 10.0)
    assert 80 < theta2 < 100, f"Expected ~90 range angle, got {theta2}"
    assert 30 < theta < 60, f"Expected ~45 pointer angle, got {theta}"
    assert 4.0 < reading < 6.0, f"Expected ~5.0 reading, got {reading}"


if __name__ == "__main__":
    test_near_zero()
    test_near_full_scale()
    test_range_angle_consistency()
    print("All angle tests passed.")
