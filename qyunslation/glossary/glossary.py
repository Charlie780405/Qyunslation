# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
"""Glossary：键规范化 + chunk 命中强指令（PLAN-034d0）。"""
from __future__ import annotations

import csv
from io import StringIO

from qyunslation.ir.document import Document


def _normalize_key(s: str) -> str:
    return " ".join((s or "").strip().split()).casefold()


class Glossary:
    def __init__(self, glossary_dict: dict[str, str] | None = None):
        self.glossary_dict: dict[str, str] = {}
        if glossary_dict:
            self.update(glossary_dict)

    def update(self, update_dict: dict[str, str] | None):
        if not update_dict:
            return
        for src, dst in update_dict.items():
            key = _normalize_key(src)
            if not key:
                continue
            # 已有键不覆盖（保持既有行为）
            if key not in self.glossary_dict:
                self.glossary_dict[key] = dst

    def append_system_prompt(self, text: str) -> str:
        from qyunslation.extensions.glossary_db import (
            build_glossary_prompt,
            filter_glossary_hits,
        )

        hits = filter_glossary_hits(self.glossary_dict, text or "")
        return build_glossary_prompt(hits)

    @staticmethod
    def glossary_dict2csv(
        glossary_dict: dict[str, str], delimiter=",", stem="glossary_gen"
    ) -> Document:
        csv_rows = [[src, dst] for src, dst in glossary_dict.items()]
        content = StringIO()
        writer = csv.writer(content, delimiter=delimiter)
        writer.writerow(["src", "dst"])
        writer.writerows(csv_rows)
        bom = "\ufeff"
        content_with_bom = bom + content.getvalue()
        return Document.from_bytes(
            content=content_with_bom.encode("utf-8"), suffix=".csv", stem=stem
        )
