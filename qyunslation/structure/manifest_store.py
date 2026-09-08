# SPDX-License-Identifier: MPL-2.0
"""PLAN-030d：manifest 持久化，供预扫描与执行共用同一份结构结果。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .models import (
    CURRENT_SCHEMA_VERSION,
    DocumentStructureManifest,
)

_SHA256_LEN = 64
_ENV_ROOT = "QYUNSLATION_MANIFEST_CACHE"


def default_cache_root() -> Path:
    override = os.environ.get(_ENV_ROOT)
    if override:
        return Path(override)
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base) / "qyunslation" / "manifests"


def _schema_major(version: str) -> str:
    return version.split(".", 1)[0]


class ManifestStore:
    """按 source_sha256 缓存 manifest。

    缓存只是加速，不是真值：任何读取或写入失败都降级为未命中，绝不阻断翻译。
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_cache_root()

    def path_for(self, source_sha256: str) -> Path:
        digest = str(source_sha256).strip().lower()
        if len(digest) != _SHA256_LEN or not all(
            c in "0123456789abcdef" for c in digest
        ):
            raise ValueError("MANIFEST_STORE_KEY_INVALID: expected full lowercase SHA-256")
        major = _schema_major(CURRENT_SCHEMA_VERSION)
        return self.root / f"v{major}" / f"{digest}.manifest.json"

    def put(self, manifest: DocumentStructureManifest) -> Path | None:
        """原子落盘。失败返回 None，不抛错。

        写入前回读校验一次：summary 与对象不一致等问题若被写进缓存，会退化成永久
        未命中且不留痕迹，宁可此处拒绝写入。
        """
        try:
            target = self.path_for(manifest.document.source_sha256)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = manifest.model_dump_json()
            DocumentStructureManifest.model_validate_json(payload)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(target.parent), prefix=".manifest-", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                os.replace(tmp_name, target)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise
            return target
        except Exception:
            return None

    def get(self, source_sha256: str) -> DocumentStructureManifest | None:
        """命中返回 manifest；未命中、损坏或 schema major 不符一律返回 None。"""
        try:
            target = self.path_for(source_sha256)
        except ValueError:
            return None
        try:
            payload = target.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return None
        try:
            manifest = DocumentStructureManifest.model_validate_json(payload)
        except Exception:
            return None
        if _schema_major(manifest.schema_version) != _schema_major(CURRENT_SCHEMA_VERSION):
            return None
        if manifest.document.source_sha256 != str(source_sha256).strip().lower():
            return None
        return manifest

    def consume(self, manifest: DocumentStructureManifest) -> None:
        """ManifestConsumer 协议：持久化后供下游阶段复用。"""
        self.put(manifest)

    def invalidate(self, source_sha256: str) -> bool:
        try:
            target = self.path_for(source_sha256)
        except ValueError:
            return False
        try:
            target.unlink()
            return True
        except OSError:
            return False
