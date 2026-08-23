# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArchiveFileRef:
    role: str  # source | translated | attachment
    file_type: str
    filename: str
    storage_key: str
    size_bytes: int = 0


@dataclass
class ArchiveRecord:
    archive_id: str
    task_id: str
    original_filename: str
    to_lang: str
    workflow_type: str
    created_at: str
    storage_backend: str
    files: list[ArchiveFileRef] = field(default_factory=list)
    vault_note_path: str | None = None
    source_text_preview: str = ""
    translated_text_preview: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "task_id": self.task_id,
            "original_filename": self.original_filename,
            "to_lang": self.to_lang,
            "workflow_type": self.workflow_type,
            "created_at": self.created_at,
            "storage_backend": self.storage_backend,
            "vault_note_path": self.vault_note_path,
            "source_text_preview": self.source_text_preview,
            "translated_text_preview": self.translated_text_preview,
            "files": [
                {
                    "role": f.role,
                    "file_type": f.file_type,
                    "filename": f.filename,
                    "storage_key": f.storage_key,
                    "size_bytes": f.size_bytes,
                }
                for f in self.files
            ],
            "extra": self.extra,
        }
