#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-009a：书信角色标注与清洗夹具。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import letter_layout as ll  # noqa: E402


class TestLetterLayout(unittest.TestCase):
    def test_clean_th_superscript(self):
        self.assertIn("4层", ll.clean_text("4820 Emperor Blvd, 4 ( ^{th} ) Floor"))
        self.assertNotIn("^{", ll.clean_text("4 ( ^{th} ) Floor Durham"))

    def test_clean_fragment(self):
        self.assertEqual(ll.clean_text("给药"), "")
        self.assertEqual(ll.clean_text("Administration"), "Administration")
        self.assertEqual(ll.clean_text("FDA‑"), "")
        self.assertEqual(ll.clean_text("‑"), "")
        self.assertIn("Health Project", ll.clean_text("Regulatory HealProject Manager"))
        self.assertEqual(ll.clean_text("Ophalmology"), "Ophthalmology")
        self.assertTrue(
            ll.clean_text(
                "The Agency has comments. U.S. Food and Drug Administration Silver Spring, MD 20993"
            ).endswith("comments.")
        )

    def test_tag_page1_fixture(self):
        # A4 点坐标，仿页 1 聚合后结构
        pw, ph = 595.0, 842.0
        boxes = [
            (114.0, 72.0, 207.0, 90.0, "FDA U.S. FOOD & DRUG ADMINISTRATION"),
            (68.0, 139.0, 141.0, 155.0, "PIND 182646"),
            (333.0, 166.0, 545.0, 181.0, "MEETING PRELIMINARY COMMENTS"),
            (67.0, 193.0, 276.0, 275.0, "Jiangsu GenScend Biopharma Co., Ltd. c/o IQVIA"),
            (67.0, 301.0, 191.0, 316.0, "Dear Dr. Mei-Fei Yueh:"),
            (
                67.0,
                327.0,
                540.0,
                418.0,
                "Please refer to your pre-investigational new drug application (PIND) file for GS301.",
            ),
            (
                67.0,
                420.0,
                471.0,
                505.0,
                "We also refer to your correspondence. Our preliminary responses to your meeting questions are enclosed.",
            ),
            (234.0, 529.0, 285.0, 546.0, "Sincerely,"),
            (238.0, 583.0, 456.0, 691.0, "Crystal Bland, MSHA Regulatory Health Project Manager"),
            (68.0, 703.0, 268.0, 734.0, "ENCLOSURE: Meeting Preliminary Comments"),
            (8.0, 788.0, 91.0, 810.0, "Reference ID: 5864277"),
        ]
        roles = ll.tag_blocks(boxes, pw, ph)
        by_text = {b[4][:20]: r for b, r in zip(boxes, roles)}
        self.assertEqual(by_text["PIND 182646"], "header")
        self.assertEqual(by_text["Dear Dr. Mei-Fei Yue"], "salutation")
        self.assertEqual(by_text["Please refer to your"], "body")
        self.assertEqual(by_text["We also refer to you"], "body")
        self.assertEqual(by_text["Sincerely,"], "closing")
        self.assertEqual(by_text["Crystal Bland, MSHA "], "signature")
        self.assertEqual(by_text["ENCLOSURE: Meeting P"], "footer")
        self.assertEqual(by_text["Jiangsu GenScend Bio"], "address")

    def test_prepare_drops_fragments(self):
        boxes = [
            (100.0, 70.0, 120.0, 85.0, "给药"),
            (67.0, 327.0, 400.0, 360.0, "Please refer to your file."),
        ]
        cleaned, roles = ll.prepare_letter_boxes(boxes, 595.0, 842.0)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(roles[0], "body")

    def test_ensure_body_indent(self):
        self.assertTrue(ll.ensure_body_indent("我们对您会议问题的初步回复如下。").startswith(ll.INDENT))
        self.assertFalse(ll.ensure_body_indent("尊敬的岳美菲博士：").startswith(ll.INDENT))
        self.assertEqual(ll.ensure_body_indent(ll.INDENT + "已缩"), ll.INDENT + "已缩")
        self.assertFalse(ll.ensure_body_indent("短").startswith(ll.INDENT))

    def test_merge_roles_keep_signature_lines(self):
        sig = [
            (300.0, 580.0, 480.0, 595.0, "Crystal Bland, MSHA"),
            (300.0, 598.0, 480.0, 613.0, "Regulatory Health Project Manager"),
            (300.0, 616.0, 480.0, 631.0, "Division of Regulatory Operations"),
            (300.0, 634.0, 480.0, 649.0, "Office of Regulatory Operations"),
            (300.0, 652.0, 480.0, 667.0, "Office of New Drugs"),
            (300.0, 670.0, 480.0, 685.0, "Center for Drug Evaluation and Research"),
        ]
        roles = ["signature"] * 6
        groups = ll.group_for_merge(sig, roles)
        self.assertEqual(len(groups), 1)
        sub, role, mergeable = groups[0]
        self.assertEqual(role, "signature")
        self.assertFalse(mergeable)
        self.assertEqual(len(sub), 6)

    def test_merge_roles_merge_body_lines(self):
        body = [
            (67.0, 300.0, 500.0, 315.0, "Please refer to your PIND file."),
            (67.0, 320.0, 500.0, 335.0, "We also refer to your correspondence."),
            (67.0, 340.0, 500.0, 355.0, "Our preliminary responses are enclosed."),
        ]
        roles = ["body"] * 3
        groups = ll.group_for_merge(body, roles)
        self.assertEqual(len(groups), 1)
        sub, role, mergeable = groups[0]
        self.assertEqual(role, "body")
        self.assertTrue(mergeable)
        self.assertEqual(len(sub), 3)

    def test_address_hint_line_level(self):
        pw, ph = 595.0, 842.0
        boxes = [
            (67.0, 200.0, 300.0, 215.0, "Attention: Regulatory Affairs"),
            (67.0, 220.0, 300.0, 235.0, "4820 Emperor Blvd"),
            (67.0, 240.0, 300.0, 255.0, "Durham, NC 27703"),
            (67.0, 300.0, 300.0, 315.0, "Dear Dr. Mei-Fei Yueh:"),
        ]
        roles = ll.tag_blocks(boxes, pw, ph)
        self.assertEqual(roles[0], "address")
        self.assertEqual(roles[1], "address")
        self.assertEqual(roles[2], "address")
        self.assertEqual(roles[3], "salutation")

    def test_fold_administration_into_fda_header(self):
        boxes = [
            (114.0, 72.0, 200.0, 90.0, "U.S. FOOD & DRUG"),
            (200.0, 72.0, 260.0, 90.0, "Administration"),
        ]
        roles = ["header", "header"]
        out_b, _ = ll.fold_short_titles(boxes, roles)
        self.assertEqual(len(out_b), 1)
        self.assertIn("Administration", out_b[0][4])

    def test_split_kv_concatenated_fields(self):
        boxes = [
            (
                67.0,
                166.0,
                400.0,
                203.0,
                "Meeting Type: Biosimilar Meeting Category: BPD Type 2b",
            ),
            (
                67.0,
                246.0,
                520.0,
                312.0,
                "Application Number: 182646 Product Name: GS301 Indication: GS301 is being developed for the same indication as those approved",
            ),
            (67.0, 354.0, 500.0, 400.0, "Introduction: This material consists of our replies."),
        ]
        out = ll.split_kv_rows(boxes, 595.0)
        texts = [b[4] for b in out]
        self.assertTrue(any(t.startswith("Meeting Type:") and "Biosimilar" in t for t in texts))
        self.assertTrue(any(t.startswith("Meeting Category:") and "BPD" in t for t in texts))
        self.assertTrue(any(t.startswith("Application Number:") and "182646" in t for t in texts))
        self.assertTrue(any(t.startswith("Product Name:") and "GS301" in t for t in texts))
        self.assertTrue(any(t.startswith("Indication:") and "developed" in t for t in texts))
        self.assertFalse(any(t.startswith("indication:") for t in texts))
        self.assertTrue(any(t.startswith("Introduction:") for t in texts))
        roles = ll.tag_blocks(out, 595.0, 842.0)
        kv_n = sum(1 for r in roles if r == "kv")
        self.assertGreaterEqual(kv_n, 5)

    def test_pack_kv_two_columns_and_split_intro(self):
        boxes = [
            (67.0, 166.0, 400.0, 184.0, "Meeting Type: Biosimilar"),
            (67.0, 186.0, 400.0, 204.0, "Product Name: GS301"),
            (
                67.0,
                206.0,
                520.0,
                224.0,
                "Sponsor Name: Jiangsu GenScend Biopharma Co., Ltd.",
            ),
            (67.0, 226.0, 240.0, 244.0, "Regulatory Pathway:"),
            (245.0, 226.0, 520.0, 244.0, "PHS Act 351(k)"),
            (
                67.0,
                354.0,
                500.0,
                647.0,
                "Introduction: This material consists of our replies to the questions.",
            ),
            (67.0, 622.0, 160.0, 647.0, "BACKGROUND"),
        ]
        split = ll.split_kv_rows(boxes, 595.0)
        split = ll.split_named_sections(split)
        packed = ll.pack_kv_table(split, 595.0, 842.0)
        packed = ll.clamp_before_section_heads(packed)
        self.assertTrue(any(b[4] == "Product Name:" for b in packed))
        self.assertTrue(any(b[4] == "GS301" for b in packed))
        self.assertTrue(any(b[4] == "Sponsor Name:" for b in packed))
        self.assertTrue(any(b[4].startswith("Regulatory Pathway") for b in packed))
        lab_x = {round(b[0], 1) for b in packed if b[4].endswith(":") and ll._KV_LABEL_RE.match(b[4])}
        self.assertEqual(len(lab_x), 1)
        heights = [round(b[3] - b[1], 1) for b in packed if b[4] in {"Product Name:", "GS301"}]
        self.assertEqual(len(set(heights)), 1)
        self.assertGreaterEqual(heights[0], 16.0)
        s_y = next(b[1] for b in packed if b[4] == "Sponsor Name:")
        p_y = next(b[1] for b in packed if b[4].startswith("Regulatory Pathway"))
        self.assertGreater(p_y, s_y + 8.0)
        bg = next(b for b in packed if b[4] == "BACKGROUND")
        body = next(b for b in packed if "replies" in b[4])
        self.assertLessEqual(body[3], bg[1] - 4.0)
        self.assertTrue(any(b[4].startswith("Introduction") for b in packed))
        roles = ll.tag_blocks(packed, 595.0, 842.0)
        self.assertIn("section", roles)
        intro_i = next(i for i, b in enumerate(packed) if b[4].startswith("Introduction"))
        bg_i = next(i for i, b in enumerate(packed) if b[4] == "BACKGROUND")
        self.assertEqual(roles[intro_i], "section")
        self.assertEqual(roles[bg_i], "section")

    def test_meeting_title_is_section_not_header(self):
        boxes = [
            (192.0, 139.0, 402.0, 164.0, "PRELIMINARY MEETING COMMENTS"),
            (67.0, 166.0, 240.0, 186.0, "Meeting Type: Biosimilar"),
        ]
        roles = ll.tag_blocks(boxes, 595.0, 842.0)
        self.assertEqual(roles[0], "section")
        self.assertEqual(ll.role_font_size("section", {"section_font_size": 14.0}), 14.0)

    def test_split_prea_title_from_body(self):
        boxes = [
            (
                67.0,
                200.0,
                520.0,
                400.0,
                "PREA REQUIREMENTS Under the Pediatric Research Equity Act (PREA) all applications",
            )
        ]
        out = ll.split_leading_caps_title(boxes)
        self.assertEqual(out[0][4], "PREA REQUIREMENTS")
        self.assertTrue(out[1][4].startswith("Under the Pediatric"))

    def test_page3_continuation_and_qa_sections(self):
        pw, ph = 595.32, 841.92
        boxes = [
            (67.0, 70.0, 141.0, 82.0, "PIND 182646"),
            (67.0, 84.0, 108.0, 98.0, "Page 2"),
            (
                67.0,
                120.0,
                516.0,
                147.0,
                "to Jiangsu on June 26, 2026, listing September 18, 2026, as the agreed upon meeting date.",
            ),
            (
                67.0,
                159.0,
                520.0,
                238.0,
                "FDA may provide further clarifications of, or refinements and/or changes to these preliminary responses.",
            ),
            (67.0, 240.0, 346.0, 265.0, "PRELIMINARY RESPONSES TO THE QUESTIONS"),
            (67.0, 307.0, 99.0, 322.0, "CMC"),
            (67.0, 760.0, 130.0, 786.0, "www.fda.gov"),
        ]
        roles = ll.tag_blocks(boxes, pw, ph)
        paired = {b[4]: r for b, r in zip(boxes, roles)}
        self.assertEqual(paired["PIND 182646"], "header")
        self.assertEqual(paired["Page 2"], "header")
        self.assertEqual(paired[boxes[2][4]], "body")
        self.assertEqual(paired[boxes[3][4]], "body")
        self.assertEqual(paired["PRELIMINARY RESPONSES TO THE QUESTIONS"], "section")
        self.assertEqual(paired["CMC"], "section")
        self.assertEqual(paired["www.fda.gov"], "footer")
        self.assertEqual(
            ll.tag_paragraph_text(
                "FDA may provide further clarifications of the advice.",
                y_ratio=0.19,
                x_ratio=0.11,
            ),
            "body",
        )
        caps = ll.tag_blocks(
            [(67.0, 120.0, 400.0, 140.0, "DATA STANDARDS FOR STUDIES")],
            595.32,
            841.92,
        )
        self.assertEqual(caps[0], "section")

    def test_page_bottom_body_is_not_footer(self):
        role = ll.tag_paragraph_text(
            "机构发送了会议请求批准函", y_ratio=0.86, x_ratio=0.11
        )
        self.assertEqual(role, "body")
        self.assertEqual(
            ll.tag_paragraph_text("Reference ID: 5864277", y_ratio=0.94, x_ratio=0.02),
            "footer",
        )

    def test_fold_ophthalmology_into_title(self):
        boxes = [
            (300.0, 580.0, 480.0, 595.0, "Regulatory Health Project Manager"),
            (300.0, 598.0, 360.0, 613.0, "Ophthalmology"),
        ]
        roles = ["signature", "signature"]
        out_b, out_r = ll.fold_short_titles(boxes, roles)
        self.assertEqual(len(out_b), 1)
        self.assertIn("Ophthalmology", out_b[0][4])
        self.assertEqual(out_r, ["signature"])


if __name__ == "__main__":
    unittest.main()
