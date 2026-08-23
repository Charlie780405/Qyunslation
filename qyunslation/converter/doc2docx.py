# SPDX-License-Identifier: MPL-2.0
"""PLAN-005b：.doc → .docx（LibreOffice headless）。"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_docx(filename: str, content: bytes) -> tuple[str, bytes]:
    """若为 .doc 则转 docx；已是 docx 原样返回。无 soffice 时抛清晰错误。"""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return filename, content
    if suffix != ".doc":
        return filename, content

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ValueError("不支持 .doc：请另存为 .docx，或在服务器安装 LibreOffice（soffice）")

    with tempfile.TemporaryDirectory(prefix="doc2docx_") as td:
        td_path = Path(td)
        src = td_path / "input.doc"
        src.write_bytes(content)
        cmd = [
            soffice,
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(td_path),
            str(src),
        ]
        logger.info("converting .doc → .docx: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise ValueError(f".doc 转换失败: {proc.stderr or proc.stdout}")
        out = td_path / "input.docx"
        if not out.is_file():
            raise ValueError(".doc 转换失败：未生成 docx")
        new_name = Path(filename).with_suffix(".docx").name
        return new_name, out.read_bytes()
