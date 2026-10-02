from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
from qyunslation.pipeline.ad_termbase import build_ad_term_policy


_EVAL_PATH = Path(__file__).parents[2] / "scripts" / "plan076-ad-eval.py"
_EVAL_SPEC = importlib.util.spec_from_file_location("plan076_ad_eval", _EVAL_PATH)
assert _EVAL_SPEC and _EVAL_SPEC.loader
plan076_ad_eval = importlib.util.module_from_spec(_EVAL_SPEC)
_EVAL_SPEC.loader.exec_module(plan076_ad_eval)


def test_eval_primitives_are_source_conditioned_and_bidirectional():
    en_source = "Patients with atopic dermatitis received dupilumab 300 mg."
    en_target = "特应性皮炎患者接受了度普利尤单抗 300 mg。"
    en_policy = build_ad_term_policy(en_source, "en-zh")
    assert not run_ad_deterministic_qa(
        QaContext(en_source, en_target, "en-zh", en_policy["terms"])
    )

    zh_source = "特应性皮炎患者接受了度普利尤单抗 300 mg。"
    zh_target = "Patients with atopic dermatitis received dupilumab 300 mg."
    zh_policy = build_ad_term_policy(zh_source, "zh-en")
    assert not run_ad_deterministic_qa(
        QaContext(zh_source, zh_target, "zh-en", zh_policy["terms"])
    )


def test_eval_direction_filter_does_not_mix_rows(monkeypatch):
    monkeypatch.setattr(
        plan076_ad_eval,
        "_read_pairs",
        lambda: [
            {
                "case": "en.source.en.txt",
                "direction": "en-zh",
                "source": "Patients with atopic dermatitis received dupilumab.",
                "target": "特应性皮炎患者接受了度普利尤单抗。",
            },
            {
                "case": "zh.source.zh.txt",
                "direction": "zh-en",
                "source": "特应性皮炎患者接受了度普利尤单抗。",
                "target": "Patients with atopic dermatitis received dupilumab.",
            },
        ],
    )
    summary = plan076_ad_eval.evaluate(direction="en-zh")
    assert summary["direction"] == "en-zh"
    assert summary["cases"] == {"en-zh": 1}
    assert [row["direction"] for row in summary["rows"]] == ["en-zh"]


def test_corpus_contract_blocks_missing_manifest(tmp_path):
    result = plan076_ad_eval.check_corpus(tmp_path)
    assert result["valid"] is False
    assert result["errors"] == ["manifest_missing"]


def test_corpus_contract_validates_hashes_and_authorization(tmp_path):
    source = tmp_path / "source.en.txt"
    reference = tmp_path / "reference.zh.txt"
    annotations = tmp_path / "annotations.json"
    source.write_text("Patients with atopic dermatitis received dupilumab.", encoding="utf-8")
    reference.write_text("特应性皮炎患者接受了度普利尤单抗。", encoding="utf-8")
    annotations.write_text(json.dumps({"facts": []}), encoding="utf-8")
    manifest = {
        "cases": [{
            "case_id": "ad-en-zh-001",
            "direction": "en-zh",
            "document_profile": "医学研究文献",
            "source_ref": source.name,
            "reference_ref": reference.name,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "annotations_ref": annotations.name,
            "license": "public-or-internal-approved",
            "is_locked_test": True,
        }]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = plan076_ad_eval.check_corpus(tmp_path, direction="en-zh")
    assert result["valid"] is True
    assert result["cases"] == 1
