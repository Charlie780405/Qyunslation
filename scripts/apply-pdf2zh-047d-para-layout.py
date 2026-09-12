#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-047d：放宽段落合并 + 同行横向孤字 + 段间空洞收缩。"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path.home() / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
PF = SITE / "babeldoc/format/pdf/document_il/midend/paragraph_finder.py"
MARKER = "_QY_046B_PARA_MERGE"
MARKER_D = "_QY_047D_PARA_LAYOUT"

# Replace entire 046b method body with 047d-relaxed version
METHOD_047D = f'''
    def {MARKER}(self, paragraphs: list[PdfParagraph]):
        """PLAN-046b/047d：合并同 layout 续行碎片、框外行尾孤字、同行横向孤字。"""
        if not paragraphs or len(paragraphs) < 2:
            return
        _END = set(".?!。？！：;")

        def _fs(p):
            style = getattr(p, "pdf_style", None)
            if style is not None and getattr(style, "font_size", None):
                return float(style.font_size or 0)
            for comp in p.pdf_paragraph_composition or []:
                line = getattr(comp, "pdf_line", None)
                chars = (line.pdf_character if line else None) or []
                if chars:
                    return float(getattr(chars[0], "font_size", 0) or 0)
            return 0.0

        def _numeric_cell(text):
            t = (text or "").strip()
            return bool(t) and any(ch.isdigit() for ch in t) and len(t) <= 20

        def _merge(a, b):
            a_text = (a.unicode or "").rstrip()
            b_text = (b.unicode or "").strip()
            a.pdf_paragraph_composition = list(a.pdf_paragraph_composition or []) + list(
                b.pdf_paragraph_composition or []
            )
            a.box.x = min(float(a.box.x), float(b.box.x))
            a.box.y = min(float(a.box.y), float(b.box.y))
            a.box.x2 = max(float(a.box.x2), float(b.box.x2))
            a.box.y2 = max(float(a.box.y2), float(b.box.y2))
            a.unicode = (a_text + " " + b_text).strip()
            self.update_paragraph_data(a)

        # Pass 1: vertical continuation (relaxed font-size)
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
            fa, fb = _fs(a), _fs(b)
            # PLAN-047d：相对差 ≤35% 或任一段 <5pt（YOLO 误判小框）
            if fa and fb:
                rel = abs(fa - fb) / max(fa, fb)
                if rel > 0.35 and fa >= 5.0 and fb >= 5.0:
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
            # PLAN-049b：同行短数字是表单元格，不是行尾 of
            if float(b.box.x) >= float(a.box.x2) - 2.0 and (
                _numeric_cell(a_text) or _numeric_cell(b_text)
            ):
                i += 1
                continue
            _merge(a, b)
            del paragraphs[i + 1]

        # Pass 2: same-y horizontal orphan (e.g. of at x=540)
        i = 0
        while i < len(paragraphs):
            a = paragraphs[i]
            if not a.box:
                i += 1
                continue
            a_text = (a.unicode or "").rstrip()
            ay_mid = (float(a.box.y) + float(a.box.y2)) / 2.0
            aw = max(1.0, float(a.box.x2) - float(a.box.x))
            j = i + 1
            while j < len(paragraphs):
                b = paragraphs[j]
                if not b.box:
                    j += 1
                    continue
                if (a.layout_label or "") != (b.layout_label or ""):
                    j += 1
                    continue
                by_mid = (float(b.box.y) + float(b.box.y2)) / 2.0
                if abs(by_mid - ay_mid) > 2.0:
                    j += 1
                    continue
                b_text = (b.unicode or "").strip()
                bw = float(b.box.x2) - float(b.box.x)
                # orphan to the right of body
                if float(b.box.x) - float(a.box.x2) < aw * 0.6 and float(b.box.x) > float(a.box.x):
                    # still allow if far to the right of page body
                    pass
                gap_x = float(b.box.x) - float(a.box.x2)
                if gap_x < 0:
                    j += 1
                    continue
                if bw >= 40.0 or len(b_text) > 8:
                    j += 1
                    continue
                if _numeric_cell(b_text) or _numeric_cell(a_text):
                    j += 1
                    continue
                if b_text and b_text[-1] in _END and len(b_text) > 3:
                    j += 1
                    continue
                # require substantial horizontal separation OR body near right
                if gap_x < aw * 0.15 and (float(a.box.x2) - float(a.box.x)) < 200:
                    j += 1
                    continue
                _merge(a, b)
                del paragraphs[j]
                a_text = (a.unicode or "").rstrip()
                aw = max(1.0, float(a.box.x2) - float(a.box.x))
                continue
            i += 1

    def {MARKER_D}(self, paragraphs: list[PdfParagraph]):
        """PLAN-047d：同 layout_id 连续段按译文长度收缩框高并归一段间距。"""
        if not paragraphs or len(paragraphs) < 2:
            return
        # 按 layout_id 分组连续段
        groups: list[list[int]] = []
        cur: list[int] = []
        prev_lid = object()
        for i, p in enumerate(paragraphs):
            lid = getattr(p, "layout_id", None)
            if lid != prev_lid or not p.box:
                if len(cur) >= 2:
                    groups.append(cur)
                cur = [i] if p.box else []
                prev_lid = lid
            else:
                cur.append(i)
        if len(cur) >= 2:
            groups.append(cur)

        for idxs in groups:
            boxes = [paragraphs[i].box for i in idxs]
            # 源段间距中位数（相邻框顶差）
            gaps = []
            for a, b in zip(boxes, boxes[1:]):
                gaps.append(abs(float(a.y) - float(b.y2)))
            if not gaps:
                continue
            gaps_sorted = sorted(gaps)
            med_gap = gaps_sorted[len(gaps_sorted) // 2]
            # 目标段间距：压回合理范围（约 2–14pt）
            target_gap = max(2.0, min(14.0, med_gap if med_gap < 20 else 11.0))
            # 从上往下重排：保留首段顶，后续段顶 = 上一段实际底 - target_gap
            # PDF y 向上增大；box.y 是底，box.y2 是顶
            for k in range(1, len(idxs)):
                prev = paragraphs[idxs[k - 1]]
                cur_p = paragraphs[idxs[k]]
                if not prev.box or not cur_p.box:
                    continue
                # 按 unicode 长度估行数，收缩过高空框
                text = (cur_p.unicode or "").strip()
                fs = 8.0
                style = getattr(cur_p, "pdf_style", None)
                if style is not None and getattr(style, "font_size", None):
                    fs = float(style.font_size or 8.0)
                width = max(20.0, float(cur_p.box.x2) - float(cur_p.box.x))
                # CJK 约 fs 宽；估行数
                chars_per_line = max(1.0, width / max(fs * 0.55, 1.0))
                n_lines = max(1, int((len(text) / chars_per_line) + 0.999))
                line_h = fs * 1.25
                needed_h = n_lines * line_h
                cur_h = float(cur_p.box.y2) - float(cur_p.box.y)
                if cur_h > needed_h + 4.0:
                    # 收缩：保持顶 y2，抬高底 y
                    cur_p.box.y = float(cur_p.box.y2) - needed_h
                # 归一段间距：当前顶贴近上一段底
                desired_top = float(prev.box.y) - target_gap
                h = float(cur_p.box.y2) - float(cur_p.box.y)
                # 若当前顶远低于上一段底（空洞过大），上移整框
                if float(cur_p.box.y2) < desired_top - 3.0:
                    cur_p.box.y2 = desired_top
                    cur_p.box.y = desired_top - h
'''

