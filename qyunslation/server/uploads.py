"""Bounded streaming helpers for untrusted FastAPI uploads."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol

from qyunslation.structure.ingest import (
    DEFAULT_MAX_UPLOAD_BYTES,
    InputPreparationError,
)


DEFAULT_UPLOAD_CHUNK_BYTES = 1024 * 1024


class AsyncUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def configured_max_upload_bytes(
    environment: Mapping[str, str] | None = None,
) -> int:
    """Read a positive byte limit without silently disabling the bound."""

    env = os.environ if environment is None else environment
    raw = (env.get("QYUNSLATION_MAX_UPLOAD_BYTES") or "").strip()
    if not raw:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("QYUNSLATION_MAX_UPLOAD_BYTES must be an integer") from exc
    if value <= 0:
        raise RuntimeError("QYUNSLATION_MAX_UPLOAD_BYTES must be positive")
    return value


async def read_upload_limited(
    upload: AsyncUpload,
    *,
    max_bytes: int | None = None,
    chunk_size: int = DEFAULT_UPLOAD_CHUNK_BYTES,
) -> bytes:
    """Read an upload incrementally and fail as soon as it exceeds the limit."""

    limit = configured_max_upload_bytes() if max_bytes is None else max_bytes
    if limit <= 0 or chunk_size <= 0:
        raise ValueError("upload limits must be positive")

    output = bytearray()
    while True:
        chunk = await upload.read(min(chunk_size, limit - len(output) + 1))
        if not chunk:
            return bytes(output)
        if len(chunk) > limit - len(output):
            raise InputPreparationError(
                "UPLOAD_TOO_LARGE",
                f"上传文件超过 {limit} 字节限制",
                http_status=413,
            )
        output.extend(chunk)
