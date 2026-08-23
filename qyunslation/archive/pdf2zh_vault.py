# SPDX-License-Identifier: MPL-2.0
"""pdf2zh 翻译产物写入 Vault 并触发 Hermes 向量索引。"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from qyunslation.archive.models import ArchiveRecord
from qyunslation.archive.pdf2zh_ingest import infer_original_filename
from qyunslation.archive.pdf_text import extract_pdf_text, pick_mono_pdf

logger = logging.getLogger(__name__)


def _preview(text: str, limit: int = 8000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def write_vault_note(
    *,
    record: ArchiveRecord,
    group_key: str,
    output_paths: list[Path],
    vault_root: Path,
    translations_dir: str = "10-Source-Documents/Translations",
    assets_subdir: str = "assets",
) -> str | None:
    if not vault_root.is_dir():
        logger.warning("Vault 不存在: %s", vault_root)
        return None

    note_dir = vault_root / translations_dir.strip("/")
    assets_dir = note_dir / assets_subdir / record.archive_id
    note_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    rel_assets = f"{assets_subdir}/{record.archive_id}"
    copied: list[tuple[str, Path]] = []
    for src in output_paths:
        if not src.is_file():
            continue
        dest = assets_dir / src.name
        shutil.copy2(src, dest)
        copied.append((src.name, dest))

    mono = pick_mono_pdf(output_paths)
    translated_text = ""
    if mono:
        try:
            translated_text = extract_pdf_text(mono)
        except Exception as exc:
            logger.warning("PDF 文本提取失败 %s: %s", mono.name, exc)

    stem = Path(record.original_filename).stem
    note_name = f"{record.archive_id}-{stem}.md"
    note_path = note_dir / note_name

    lines = [
        "---",
        f"archive_id: {record.archive_id}",
        f"task_id: {record.task_id}",
        f"source_file: {record.original_filename}",
        f"target_lang: {record.to_lang}",
        f"workflow_type: pdf2zh",
        f"created_at: {record.created_at}",
        f"title: {stem}（{record.to_lang} · PDF 翻译）",
        "tags: [translation, pdf2zh, babeldoc]",
        "source_grade: B",
        f"output_group: {group_key}",
        "---",
        "",
        f"# {stem}（{record.to_lang} · PDF 保留排版）",
        "",
        "## 元数据",
        f"- 编号：`{record.archive_id}`",
        f"- 原文件：{record.original_filename}",
        f"- 引擎：PDFMathTranslate-next / BabelDOC",
        f"- 存储：MinIO `{record.storage_backend}`",
        "",
        "## 归档文件",
    ]
    for name, _ in copied:
        lines.append(
            f"- [[{translations_dir}/{rel_assets}/{name}|{name}]]"
        )

    lines.extend(["", "## 译文正文摘录", ""])
    if translated_text:
        lines.append(_preview(translated_text, 12000))
    else:
        lines.append("> （未能从 PDF 提取文本，见上方链接）")

    lines.extend(
        [
            "",
            "## 检索说明",
            "- 本条目由 translate.qyunsgen.com 自动入库",
            "- 可通过 knowledge.qyunsgen.com 混合/向量检索",
            "",
        ]
    )
    note_path.write_text("\n".join(lines), encoding="utf-8")
    return str(note_path.relative_to(vault_root))


def run_vault_indexer(
    *,
    vault_note_rel: str,
    hermes_root: Path,
    hermes_python: Path,
    timeout: int = 300,
) -> bool:
    indexer = hermes_root / "rag/vault_indexer.py"
    if not indexer.is_file():
        logger.warning("缺少 vault_indexer: %s", indexer)
        return False
    cmd = [
        str(hermes_python),
        str(indexer),
        "--files",
        vault_note_rel,
        "--force",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("向量索引失败: %s", exc)
        return False
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-400:]
        logger.warning("vault_indexer exit %s: %s", proc.returncode, tail)
        return False
    logger.info("向量索引完成: %s", vault_note_rel)
    return True


def ingest_vault_and_index(
    *,
    record: ArchiveRecord,
    group_key: str,
    output_paths: list[Path],
    vault_root: Path,
    hermes_root: Path,
    hermes_python: Path,
    translations_dir: str = "10-Source-Documents/Translations",
    index_enable: bool = True,
) -> str | None:
    rel = write_vault_note(
        record=record,
        group_key=group_key,
        output_paths=output_paths,
        vault_root=vault_root,
        translations_dir=translations_dir,
    )
    if not rel:
        return None
    if index_enable:
        run_vault_indexer(
            vault_note_rel=rel,
            hermes_root=hermes_root,
            hermes_python=hermes_python,
        )
    return rel
