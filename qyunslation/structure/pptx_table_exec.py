# SPDX-License-Identifier: MPL-2.0
"""PLAN-037 P1-B：PPTX 表格单元格 translation_policy 执行分流。"""
from __future__ import annotations

import re

from .docx_table_exec import DocxSegmentBatch, merge_docx_translations
from .models import DocumentStructureManifest, TranslationPolicy
from .table_cell_policy import classify_cell_policy

_PPTX_CELL_BLOCK = re.compile(r"^table:slide:(\d+):(\d+):r(\d+)c(\d+)$")


def pptx_table_cell_policy_map(
    manifest: DocumentStructureManifest | None,
) -> dict[tuple[int, int, int, int], TranslationPolicy]:
    if manifest is None:
        return {}
    policies: dict[tuple[int, int, int, int], TranslationPolicy] = {}
    for obj in manifest.objects:
        if obj.type.value != "TABLE":
            continue
        for block in obj.translatable_blocks:
            match = _PPTX_CELL_BLOCK.match(block.block_id or "")
            if not match or block.translation_policy is None:
                continue
            key = tuple(int(part) for part in match.groups())
            policy = block.translation_policy
            if isinstance(policy, TranslationPolicy):
                policies[key] = policy
            else:
                policies[key] = TranslationPolicy(str(policy))
    return policies


def resolve_pptx_table_cell_policy(
    *,
    table_cell_ref: tuple[int, int, int, int] | None,
    source_text: str,
    policies: dict[tuple[int, int, int, int], TranslationPolicy],
) -> TranslationPolicy | None:
    if table_cell_ref is None:
        return None
    policy = policies.get(table_cell_ref)
    if policy is not None:
        return policy
    return classify_cell_policy(source_text)


def partition_pptx_segments(
    originals: list[str],
    elements: list[dict],
    manifest: DocumentStructureManifest | None,
) -> DocxSegmentBatch:
    policies = pptx_table_cell_policy_map(manifest)
    llm_texts: list[str] = []
    llm_to_original: list[int] = []
    token_maps: dict[int, dict[str, str]] = {}
    preserved: set[int] = set()

    for index, (original, info) in enumerate(zip(originals, elements)):
        policy = resolve_pptx_table_cell_policy(
            table_cell_ref=info.get("table_cell_ref"),
            source_text=original,
            policies=policies,
        )
        if policy is TranslationPolicy.PRESERVE:
            preserved.add(index)
            continue
        text = original
        if policy is TranslationPolicy.PROTECT_TOKENS:
            from .protect import protect_tokens

            text, mapping = protect_tokens(original)
            token_maps[index] = mapping
        llm_texts.append(text)
        llm_to_original.append(index)

    return DocxSegmentBatch(
        llm_texts=llm_texts,
        llm_to_original=llm_to_original,
        token_maps=token_maps,
        preserved_indices=frozenset(preserved),
    )
