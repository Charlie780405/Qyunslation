# SPDX-License-Identifier: MPL-2.0
"""PLAN-041d：表格单元格 QC 账本与终态硬门禁（不进入图片 HARD_FAIL）。"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .models import TranslationPolicy
from .protect import missing_protected_tokens, protect_tokens
from .role_fitter import QC_OVERFLOW, FitResult, TABLE_HARD_FAIL, wrap_lines
from .table_translate import TableTranslateError, _policy_value

QC_MISSING_TARGET = "MISSING_TARGET"
QC_SOURCE_RESIDUE = "SOURCE_RESIDUE"

TABLE_TERMINAL_FAIL = TABLE_HARD_FAIL | {
    QC_MISSING_TARGET,
    QC_SOURCE_RESIDUE,
    "LABEL_VALUE_SHIFT",
    "CELL_MERGE",
    "KEY_VALUE_COLLAPSE",
}

# PLAN-043c：字号偏低告警但不阻断写回（OVERFLOW 无续页仍为硬失败）
TABLE_QC_SOFT = frozenset({"FONT_BELOW_TARGET"})

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def has_cjk(text: str | None) -> bool:
    return bool(_CJK_RE.search(text or ""))


def infer_lang(text: str | None) -> str:
    if has_cjk(text):
        return "zh"
    stripped = (text or "").strip()
    if stripped and re.search(r"[A-Za-z]", stripped):
        return "en"
    return "und"


@dataclass
class CellQc:
    block_id: str
    row: int | None
    column: int | None
    policy: str
    source_text: str
    target_text: str
    source_lang: str
    target_lang: str
    protected_tokens: list[str] = field(default_factory=list)
    font_size: float | None = None
    source_font_size: float | None = None
    bold: bool = False
    overflow: bool = False
    wrapped: bool = False
    writeback: str = "ok"
    qc: list[str] = field(default_factory=list)
    status: str = "pass"

    def as_dict(self) -> dict:
        return asdict(self)


def _wrapped(text: str, font_size: float, box_w: float) -> bool:
    width_chars = max(4, int(box_w / max(font_size * 0.5, 1.0)))
    return len(wrap_lines(text or "", width_chars)) > 1


def evaluate_table_qc(
    blocks,
    translations: dict[str, str],
    results: list[FitResult] | None = None,
    *,
    leftover: list[list[str]] | None = None,
) -> tuple[list[CellQc], list[str]]:
    records: list[CellQc] = []
    hard: list[str] = []
    continued = bool(leftover)
    fitted = results or [None] * len(blocks)
    for block, result in zip(blocks, fitted, strict=False):
        policy = _policy_value(block)
        source = block.source_text or ""
        target = translations.get(block.block_id, "")
        if result is not None and result.text is not None:
            target = result.text
        _protected, mapping = protect_tokens(source)
        tokens = list(dict.fromkeys(mapping.values()))
        style = getattr(block, "source_style", None)
        source_size = float(style.font_size) if style and style.font_size else None
        box_w = 80.0
        if block.bbox:
            box_w = max(1.0, float(block.bbox.x1 - block.bbox.x0))
        font_size = result.font_size if result is not None else source_size
        bold = result.bold if result is not None else bool(
            style and style.font_weight not in {None, "regular", "normal"}
        )
        qc = list(result.qc) if result is not None else []
        overflow = bool(result.overflow) if result is not None else QC_OVERFLOW in qc
        writeback = "continuation" if overflow and continued else ("failed" if overflow else "ok")
        if policy is TranslationPolicy.PRESERVE:
            if source.strip() and missing_protected_tokens(source, target or source):
                qc.append("TABLE_TOKEN_DRIFT")
        elif policy is TranslationPolicy.TRANSLATE:
            if not (target or "").strip() and source.strip():
                qc.append(QC_MISSING_TARGET)
            if has_cjk(target):
                qc.append(QC_SOURCE_RESIDUE)
        record = CellQc(
            block_id=block.block_id,
            row=block.row_index,
            column=block.column_index,
            policy=str(policy),
            source_text=source,
            target_text=target,
            source_lang=infer_lang(source),
            target_lang=infer_lang(target),
            protected_tokens=tokens,
            font_size=font_size,
            source_font_size=source_size,
            bold=bold,
            overflow=overflow,
            wrapped=_wrapped(target, font_size or 9.0, box_w),
            writeback=writeback,
            qc=list(dict.fromkeys(qc)),
            status="preserve" if policy is TranslationPolicy.PRESERVE else "pass",
        )
        cell_hard = []
        for code in record.qc:
            if code == QC_OVERFLOW and continued:
                continue
            if code in TABLE_QC_SOFT:
                continue
            if code in TABLE_TERMINAL_FAIL or code == "TABLE_TOKEN_DRIFT":
                cell_hard.append(code)
        if cell_hard:
            record.status = "fail"
            hard.extend(cell_hard)
        records.append(record)
    try:
        from .table_attribution import evaluate_attribution

        for issue in evaluate_attribution(blocks, translations):
            hard.append(issue.code)
            for record in records:
                if record.block_id == issue.block_id:
                    if issue.code not in record.qc:
                        record.qc.append(issue.code)
                    record.status = "fail"
    except Exception:
        pass
    return records, list(dict.fromkeys(hard))


def source_residue_on_page(page, blocks, translations: dict[str, str], *, x_min_frac: float | None) -> list[str]:
    import pymupdf

    from .table_writeback import output_bbox

    codes: list[str] = []
    width = float(page.rect.width)
    for block in blocks:
        if _policy_value(block) is TranslationPolicy.PRESERVE:
            continue
        source = (block.source_text or "").strip()
        if not source or not has_cjk(source) or not block.bbox:
            continue
        target = (translations.get(block.block_id) or "").strip()
        bbox = output_bbox(block.bbox, width, x_min_frac=x_min_frac)
        extracted = page.get_text("text", clip=pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)) or ""
        extracted = extracted.replace("\xa0", " ")
        if source in extracted:
            codes.append(QC_SOURCE_RESIDUE)
            continue
        if has_cjk(extracted) and target and not has_cjk(target):
            codes.append(QC_SOURCE_RESIDUE)
    return list(dict.fromkeys(codes))


def assert_table_qc_clean(_records: list[CellQc], hard: list[str]) -> None:
    terminal = [code for code in hard if code not in TABLE_QC_SOFT]
    if terminal:
        raise TableTranslateError(f"TABLE_QC_HARD:{terminal}")


def source_qc_ledger(manifest) -> list[dict]:
    from .models import ObjectType

    rows: list[dict] = []
    for obj in manifest.objects:
        if obj.type is not ObjectType.TABLE:
            continue
        try:
            page_no = int(str(obj.canvas_id).split(":")[-1])
        except Exception:
            page_no = None
        for block in obj.translatable_blocks or []:
            policy = _policy_value(block)
            source = block.source_text or ""
            _protected, mapping = protect_tokens(source)
            style = getattr(block, "source_style", None)
            rows.append(
                {
                    "page": page_no,
                    "table": obj.semantic_id,
                    "block_id": block.block_id,
                    "row": block.row_index,
                    "column": block.column_index,
                    "policy": str(policy),
                    "empty_source": not bool(source.strip()),
                    "source_lang": infer_lang(source),
                    "protected_tokens": list(dict.fromkeys(mapping.values())),
                    "font_size": float(style.font_size) if style and style.font_size else None,
                    "bold": bool(style and style.font_weight not in {None, "regular", "normal"}),
                    "status": "pending",
                }
            )
    return rows
