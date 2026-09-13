# SPDX-License-Identifier: MPL-2.0
"""PLAN-036：DOCX 表格单元格 translation_policy 执行分流。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import DocumentStructureManifest, TranslationPolicy, DEFERRED_TRANSLATION_POLICIES
from .protect import protect_tokens, restore_tokens
from .table_cell_policy import classify_cell_policy

_CELL_BLOCK = re.compile(r"^cell:(\d+):(\d+):(\d+)$")


def table_cell_policy_map(
    manifest: DocumentStructureManifest | None,
) -> dict[tuple[int, int, int], TranslationPolicy]:
    if manifest is None:
        return {}
    policies: dict[tuple[int, int, int], TranslationPolicy] = {}
    for obj in manifest.objects:
        if obj.type.value != "TABLE":
            continue
        for block in obj.translatable_blocks:
            match = _CELL_BLOCK.match(block.block_id or "")
            if not match or block.translation_policy is None:
                continue
            key = tuple(int(part) for part in match.groups())
            policy = block.translation_policy
            if isinstance(policy, TranslationPolicy):
                policies[key] = policy
            else:
                policies[key] = TranslationPolicy(str(policy))
    return policies


def resolve_table_cell_policy(
    *,
    table_path: tuple[int, int, int] | None,
    source_text: str,
    policies: dict[tuple[int, int, int], TranslationPolicy],
) -> TranslationPolicy | None:
    if table_path is None:
        return None
    policy = policies.get(table_path)
    if policy is not None:
        return policy
    return classify_cell_policy(source_text)


@dataclass(frozen=True)
class DocxSegmentBatch:
    llm_texts: list[str]
    llm_to_original: list[int]
    token_maps: dict[int, dict[str, str]]
    preserved_indices: frozenset[int]


def partition_docx_segments(
    originals: list[str],
    elements: list[dict],
    manifest: DocumentStructureManifest | None,
) -> DocxSegmentBatch:
    policies = table_cell_policy_map(manifest)
    llm_texts: list[str] = []
    llm_to_original: list[int] = []
    token_maps: dict[int, dict[str, str]] = {}
    preserved: set[int] = set()

    for index, (original, info) in enumerate(zip(originals, elements)):
        policy = resolve_table_cell_policy(
            table_path=info.get("table_path"),
            source_text=original,
            policies=policies,
        )
        if policy is TranslationPolicy.PRESERVE:
            preserved.add(index)
            continue
        if policy in DEFERRED_TRANSLATION_POLICIES:
            # PLAN-034b：TERM_ONLY / HUMAN_REVIEW 不送 LLM
            preserved.add(index)
            continue
        text = original
        if policy is TranslationPolicy.PROTECT_TOKENS:
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


def merge_docx_translations(
    originals: list[str],
    llm_texts: list[str],
    llm_to_original: list[int],
    token_maps: dict[int, dict[str, str]],
    preserved_indices: frozenset[int],
) -> list[str]:
    merged = list(originals)
    for llm_index, original_index in enumerate(llm_to_original):
        text = llm_texts[llm_index]
        mapping = token_maps.get(original_index)
        if mapping:
            text = restore_tokens(text, mapping)
        merged[original_index] = text
    for index in preserved_indices:
        merged[index] = originals[index]
    return merged
