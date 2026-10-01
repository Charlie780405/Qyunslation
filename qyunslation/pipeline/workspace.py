# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：任务工作区——原件只读，阶段只写工作副本。"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SealedSource:
    path: Path
    sha256: str
    size_bytes: int


class RunWorkspace:
    """Content-addressed sealed source + per-run/generation work tree."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.sources = self.root / "sources"
        self.runs = self.root / "runs"
        self.sources.mkdir(parents=True, exist_ok=True)
        self.runs.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def seal_source(self, source: Path, *, suffix: str | None = None) -> SealedSource:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        sha = self.sha256_file(source)
        ext = suffix if suffix is not None else source.suffix
        dest = self.sources / sha[:2] / f"{sha}{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            shutil.copy2(source, tmp)
            os.chmod(tmp, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            tmp.replace(dest)
            os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        else:
            # Enforce read-only even if a previous run left a writable copy.
            os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        return SealedSource(path=dest, sha256=sha, size_bytes=dest.stat().st_size)

    def run_dir(self, *, run_id: str, generation: int) -> Path:
        if generation < 1:
            raise ValueError("generation must be >= 1")
        path = self.runs / run_id / f"gen-{generation}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def materialize_work_copy(
        self, sealed: SealedSource, *, run_id: str, generation: int, filename: str
    ) -> Path:
        work = self.run_dir(run_id=run_id, generation=generation)
        safe_name = Path(filename).name or f"source{sealed.path.suffix}"
        dest = work / "input" / safe_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return dest
        shutil.copy2(sealed.path, dest)
        # Work copy may be rewritten by OCR/converters; source stays sealed.
        os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
        return dest

    def assert_source_unchanged(self, sealed: SealedSource) -> None:
        if not sealed.path.is_file():
            raise RuntimeError("sealed source missing")
        mode = sealed.path.stat().st_mode
        if mode & stat.S_IWUSR:
            raise RuntimeError("sealed source is writable")
        if self.sha256_file(sealed.path) != sealed.sha256:
            raise RuntimeError("sealed source hash drifted")
