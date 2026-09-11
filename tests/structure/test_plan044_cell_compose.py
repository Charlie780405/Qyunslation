"""PLAN-044a：单元格 span 拼接与软换行合并。"""
from __future__ import annotations

from qyunslation.structure.table_structure import compose_cell_text, join_span_texts


def test_join_cjk_no_space():
    assert join_span_texts(["序", "号"]) == "序号"
    assert join_span_texts(["体", "格检查"]) == "体格检查"
    assert join_span_texts(["2", "周", "一", "次"]) == "2周一次"


def test_join_latin_keeps_space():
    assert join_span_texts(["Registration", "No."]) == "Registration No."


def test_baseline_bucket_fixes_cross_font_order():
    # Calibri "3" slightly above SimSun "、受试者信息" → old y0 sort put comma first.
    items = [
        (100.0, 120.2, 180.0, 132.2, "、受试者信息"),
        (90.0, 118.0, 98.0, 130.0, "3"),
    ]
    assert compose_cell_text(items) == "3、受试者信息"


def test_soft_merge_orphan_char():
    items = [
        (80.0, 100.0, 200.0, 112.0, "方案是否为联合用"),
        (80.0, 112.5, 92.0, 124.5, "药"),
    ]
    assert compose_cell_text(items) == "方案是否为联合用药"


def test_soft_merge_dose_frequency():
    items = [
        (80.0, 100.0, 160.0, 112.0, "2"),
        (162.0, 100.2, 200.0, 112.2, "周一"),
        (80.0, 113.0, 92.0, 125.0, "次"),
    ]
    assert compose_cell_text(items) == "2周一次"
    # 源 span 内嵌空格
    assert compose_cell_text([(80.0, 100.0, 200.0, 112.0, "2 周一"), (80.0, 113.0, 92.0, 125.0, "次")]) == "2周一次"


def test_numbered_start_keeps_break_space():
    items = [
        (80.0, 100.0, 200.0, 112.0, "上一句结束。"),
        (80.0, 120.0, 200.0, 132.0, "3、受试者信息"),
    ]
    assert compose_cell_text(items) == "上一句结束。 3、受试者信息"
