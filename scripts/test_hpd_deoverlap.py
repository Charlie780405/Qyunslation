#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-010a：盒去重叠夹具（页 1 实测重叠对）。"""
from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hpd_ocr as h  # noqa: E402


# 页 1 实测重叠对（聚合后）：We also refer 压住 You should provide 等
_PAGE1_OVERLAPS = [
    (67.0, 341.0, 540.0, 444.7, "We also refer to your correspondence dated."),
    (67.0, 421.0, 540.0, 504.8, "You should provide any updates."),
    (67.0, 490.0, 540.0, 560.0, "If you have any questions."),
    (67.0, 540.0, 540.0, 610.0, "Please refer to the enclosure."),
    (67.0, 200.0, 540.0, 290.0, "Please refer to your PIND file for GS301."),
    (67.0, 270.0, 540.0, 350.0, "Our preliminary responses are enclosed."),
]


def _vertically_overlaps(
    a: tuple[float, float, float, float, str],
    b: tuple[float, float, float, float, str],
    *,
    min_v: float = 1.0,
) -> bool:
    if h._x_overlap_ratio(a, b) <= 0.3 and h._x_overlap_ratio(b, a) <= 0.3:
        return False
    oy0 = max(a[1], b[1])
    oy1 = min(a[3], b[3])
    return (oy1 - oy0) > min_v


class TestDeoverlap(unittest.TestCase):
    def test_no_vertical_overlap_after_deoverlap(self):
        boxes, clamped = h._deoverlap_boxes(list(_PAGE1_OVERLAPS))
        self.assertEqual(len(boxes), len(_PAGE1_OVERLAPS))
        self.assertTrue(any(clamped))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                self.assertFalse(
                    _vertically_overlaps(a, b),
                    msg=f"still overlap: {a[4][:20]!r} vs {b[4][:20]!r} "
                    f"y=[{a[1]:.1f},{a[3]:.1f}] vs [{b[1]:.1f},{b[3]:.1f}]",
                )

    def test_min_height_floor(self):
        # 极端重叠：后继 y0 几乎贴着前驱 y0
        boxes = [
            (10.0, 100.0, 200.0, 180.0, "long paragraph that would be crushed"),
            (10.0, 105.0, 200.0, 160.0, "next line almost on top"),
        ]
        with self.assertLogs(level=logging.WARNING) as cm:
            out, clamped = h._deoverlap_boxes(boxes, min_h=10.0, gap=2.0)
        self.assertTrue(any("min_h" in r.getMessage() for r in cm.records))
        self.assertGreaterEqual(out[0][3] - out[0][1], 10.0 - 1e-6)
        self.assertTrue(clamped[0])

    def test_disjoint_columns_untouched(self):
        left = (10.0, 100.0, 100.0, 200.0, "left column")
        right = (300.0, 120.0, 400.0, 180.0, "right column")
        out, clamped = h._deoverlap_boxes([left, right])
        self.assertEqual(out[0][3], 200.0)
        self.assertEqual(out[1][3], 180.0)
        self.assertFalse(any(clamped))


if __name__ == "__main__":
    unittest.main()
