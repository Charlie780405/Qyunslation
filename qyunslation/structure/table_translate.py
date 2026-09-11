# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：按稳定块 ID 翻译表格，并生成单语/双语续页。"""
from __future__ import annotations

from dataclasses import dataclass

from .models import TranslationPolicy, TranslatableBlock
from .protect import missing_protected_tokens, protect_tokens, restore_tokens
from .table_cell_policy import assert_digit_tokens_preserved

CONTINUATION_LABEL = "（续）"


class TableTranslateError(RuntimeError):
    """漏块、漏脚注、截断或溢出。"""


@dataclass
class TableContinuation:
    table_number: int
    title: str
    header_texts: list[str]
    body_rows: list[list[str]]
    is_continuation: bool = False

    def heading(self) -> str:
        if self.is_continuation:
            return f"表 {self.table_number}{CONTINUATION_LABEL}"
        return self.title


@dataclass
class DualContinuationPage:
    left_source_page: int
    right_is_continuation: bool


def _policy_value(block: TranslatableBlock) -> TranslationPolicy:
    policy = block.translation_policy
    if policy is None:
        return TranslationPolicy.TRANSLATE
    if isinstance(policy, TranslationPolicy):
        return policy
    return TranslationPolicy(str(policy))


def translate_table_blocks(
    blocks: list[TranslatableBlock],
    translator,
) -> dict[str, str]:
    payloads = []
    maps: dict[str, dict[str, str]] = {}
    preserved: dict[str, str] = {}
    controlled: dict[str, str] = {}
    try:
        from .regulatory_entities import lookup_controlled, normalize_phase_label

        for block in blocks:
            policy = _policy_value(block)
            if policy is TranslationPolicy.PRESERVE:
                continue
            src = block.source_text or ""
            phase = normalize_phase_label(src)
            if phase != src and phase.startswith("Phase"):
                controlled[block.block_id] = phase
                continue
            hit = lookup_controlled(src)
            if hit is not None:
                controlled[block.block_id] = hit
    except Exception:
        controlled = {}
    for block in blocks:
        policy = _policy_value(block)
        if policy is TranslationPolicy.PRESERVE:
            preserved[block.block_id] = block.source_text
            continue
        if block.block_id in controlled:
            continue
        protected, mapping = protect_tokens(block.source_text)
        maps[block.block_id] = mapping
        payloads.append({"id": block.block_id, "text": protected})
    raw: dict[str, str] = {}
    if payloads:
        raw = translator(payloads)
        if not isinstance(raw, dict):
            raise TableTranslateError("TABLE_LLM_INVALID: expected id→text map")
    missing = [
        block.block_id
        for block in blocks
        if block.block_id not in preserved
        and block.block_id not in controlled
        and block.block_id not in raw
    ]
    if missing:
        raise TableTranslateError(f"TABLE_LLM_INCOMPLETE: missing {missing}")
    footnotes = [b.block_id for b in blocks if str(b.role) in {"table_footnote", "TABLE_FOOTNOTE"}]
    if any(fid not in raw and fid not in preserved and fid not in controlled for fid in footnotes):
        raise TableTranslateError("TABLE_FOOTNOTE_MISSING")
    out = dict(preserved)
    out.update(controlled)
    for block in blocks:
        if block.block_id in preserved:
            text = preserved[block.block_id]
        elif block.block_id in controlled:
            # 受控词表命中：允许目标侧引入品牌数字（如 3SBio），跳过 DIGIT_DRIFT
            out[block.block_id] = controlled[block.block_id]
            continue
        else:
            text = restore_tokens(str(raw[block.block_id]), maps[block.block_id])
            try:
                from .regulatory_entities import rewrite_embedded_phase

                text = rewrite_embedded_phase(text)
            except Exception:
                pass
        if not text.strip():
            if _policy_value(block) is TranslationPolicy.PRESERVE:
                out[block.block_id] = text
                continue
            raise TableTranslateError(f"TABLE_CELL_EMPTY:{block.block_id}")
        if _looks_truncated(block.source_text, text):
            raise TableTranslateError(f"TABLE_TRUNCATED:{block.block_id}")
        try:
            assert_digit_tokens_preserved(
                block.source_text, text, block_id=block.block_id
            )
        except ValueError as exc:
            raise TableTranslateError(str(exc)) from exc
        missing_tokens = missing_protected_tokens(block.source_text, text)
        if missing_tokens:
            raise TableTranslateError(
                f"TABLE_TOKEN_DRIFT:{block.block_id}:{missing_tokens}"
            )
        out[block.block_id] = text
    return out


def _looks_truncated(source: str, translated: str) -> bool:
    return bool(source.strip()) and translated.endswith("...") and len(translated) < len(source)


def plan_mono_continuations(
    *,
    table_number: int,
    title: str,
    header: list[str],
    rows: list[list[str]],
    rows_per_page: int,
) -> list[TableContinuation]:
    if rows_per_page < 1:
        raise TableTranslateError("TABLE_CONTINUATION_INVALID")
    pages = []
    for index in range(0, max(len(rows), 1), rows_per_page):
        chunk = rows[index : index + rows_per_page]
        pages.append(
            TableContinuation(
                table_number=table_number,
                title=title,
                header_texts=list(header),
                body_rows=chunk,
                is_continuation=index > 0,
            )
        )
    return pages


def plan_dual_continuations(
    source_page: int, continuation_count: int
) -> list[DualContinuationPage]:
    """每个译文续页配对重复原表页，左侧保持原稿。"""
    pages = [DualContinuationPage(left_source_page=source_page, right_is_continuation=False)]
    for _ in range(max(continuation_count, 0)):
        pages.append(
            DualContinuationPage(left_source_page=source_page, right_is_continuation=True)
        )
    return pages


def assert_vector_searchable(pdf_page_text: str, required: list[str]) -> None:
    missing = [item for item in required if item not in (pdf_page_text or "")]
    if missing:
        raise TableTranslateError(f"TABLE_TEXT_NOT_SEARCHABLE:{missing}")
