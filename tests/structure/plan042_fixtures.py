# SPDX-License-Identifier: MPL-2.0
"""PLAN-042a：监管表单合成夹具（匿名，不入库二进制）。"""
from __future__ import annotations

from pathlib import Path

import pymupdf


def _grid(page, bbox, rows: int, cols: int, cells: list[list[str]], *, fontsize: float = 8.0) -> None:
    x0, y0, x1, y1 = bbox
    rh = (y1 - y0) / rows
    cw = (x1 - x0) / cols
    for r in range(rows):
        for c in range(cols):
            cx0 = x0 + c * cw
            cx1 = cx0 + cw
            cy0 = y0 + r * rh
            cy1 = cy0 + rh
            page.draw_rect(pymupdf.Rect(cx0, cy0, cx1, cy1), color=(0, 0, 0), width=0.4)
            text = cells[r][c] if r < len(cells) and c < len(cells[r]) else ""
            if text:
                page.insert_text((cx0 + 2, cy0 + min(rh - 2, fontsize + 2)), text, fontsize=fontsize)


def short_label_form(path: Path) -> Path:
    """A1/A4：短值格与表头（1–4 汉字）。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=420)
    page.insert_text((72, 40), "临床试验登记表", fontsize=12)
    _grid(
        page,
        (72, 60, 523, 200),
        5,
        2,
        [
            ["登记号", "CTR00000000"],
            ["试验状态", "进行中"],
            ["试验分类", "生物制品"],
            ["是否为联合用药", "否"],
            ["盲法", "双盲"],
        ],
    )
    doc.save(path)
    doc.close()
    return path


def long_list_form(path: Path) -> Path:
    """A2：长排除标准列表。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 40), "排除标准", fontsize=11)
    rows = [[f"{i}. 合并活动性感染或实验室异常项{i}", ""] for i in range(1, 9)]
    _grid(page, (72, 60, 523, 400), len(rows), 2, rows, fontsize=7)
    doc.save(path)
    doc.close()
    return path


def key_value_form(path: Path) -> Path:
    """B6/C2：标签-值键值对表。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=420)
    _grid(
        page,
        (72, 60, 523, 220),
        4,
        2,
        [
            ["登记号", "CTR00000000"],
            ["申请人", "示例药业股份有限公司"],
            ["联系人邮箱", "contact@example.com"],
            ["联系人座机", "021-80000000"],
        ],
    )
    doc.save(path)
    doc.close()
    return path


def institution_form(path: Path) -> Path:
    """C1/D2：多行机构名与研究者分列。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=420)
    _grid(
        page,
        (72, 60, 523, 200),
        3,
        3,
        [
            ["序号", "机构名称", "主要研究者"],
            ["1", "首都医科大学附属北京同仁医院", "张三"],
            ["2", "北京医院", "李四"],
        ],
        fontsize=7,
    )
    doc.save(path)
    doc.close()
    return path


def word_break_pressure_text() -> list[str]:
    """B2/B3：断词压力短语（用于排版断言，非 PDF）。"""
    return [
        "immunogenicity score",
        "primary endpoint indicator",
        "Monoclonal antibody",
        "Endpoints evaluation",
        "physical examination",
        "Monitoring Committee",
        "Insurance coverage",
    ]


def section_number_samples() -> list[tuple[str, str]]:
    """E1：章节序号确定性映射。"""
    return [
        ("一、题目和背景信息", "I. Title and Background Information"),
        ("二、申请人信息", "II. Applicant Information"),
        ("三、临床试验信息", "III. Clinical Trial Information"),
        ("四、研究者信息", "IV. Investigator Information"),
        ("五、伦理委员会信息", "V. Ethics Committee Information"),
        ("六、试验状态", "VI. Trial Status"),
        ("七、临床试验结果摘要", "VII. Summary of Clinical Trial Results"),
    ]
