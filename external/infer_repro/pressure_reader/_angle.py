"""Angle and reading calculation from geometric primitives."""
from typing import Tuple

from core_utils import Functions


def compute_reading(zero_point: Tuple[float, float],
                    end_point: Tuple[float, float],
                    center_point: Tuple[float, float],
                    pointer_tip: Tuple[float, float],
                    full_range: float
                    ) -> Tuple[float, float, float]:
    """Compute clockwise pointer angle, range angle, and reading.

    Returns:
        (pointer_angle, range_angle, reading)
    """
    v1 = [zero_point[0] - center_point[0],
          zero_point[1] - center_point[1]]
    v2 = [pointer_tip[0] - center_point[0],
          pointer_tip[1] - center_point[1]]
    theta = round(Functions.GetClockAngle(v1, v2), 2)

    v4 = [end_point[0] - center_point[0],
          end_point[1] - center_point[1]]
    theta2 = round(Functions.GetClockAngle(v1, v4), 2)

    reading = round((full_range / theta2) * theta, 2)
    return theta, theta2, reading
