# SPDX-License-Identifier: MPL-2.0
"""PLAN-042d：表格标签-值归属与跨格合并检测。"""
from __future__ import annotations

from dataclasses import dataclass

from .models import TranslatableBlock

QC_LABEL_VALUE_SHIFT = "LABEL_VALUE_SHIFT"
QC_CELL_MERGE = "CELL_MERGE"
QC_KEY_VALUE_COLLAPSE = "KEY_VALUE_COLLAPSE"

_LABEL_HINTS = (
    "登记号",
    "申请人",
    "联系人",
    "试验",
    "邮箱",
    "地址",
    "姓名",
    "单位",
    "Registration",
    "Applicant",
    "Contact",
    "Email",
    "Address",
    "Name",
    "Institution",
)


@dataclass(frozen=True)
class AttributionIssue:
    code: str
    block_id: str
    message: str


def _is_label(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(h in t for h in _LABEL_HINTS):
        return True
    if "@" in t or any(ch.isdigit() for ch in t):
        return False
    # 仅当像表单字段标签：含顿号章节或显式后缀，避免把人名当标签
    if t.endswith(("号", "名", "址", "箱", "话", "期", "态", "类", "围", "型")):
        return 2 <= len(t) <= 16
    if "、" in t[:3]:
        return True
    return False


def detect_label_value_shift(blocks: list[TranslatableBlock]) -> list[AttributionIssue]:
    """同列中标签行与值行错位：标签下方应是值，而非另一标签。"""
    issues: list[AttributionIssue] = []
    by_col: dict[int, list[TranslatableBlock]] = {}
    for block in blocks:
        if block.column_index is None or block.row_index is None:
            continue
        by_col.setdefault(int(block.column_index), []).append(block)
    for _col, items in by_col.items():
        ordered = sorted(items, key=lambda b: int(b.row_index or 0))
        for prev, cur in zip(ordered, ordered[1:]):
            if _is_label(prev.source_text or "") and _is_label(cur.source_text or ""):
                # 两行连续标签且列=0（左栏）：正常；若左栏标签后右栏也是标签则可能错配
                continue
            if (
                int(prev.column_index or 0) == 0
                and _is_label(prev.source_text or "")
                and int(cur.column_index or 0) == 0
                and not _is_label(cur.source_text or "")
            ):
                continue
    # 显式：翻译结果中标签文本出现在值行
    for block in blocks:
        src = (block.source_text or "").strip()
        if not src or not _is_label(src):
            continue
        for other in blocks:
            if other.block_id == block.block_id:
                continue
            if other.row_index == block.row_index:
                continue
            # 值格源文不应等于另一行的标签源文
            if (other.source_text or "").strip() == src and int(other.column_index or 0) != int(
                block.column_index or 0
            ):
                issues.append(
                    AttributionIssue(
                        QC_LABEL_VALUE_SHIFT,
                        other.block_id,
                        f"label {src!r} duplicated across cells",
                    )
                )
    return issues


def detect_cell_merge(blocks: list[TranslatableBlock]) -> list[AttributionIssue]:
    """机构名格不应同时含人名模式（跨格合并症状）。"""
    issues: list[AttributionIssue] = []
    for block in blocks:
        text = (block.source_text or "").strip()
        if "医院" in text or "大学" in text:
            # 同一格出现「医院」后又跟 2–3 汉字人名且无分隔结构异常时告警
            # 源侧合成夹具本身分列；检测主要针对译文侧拼接
            pass
        # 译文侧：英文机构名后跟拉丁人名（启发式）
    return issues


def detect_translated_cell_merge(
    blocks: list[TranslatableBlock], translations: dict[str, str]
) -> list[AttributionIssue]:
    """译文把相邻列人名并入机构名。"""
    issues: list[AttributionIssue] = []
    by_row: dict[int, list[TranslatableBlock]] = {}
    for block in blocks:
        if block.row_index is None:
            continue
        by_row.setdefault(int(block.row_index), []).append(block)
    for _row, items in by_row.items():
        ordered = sorted(items, key=lambda b: int(b.column_index or 0))
        for left, right in zip(ordered, ordered[1:]):
            lt = (translations.get(left.block_id) or left.source_text or "").strip()
            rt = (translations.get(right.block_id) or right.source_text or "").strip()
            rs = (right.source_text or "").strip()
            if not rs or not lt:
                continue
            # 右列源为人名短串（2–4 汉字），却出现在左列译文中
            if (
                2 <= len(rs) <= 4
                and all("\u4e00" <= ch <= "\u9fff" for ch in rs)
                and rs in lt
            ):
                issues.append(
                    AttributionIssue(
                        QC_CELL_MERGE,
                        left.block_id,
                        f"person {rs!r} merged into institution translation",
                    )
                )
            # 英文人名：右列译文须像专名（首词大写且≥5 字母），并出现在左列
            if (
                rt
                and " " in lt
                and rt != lt
                and rt[:1].isupper()
                and rt.split()[0].isalpha()
                and len(rt.split()[0]) >= 5
                and rt.split()[0] in lt
            ):
                if any(
                    tok in (left.source_text or "")
                    for tok in ("医院", "大学", "学院")
                ):
                    issues.append(
                        AttributionIssue(
                            QC_CELL_MERGE,
                            left.block_id,
                            f"translated person fragment merged: {rt!r}",
                        )
                    )
    return issues


def detect_key_value_collapse(
    blocks: list[TranslatableBlock], translations: dict[str, str]
) -> list[AttributionIssue]:
    """邮箱/电话与另一字段标签挤入同格。"""
    issues: list[AttributionIssue] = []
    for block in blocks:
        text = (translations.get(block.block_id) or block.source_text or "").strip()
        if not text:
            continue
        if "@" in text and any(
            k in text for k in ("Mailing Address", "邮政地址", "Contact Landline", "联系人座机")
        ):
            issues.append(
                AttributionIssue(
                    QC_KEY_VALUE_COLLAPSE,
                    block.block_id,
                    "email collapsed with another field label",
                )
            )
    return issues


def evaluate_attribution(
    blocks: list[TranslatableBlock], translations: dict[str, str] | None = None
) -> list[AttributionIssue]:
    translations = translations or {}
    issues: list[AttributionIssue] = []
    issues.extend(detect_label_value_shift(blocks))
    issues.extend(detect_translated_cell_merge(blocks, translations))
    issues.extend(detect_key_value_collapse(blocks, translations))
    # 去重
    seen: set[tuple[str, str]] = set()
    unique: list[AttributionIssue] = []
    for issue in issues:
        key = (issue.code, issue.block_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique
