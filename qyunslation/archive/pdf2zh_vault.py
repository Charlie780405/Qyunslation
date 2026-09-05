# SPDX-License-Identifier: MPL-2.0
"""pdf2zh 翻译产物写入 Vault 并触发 Hermes 向量索引。"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from qyunslation.archive.models import ArchiveRecord
from qyunslation.archive.pdf_text import extract_pdf_text, pick_mono_pdf, pick_translated_md

logger = logging.getLogger(__name__)

# 不复制进 Vault assets 的类型（原文过大，仅 MinIO）
_SKIP_VAULT_COPY = {"source_pdf"}


def _preview(text: str, limit: int = 8000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _file_type_of(name: str) -> str:
    n = name.lower()
    if n.endswith(".letter-mono.pdf") or n.endswith(".mono.pdf"):
        return "mono_pdf" if not n.endswith(".letter-mono.pdf") else "letter_mono_pdf"
    if n.endswith(".dual.pdf"):
        return "dual_pdf"
    if n.endswith(".zh.md"):
        return "translated_md"
    if n.endswith(".zh.docx"):
        return "translated_docx"
    if n.endswith(".glossary.csv"):
        return "glossary_csv"
    if n.endswith(".pdf"):
        return "source_pdf"
    return "other"


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
    formats: list[str] = []
    seen_names: set[str] = set()
    for src in output_paths:
        if not src.is_file():
            continue
        if src.name in seen_names:
            continue
        seen_names.add(src.name)
        ft = _file_type_of(src.name)
        # 对照 ArchiveRecord.files 的 source 角色；路径侧跳过疑似原文大文件
        if ft in _SKIP_VAULT_COPY:
            continue
        # 与 group 同名的原文 PDF 不进 Vault
        if src.name == record.original_filename:
            continue
        dest = assets_dir / src.name
        shutil.copy2(src, dest)
        copied.append((src.name, dest))
        if ft not in formats and ft != "other":
            formats.append(ft)

    # 记录里的 source MinIO key
    original_storage_key = ""
    for f in record.files:
        if f.role == "source" or f.file_type == "source_pdf":
            original_storage_key = f.storage_key
            break
        if f.file_type not in formats and f.file_type not in ("other",):
            if f.file_type not in formats:
                formats.append(f.file_type)

    md_path = pick_translated_md(output_paths)
    translated_text = ""
    body_source = "pdf_extract"
    if md_path and md_path.is_file():
        try:
            translated_text = md_path.read_text(encoding="utf-8")
            body_source = "translated_md"
        except OSError as exc:
            logger.warning("读取译文 md 失败 %s: %s", md_path.name, exc)
    if not translated_text:
        mono = pick_mono_pdf(output_paths)
        if mono:
            try:
                translated_text = extract_pdf_text(mono)
            except Exception as exc:
                logger.warning("PDF 文本提取失败 %s: %s", mono.name, exc)

    stem = Path(record.original_filename).stem
    note_name = f"{record.archive_id}-{stem}.md"
    note_path = note_dir / note_name
    doc_profile = (record.extra or {}).get("doc_profile", "")
    formats_csv = ", ".join(formats) if formats else "pdf"

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
        f"formats: [{formats_csv}]",
        f"original_storage_key: {original_storage_key or ''}",
        f"doc_profile: {doc_profile or ''}",
        f"body_source: {body_source}",
        "---",
        "",
        f"# {stem}（{record.to_lang} · PDF 保留排版）",
        "",
        "## 元数据",
        f"- 编号：`{record.archive_id}`",
        f"- 原文件：{record.original_filename}",
        f"- 引擎：PDFMathTranslate-next / BabelDOC",
        f"- 存储：MinIO `{record.storage_backend}`",
    ]
    if original_storage_key:
        lines.append(f"- 原文 MinIO：`{original_storage_key}`")
    if doc_profile:
        lines.append(f"- 文档画像：`{doc_profile}`")

    lines.extend(["", "## 归档文件（Vault 附件）"])
    for name, _ in copied:
        lines.append(f"- [[{translations_dir}/{rel_assets}/{name}|{name}]]")
    if not copied:
        lines.append("- （无 Vault 附件）")

    if original_storage_key:
        lines.extend(
            [
                "",
                "## 原文（仅 MinIO）",
                f"- `{original_storage_key}`",
            ]
        )

    lines.extend(["", "## 译文正文", ""])
    if translated_text:
        if body_source == "translated_md":
            lines.append(translated_text.strip())
        else:
            lines.append(_preview(translated_text, 12000))
    else:
        lines.append("> （未能从 PDF / Markdown 提取文本，见上方链接）")

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
