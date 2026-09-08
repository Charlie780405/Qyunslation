"""Public protocols for future structure scanners and manifest consumers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import ContentProfile, DocumentStructureManifest, ProcessingMode


@runtime_checkable
class StructureScanner(Protocol):
    """Produce a validated structure manifest without translating the document."""

    def scan(
        self,
        source: Path,
        *,
        content_profile: ContentProfile | None = None,
        processing_mode: ProcessingMode | None = None,
    ) -> DocumentStructureManifest: ...


@runtime_checkable
class ManifestConsumer(Protocol):
    """Consume a validated manifest without depending on detector internals."""

    def consume(self, manifest: DocumentStructureManifest) -> None: ...
