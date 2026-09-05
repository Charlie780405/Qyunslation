#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-010d：专名 harvest 夹具。"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import proper_nouns as pn  # noqa: E402


class TestProperNouns(unittest.TestCase):
    def test_camelcase_harvested(self):
        terms = pn.harvest_from_text("Jiangsu GenScend Biopharma met IQVIA staff.")
        self.assertIn("GenScend", terms)
        self.assertIn("IQVIA", terms)

    def test_stopword_skipped(self):
        terms = pn.harvest_from_text("FDA reviewed the PIND file for MEETING.")
        self.assertNotIn("FDA", terms)
        self.assertNotIn("PIND", terms)
        self.assertNotIn("MEETING", terms)

    def test_manual_wins(self):
        manual = pn._read_sources(pn.MANUAL)
        self.assertIn("GenScend", manual)
        terms = pn.harvest_from_text(
            "GenScend and BrandXCo meet.",
            exclude=manual | set(pn.STOPWORDS),
        )
        self.assertNotIn("GenScend", terms)

    def test_glossary_args_order(self):
        s = pn.glossary_args()
        parts = [p for p in s.split(",") if p]
        self.assertTrue(parts)
        self.assertTrue(parts[0].endswith("proper-nouns.csv"))


if __name__ == "__main__":
    unittest.main()
