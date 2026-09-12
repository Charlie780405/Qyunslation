#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-046b：BabelDOC 段落再合并 + typesetting min_scale 可读。"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path.home() / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
PF = SITE / "babeldoc/format/pdf/document_il/midend/paragraph_finder.py"
TS = SITE / "babeldoc/format/pdf/document_il/midend/typesetting.py"
MARKER = "_QY_046B_PARA_MERGE"

OLD_CALL = """        if getattr(self.translation_config, "merge_alternating_line_numbers", True):
            self.merge_alternating_line_number_paragraphs(paragraphs)

        for paragraph in paragraphs:
            self.update_paragraph_data(paragraph, update_unicode=True)
"""

NEW_CALL = f"""        if getattr(self.translation_config, "merge_alternating_line_numbers", True):
            self.merge_alternating_line_number_paragraphs(paragraphs)

        self.{MARKER}(paragraphs)  # PLAN-046b

        for paragraph in paragraphs:
            self.update_paragraph_data(paragraph, update_unicode=True)
"""

METHOD = f'''
    def {MARKER}(self, paragraphs: list[PdfParagraph]):
        """PLAN-046b：合并同 layout 续行碎片与框外行尾孤字（如 of）。"""
        if not paragraphs or len(paragraphs) < 2:
            return
        _END = set(".?!。？！：;")
        i = 0
        while i < len(paragraphs) - 1:
            a = paragraphs[i]
            b = paragraphs[i + 1]
            if (a.layout_label or "") != (b.layout_label or ""):
                i += 1
                continue
            if not a.box or not b.box:
                i += 1
                continue
            ah = max(1.0, float(a.box.y2) - float(a.box.y))
            gap = float(a.box.y) - float(b.box.y2)
            if gap > ah * 1.6 or gap < -ah * 0.3:
                i += 1
                continue
            a_text = (a.unicode or "").rstrip()
            b_text = (b.unicode or "").strip()
            if not a_text or not b_text:
                i += 1
                continue
            if a_text[-1] in _END:
                i += 1
                continue
            def _fs(p):
                for comp in p.pdf_paragraph_composition or []:
                    line = getattr(comp, "pdf_line", None)
                    chars = (line.pdf_character if line else None) or []
                    if chars:
                        return float(getattr(chars[0], "font_size", 0) or 0)
                return 0.0
            fa, fb = _fs(a), _fs(b)
            if fa and fb and abs(fa - fb) > 0.3:
                i += 1
                continue
            left_edge = min(float(a.box.x), float(b.box.x))
            right_edge = max(float(a.box.x2), float(b.box.x2))
            span = max(1.0, right_edge - left_edge)
            a_near_right = (float(a.box.x2) - left_edge) >= span * 0.85
            b_near_left = (float(b.box.x) - left_edge) <= span * 0.15
            b_is_orphan = (float(b.box.x2) - float(b.box.x)) < 30.0 and len(b_text) <= 8
            if not (a_near_right or b_near_left or b_is_orphan):
                i += 1
                continue
            a.pdf_paragraph_composition = list(a.pdf_paragraph_composition or []) + list(
                b.pdf_paragraph_composition or []
            )
            a.box.x = min(float(a.box.x), float(b.box.x))
            a.box.y = min(float(a.box.y), float(b.box.y))
            a.box.x2 = max(float(a.box.x2), float(b.box.x2))
            a.box.y2 = max(float(a.box.y2), float(b.box.y2))
            a.unicode = (a_text + " " + b_text).strip()
            self.update_paragraph_data(a)
            del paragraphs[i + 1]
'''

OLD_MIN = "        min_scale = 0.1"
NEW_MIN = (
    "        min_scale = float(globals().get('_QY_MIN_SCALE', 0.1) or 0.1)"
    "  # PLAN-046b"
)


def patch_paragraph_finder(text: str) -> tuple[str, bool]:
    changed = False
    if MARKER not in text:
        if OLD_CALL not in text:
            print("ERROR: merge_alternating anchor missing", file=sys.stderr)
            return text, False
        text = text.replace(OLD_CALL, NEW_CALL, 1)
        changed = True
    if f"def {MARKER}(" not in text:
        anchor = (
            "    def merge_alternating_line_number_paragraphs"
            "(self, paragraphs: list[PdfParagraph]):"
        )
        if anchor not in text:
            print("ERROR: method anchor missing", file=sys.stderr)
            return text, False
        text = text.replace(anchor, METHOD + "\n" + anchor, 1)
        changed = True
    return text, changed


def patch_typesetting(text: str) -> tuple[str, bool]:
    if "globals().get('_QY_MIN_SCALE'" in text:
        return text, False
    if OLD_MIN not in text:
        print("ERROR: min_scale=0.1 anchor missing", file=sys.stderr)
        return text, False
    return text.replace(OLD_MIN, NEW_MIN, 1), True


def main() -> int:
    ok = True
    if not PF.is_file():
        print(f"ERROR: missing {PF}", file=sys.stderr)
        return 1
    raw = PF.read_text(encoding="utf-8")
    patched, changed = patch_paragraph_finder(raw)
    if changed:
        PF.write_text(patched, encoding="utf-8")
        print(f"patched {PF}")
    else:
        print(f"unchanged {PF}")
    if MARKER not in patched:
        print("ERROR: 046b para merge not present", file=sys.stderr)
        ok = False

    if not TS.is_file():
        print(f"ERROR: missing {TS}", file=sys.stderr)
        return 1
    ts_raw = TS.read_text(encoding="utf-8")
    ts_patched, ts_changed = patch_typesetting(ts_raw)
    if ts_changed:
        TS.write_text(ts_patched, encoding="utf-8")
        print(f"patched {TS}")
    else:
        print(f"unchanged {TS}")
    if "globals().get('_QY_MIN_SCALE'" not in ts_patched:
        print("ERROR: 046b min_scale not present", file=sys.stderr)
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
