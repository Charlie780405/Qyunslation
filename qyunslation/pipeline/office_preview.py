# SPDX-License-Identifier: MPL-2.0
"""PLAN-071f：DOCX/PPTX → 受保护 PDF 预览（LibreOffice headless），带稳定错误码。"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

OFFICE_SUFFIXES = {".docx", ".doc", ".pptx", ".ppt"}
IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class OfficePreviewError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _soffice() -> str | None:
    override = (os.environ.get("QYUNSLATION_SOFFICE") or "").strip()
    if override:
        return override if Path(override).exists() else None
    return shutil.which("soffice") or shutil.which("libreoffice")


def preview_cache_dir() -> Path:
    raw = (os.environ.get("QYUNSLATION_PIPELINE_ROOT") or "var/pipeline").strip()
    root = Path(raw)
    root = root if root.is_absolute() else Path.cwd() / root
    return root / "preview-cache"


def office_to_pdf(path: Path, *, timeout: int = 120) -> Path:
    """返回缓存的预览 PDF；失败抛 ``OfficePreviewError``（code 稳定可断言）。"""
    if path.suffix.casefold() not in OFFICE_SUFFIXES:
        raise OfficePreviewError("OFFICE_PREVIEW_UNSUPPORTED", "not an office document")
    stat = path.stat()
    digest = hashlib.sha256(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:32]
    cache = preview_cache_dir()
    target = cache / f"{digest}.pdf"
    if target.is_file():
        return target
    exe = _soffice()
    if exe is None:
        raise OfficePreviewError("OFFICE_PREVIEW_UNAVAILABLE", "LibreOffice (soffice) is not installed")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p071-office-") as tmp:
        work = Path(tmp)
        src = work / f"in{path.suffix.casefold()}"
        shutil.copyfile(path, src)
        profile = work / "profile"
        try:
            proc = subprocess.run(
                [
                    exe,
                    f"-env:UserInstallation=file://{profile}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(work),
                    str(src),
                ],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OfficePreviewError("OFFICE_PREVIEW_TIMEOUT", "office conversion timed out") from exc
        produced = work / "in.pdf"
        if proc.returncode != 0 or not produced.is_file():
            raise OfficePreviewError("OFFICE_PREVIEW_FAILED", "office conversion failed")
        shutil.move(str(produced), target)
    return target
