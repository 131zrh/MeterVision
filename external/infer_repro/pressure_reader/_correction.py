"""Geometric self-consistency center correction."""
from typing import Optional, Tuple

import numpy as np

from ._config import ReaderConfig, DEFAULT_CONFIG
from ._models import CircleDetection


def correct_center(zero_point: Tuple[float, float],
                   end_point: Tuple[float, float],
                   pointer_tip: Tuple[float, float],
                   center_point: Tuple[float, float],
                   circle: Optional[CircleDetection],
                   config: ReaderConfig = DEFAULT_CONFIG
                   ) -> Tuple[float, float]:
    """Intersection of chord perpendicular bisector and pointer axis.

    If the new center is within tolerance of the old one, adopt it.
    Otherwise return the original center unchanged.
    """
    zp = np.array(zero_point, dtype=np.float64)
    ep = np.array(end_point, dtype=np.float64)
    mid = (zp + ep) / 2.0
    chord = ep - zp
    bis_dir = np.array([-chord[1], chord[0]])

    cp_old = np.array(center_point, dtype=np.float64)
    fp = np.array(pointer_tip, dtype=np.float64)
    ptr_dir = fp - cp_old

    M = np.stack([bis_dir, -ptr_dir], axis=1)
    det = M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]
    if abs(det) <= 1e-6:
        return center_point

    sol = np.linalg.solve(M, fp - mid)
    new_c = mid + sol[0] * bis_dir

    if circle is not None:
        if np.linalg.norm(new_c - cp_old) > config.correction_tolerance * circle.radius:
            return center_point

    return (float(new_c[0]), float(new_c[1]))