CALL_047D = f"""        self.{MARKER}(paragraphs)  # PLAN-046b

        self.{MARKER_D}(paragraphs)  # PLAN-047d

        for paragraph in paragraphs:
"""

OLD_CALL_TAIL = f"""        self.{MARKER}(paragraphs)  # PLAN-046b

        for paragraph in paragraphs:
"""


def main() -> int:
    if not PF.is_file():
        print(f"missing {PF}", file=sys.stderr)
        return 1
    text = PF.read_text(encoding="utf-8")
    changed = False

    # Replace old method definition if present
    if f"def {MARKER}(" in text:
        # cut from def MARKER to next "    def "
        start = text.find(f"    def {MARKER}(")
        if start >= 0:
            rest = text[start + 4 :]
            next_def = rest.find("\n    def ")
            if next_def < 0:
                print("cannot find end of method", file=sys.stderr)
                return 1
            end = start + 4 + next_def
            # If 047d layout method already follows, replace both
            if MARKER_D in text[start:end + 200]:
                # find end after MARKER_D method
                d_start = text.find(f"    def {MARKER_D}(")
                if d_start > start:
                    rest2 = text[d_start + 4 :]
                    next2 = rest2.find("\n    def ")
                    if next2 >= 0:
                        end = d_start + 4 + next2
            text = text[:start] + METHOD_047D + "\n" + text[end:]
            changed = True
    else:
        print("046b method missing; run apply-pdf2zh-046b-para-merge.py first", file=sys.stderr)
        return 1

    if MARKER_D not in text or f"self.{MARKER_D}(paragraphs)" not in text:
        if OLD_CALL_TAIL in text:
            text = text.replace(OLD_CALL_TAIL, CALL_047D, 1)
            changed = True
        elif f"self.{MARKER_D}(paragraphs)" not in text:
            print("call site not found", file=sys.stderr)
            return 1

    if changed:
        PF.write_text(text, encoding="utf-8")
        print(f"patched {PF}")
    else:
        print(f"already up to date: {PF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
