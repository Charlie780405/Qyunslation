#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kv_reinsert as kr  # noqa: E402


class TestKvReinsert(unittest.TestCase):
    def test_map_label_and_value(self):
        g = kr._load_glossary()
        self.assertEqual(kr._map_text("Meeting Type:", g), "会议类型：")
        self.assertEqual(kr._map_text("GS301", g), "GS301")
        self.assertIn("351(k)", kr._map_text("351(k) of the Public Health Service Act", g))
        self.assertTrue(kr._map_text("351(k) of the Public Health Service Act", g).startswith("《"))

    def test_cjk_glue_and_joined_last_sentence(self):
        self.assertEqual(kr._cjk_glue("问 题 以及"), "问题以及")
        zh = kr._body_zh(
            "On June 12, 2026, Jiangsu GenScend Biopharma Co., Ltd. submitted. "
            "The Agency sent a meeting request granted letter",
            [],
        )
        self.assertIn("该机构于2026年6月26日向江苏发送了会议请求批准函", zh)
        self.assertNotIn("\n", zh)
        intro = kr._body_zh("This material consists of our preliminary responses to your questions", [])
        self.assertIn("本材料包含我们对您问题的初步回复", intro)
        self.assertNotIn("问 题", intro)

    def test_page3_bodies_and_letterhead_strip(self):
        q = kr._body_zh("Question 1: Based on the totality of analytical comparability", [])
        self.assertTrue(q.startswith("问题1："))
        resp = kr._body_zh(
            "FDA Response to Question 1(a): Yes. U.S. Food and Drug Administration Silver Spring, MD 20993",
            [],
        )
        self.assertIn("FDA对问题1(a)的回复", resp)
        self.assertNotIn("Silver Spring", resp)
        self.assertEqual(
            kr._item_zh("Reference ID: 5864277", "footer", []),
            "参考编号：5864277",
        )
        self.assertEqual(kr._item_zh("CMC", "section", kr._load_glossary()), "CMC")
        self.assertEqual(kr._item_zh("Page 4", "header", []), "第4页")
        self.assertEqual(
            kr._item_zh("Question 2: leftover english", "body", [], "问题2：模型译文"),
            "问题2：模型译文",
        )
        self.assertEqual(
            kr._draw_style("body", "Question 3: Does the Agency", "r", "b")[1],
            "b",
        )
        self.assertEqual(
            kr._draw_style("body", "b) We note that PTMs", "r", "b")[1],
            "r",
        )
        self.assertEqual(
            kr._draw_style("body", "(a) the scope", "r", "b", in_question=True)[1],
            "b",
        )
        self.assertGreater(kr._wrap_height("甲" * 80, 400.0, 12.0), 12.0 * 2)
        fs_s, sec_s, lead_s, gap_s = kr._flow_plan(6, 2, 600.0)
        self.assertEqual(fs_s, kr._BODY_AIRY)
        self.assertEqual(sec_s, kr._SEC_AIRY)
        self.assertLessEqual(lead_s, 1.60)
        fs_m, sec_m, lead_m, _ = kr._flow_plan(18, 4, 600.0)
        self.assertEqual(fs_m, kr._BODY_AIRY)
        self.assertEqual(sec_m, kr._SEC_AIRY)
        self.assertGreaterEqual(lead_m, kr._LEAD_AIRY)
        fs_n, sec_n, lead_n, _ = kr._flow_plan(28, 5, 600.0)
        self.assertEqual(fs_n, kr._BODY_BASE)
        self.assertEqual(sec_n, kr._SEC_BASE)
        self.assertGreaterEqual(lead_n, kr._LEAD_BASE)
        fs_t, _sec_t, lead_t, gap_t = kr._flow_plan(40, 6, 200.0)
        self.assertEqual(fs_t, kr._BODY_BASE)
        self.assertEqual(lead_t, kr._LEAD_MIN)
        self.assertEqual(gap_t, kr._GAP_MIN)
        self.assertEqual(kr._cjk_glue("建议如下。美国食品与药品管理局"), "建议如下。")


if __name__ == "__main__":
    unittest.main()
