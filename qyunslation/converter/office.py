# SPDX-License-Identifier: MPL-2.0
"""Isolated LibreOffice normalization for legacy DOC/PPT inputs."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qyunslation.structure.ingest import (
    DEFAULT_MAX_UPLOAD_BYTES,
    InputPreparationError,
    detect_input,
    sanitize_upload_name,
)
from qyunslation.structure.models import SourceFormat


_TARGETS = {
    SourceFormat.DOC: (SourceFormat.DOCX, "docx"),
    SourceFormat.PPT: (SourceFormat.PPTX, "pptx"),
}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


@dataclass(frozen=True, slots=True)
class OfficeConversion:
    output_name: str
    output_format: SourceFormat
    content: bytes = field(repr=False)
    converter: str = "libreoffice"
    converter_version: str = "unknown"
    parameters: dict[str, Any] = field(default_factory=dict)


def _safe_process_detail(value: str | None) -> str:
    cleaned = _CONTROL_CHARS.sub(" ", value or "").strip()
    return cleaned[:1_000]


def _read_version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return "unknown"
    return _safe_process_detail(result.stdout or result.stderr) or "unknown"


class LibreOfficeConverter:
    """Convert one legacy Office payload in an isolated temporary directory."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        version: str | None = None,
        timeout_seconds: int = 120,
        max_output_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        command_finder: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.executable = executable or command_finder("soffice") or command_finder(
            "libreoffice"
        )
        self.version = version or (
            _read_version(self.executable)
            if self.executable and runner is subprocess.run
            else "unknown"
        )
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.runner = runner

    def convert(
        self,
        source_name: str,
        content: bytes,
        source_format: SourceFormat,
    ) -> OfficeConversion:
        if source_format not in _TARGETS:
            raise InputPreparationError(
                "OFFICE_SOURCE_FORMAT_UNSUPPORTED",
                f"LibreOffice 规范化不接受 {source_format.value}",
                http_status=415,
            )
        if not self.executable:
            raise InputPreparationError(
                "OFFICE_CONVERTER_UNAVAILABLE",
                "当前服务器未安装 LibreOffice/soffice",
                http_status=503,
        )
        target_format, target_extension = _TARGETS[source_format]
        safe_name = sanitize_upload_name(source_name)
        output_name = f"{Path(safe_name).stem}.{target_extension}"
        source_extension = ".doc" if source_format is SourceFormat.DOC else ".ppt"

        with tempfile.TemporaryDirectory(prefix="qy_office_normalize_") as temp_name:
            temp_dir = Path(temp_name)
            profile_dir = temp_dir / "profile"
            profile_dir.mkdir()
            source_path = temp_dir / f"input{source_extension}"
            source_path.write_bytes(content)
            output_path = temp_dir / f"input.{target_extension}"
            command = [
                self.executable,
                f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                "--headless",
                "--convert-to",
                target_extension,
                "--outdir",
                str(temp_dir),
                str(source_path),
            ]
            try:
                result = self.runner(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise InputPreparationError(
                    "OFFICE_CONVERSION_TIMEOUT",
                    f"Office 规范化超过 {self.timeout_seconds} 秒",
                    http_status=504,
                ) from exc
            except OSError as exc:
                raise InputPreparationError(
                    "OFFICE_CONVERTER_UNAVAILABLE",
                    "无法启动 LibreOffice/soffice",
                    http_status=503,
                ) from exc

            if result.returncode != 0:
                detail = _safe_process_detail(result.stderr or result.stdout)
                suffix = f"：{detail}" if detail else ""
                raise InputPreparationError(
                    "OFFICE_CONVERSION_FAILED",
                    f"LibreOffice 返回退出码 {result.returncode}{suffix}",
                )
            if not output_path.is_file():
                raise InputPreparationError(
                    "OFFICE_OUTPUT_MISSING", "LibreOffice 未生成预期输出文件"
                )
            if output_path.stat().st_size > self.max_output_bytes:
                raise InputPreparationError(
                    "OFFICE_OUTPUT_TOO_LARGE",
                    "Office 规范化输出超过安全上限",
                    http_status=413,
                )
            output = output_path.read_bytes()

        try:
            detected = detect_input(
                output_name,
                output,
                max_bytes=self.max_output_bytes,
            )
        except InputPreparationError as exc:
            raise InputPreparationError(
                "OFFICE_OUTPUT_INVALID",
                "LibreOffice 输出不是有效的目标 OOXML 文档",
            ) from exc
        if detected.source_format is not target_format:
            raise InputPreparationError(
                "OFFICE_OUTPUT_INVALID",
                f"LibreOffice 输出格式不是 {target_format.value}",
            )

        return OfficeConversion(
            output_name=output_name,
            output_format=target_format,
            content=output,
            converter_version=self.version,
            parameters={
                "headless": True,
                "timeout_seconds": self.timeout_seconds,
                "target": target_extension,
            },
        )
