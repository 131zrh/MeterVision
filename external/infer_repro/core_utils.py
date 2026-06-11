"""
与 GUI 无关的基础几何/统计工具函数。
抽出来是为了让命令行脚本和冒烟测试能复用，而不必 import PyQt5/PySide6。
"""
from math import sqrt
import numpy as np


class Functions:
    @staticmethod
    def GetClockAngle(v1, v2):
        """两个向量的顺时针夹角（0~360 度）。"""
        TheNorm = np.linalg.norm(v1) * np.linalg.norm(v2)
        rho = np.rad2deg(np.arcsin(np.cross(v1, v2) / TheNorm))
        theta = np.rad2deg(np.arccos(np.dot(v1, v2) / TheNorm))
        if rho > 0:
            return theta
        return 360 - theta

    @staticmethod
    def Distances(a, b):
        x1, y1 = a
        x2, y2 = b
        return float(sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2))

    @staticmethod
    def couputeMean(deg):
        """箱线图法剔除异常值后取均值。"""
        mean = np.mean(deg)
        percentile = np.percentile(deg, (25, 50, 75), method='midpoint')
        Q1, _, Q3 = percentile
        IQR = Q3 - Q1
        ulim = Q3 + 2.5 * IQR
        llim = Q1 - 1.5 * IQR
        new_deg = [v for v in deg if llim < v < ulim]
        if not new_deg:
            return float(mean)
        return float(np.mean(new_deg))
