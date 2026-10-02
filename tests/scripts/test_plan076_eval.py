from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
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
    annotations.write_text(
        json.dumps({
            "facts": [{
                "fact_id": "dose-1",
                "type": "dose",
                "source_span": "300 mg",
                "target_terms": ["300 mg"],
                "criticality": "high",
            }]
        }),
        encoding="utf-8",
    )
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


def test_baseline_only_is_fail_closed_until_model_runner_exists(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(plan076_ad_eval, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["plan076-ad-eval.py", "--baseline-only"])
    assert plan076_ad_eval.main() == 2
    output = capsys.readouterr().out
    assert '"model_run"' in output
    assert "corpus_contract" in output


def test_read_pairs_uses_locked_manifest_cases_only(monkeypatch, tmp_path):
    registered_source = tmp_path / "registered.source.en.txt"
    registered_target = tmp_path / "registered.target.zh.txt"
    orphan_source = tmp_path / "orphan.source.en.txt"
    orphan_target = tmp_path / "orphan.target.zh.txt"
    registered_source.write_text("Patients with atopic dermatitis.", encoding="utf-8")
    registered_target.write_text("特应性皮炎患者。", encoding="utf-8")
    orphan_source.write_text("Unregistered source.", encoding="utf-8")
    orphan_target.write_text("未登记文本。", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({
            "cases": [{
                "case_id": "registered-001",
                "direction": "en-zh",
                "source_ref": registered_source.name,
                "reference_ref": registered_target.name,
                "is_locked_test": True,
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(plan076_ad_eval, "CORPUS_ROOT", tmp_path)
    rows = plan076_ad_eval._read_pairs()
    assert [row["case"] for row in rows] == ["registered-001"]


def test_model_runner_blocks_without_explicit_endpoint_or_model(monkeypatch):
    for key in (
        "QYUNSLATION_BASE_URL",
        "DOCUTRANSLATE_BASE_URL",
        "QYUNSLATION_MODEL_ID",
        "DOCUTRANSLATE_MODEL_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    result = plan076_ad_eval.run_model_cases(
        [{"case": "case-1", "direction": "en-zh", "document_profile": "医学研究文献", "source": "source", "target": "target"}],
        mode="baseline",
        base_url=None,
        model=None,
        api_key=None,
        temperature=0.0,
        timeout=1.0,
    )
    assert result == {"status": "BLOCKED", "mode": "baseline", "errors": ["model_endpoint_missing"]}


def test_model_runner_writes_immutable_machine_output(monkeypatch, tmp_path):
    class FakeRunner:
        def __init__(self, **_kwargs):
            pass

        def translate(self, source, *, system):
            assert source == "source"
            assert "English" in system
            return "machine output", {"latency_ms": 1.0, "usage": {"total_tokens": 3}}

    monkeypatch.setattr(plan076_ad_eval, "OpenAICompatibleRunner", FakeRunner)
    monkeypatch.setattr(plan076_ad_eval, "RUNS_ROOT", tmp_path)
    result = plan076_ad_eval.run_model_cases(
        [{"case": "case-1", "direction": "en-zh", "document_profile": "医学研究文献", "source": "source", "target": "target"}],
        mode="baseline",
        base_url="http://127.0.0.1:11434/v1",
        model="test-model",
        api_key="test-key",
        temperature=0.0,
        timeout=1.0,
    )
    assert result["status"] == "PASS"
    assert result["cases"] == 1
    assert result["rows"][0]["metrics"]["score"] == 1.0
    report = Path(result["run_dir"]) / "report.json"
    assert report.is_file()
    assert "machine output" not in report.read_text(encoding="utf-8")
    output_path = Path(result["run_dir"]) / result["rows"][0]["output_ref"]
    assert output_path.read_text(encoding="utf-8").strip() == "machine output"


def test_model_runner_blocks_external_endpoint_by_default():
    result = plan076_ad_eval.run_model_cases(
        [{"case": "case-1", "direction": "en-zh", "document_profile": "医学研究文献", "source": "source", "target": "target"}],
        mode="baseline",
        base_url="https://api.example.com/v1",
        model="test-model",
        api_key="test-key",
        temperature=0.0,
        timeout=1.0,
    )
    assert result == {"status": "BLOCKED", "mode": "baseline", "errors": ["endpoint_external"]}


def test_display_endpoint_strips_embedded_credentials():
    assert plan076_ad_eval._display_endpoint("https://user:password@example.com/v1") == "https://example.com/v1"


def test_expert_review_gate_computes_kappa_and_preference():
    source_units = {f"case-{index}": 100 for index in range(20)}
    document = {
        "schema": "plan076-expert-review/v1",
        "cases": [
            {
                "case_id": case_id,
                "reviewers": [
                    {"reviewer_role": "ad_medical", "blind_choice": "candidate", "severity": "none", "categories": []},
                    {"reviewer_role": "medical_translation", "blind_choice": "candidate", "severity": "none", "categories": []},
                ],
                "adjudicated": {"severity": "none", "categories": []},
            }
            for case_id in source_units
        ],
    }
    result = plan076_ad_eval.assess_expert_review(
        document,
        source_units,
        expected_case_ids=set(source_units),
    )
    assert result["status"] == "PASS"
    assert result["kappa"] == 1.0
    assert result["candidate_preference"] == 1.0


def test_expert_review_gate_blocks_missing_roles_and_fails_critical():
    source_units = {"case-1": 1000}
    document = {
        "cases": [{
            "case_id": "case-1",
            "reviewers": [
                {"reviewer_role": "ad_medical", "blind_choice": "candidate", "severity": "critical", "categories": ["fact"]},
                {"reviewer_role": "medical_translation", "blind_choice": "candidate", "severity": "critical", "categories": ["fact"]},
            ],
            "adjudicated": {"severity": "critical", "categories": ["fact"]},
        }],
    }
    result = plan076_ad_eval.assess_expert_review(document, source_units, min_cases=1)
    assert result["status"] == "FAIL"
    assert result["critical"] == 1

    result = plan076_ad_eval.assess_expert_review({"cases": []}, source_units, min_cases=1)
    assert result["status"] == "BLOCKED"


def test_expert_review_gate_rejects_model_or_source_fields():
    result = plan076_ad_eval.assess_expert_review(
        {"model": "secret-model", "cases": []},
        {},
        min_cases=0,
    )
    assert result == {"status": "BLOCKED", "errors": ["review_contains_sensitive_fields"]}


def test_pilot_gate_requires_four_cells_and_performance_budget():
    tasks = []
    cells = [
        ("en-zh", "医学研究文献"),
        ("en-zh", "临床研究文档"),
        ("zh-en", "医学研究文献"),
        ("zh-en", "临床研究文档"),
    ]
    for direction, profile in cells:
        for index in range(5):
            tasks.append({
                "task_id": f"{direction}-{profile}-{index}",
                "direction": direction,
                "document_profile": profile,
                "status": "approved",
                "prompt_digest": f"prompt-{direction}-{profile}",
                "termbase_version": f"terms-{direction}-{profile}",
                "latency_ms": 110,
                "tokens": 110,
                "high_risk_fact_errors": 0,
                "drug_drift": 0,
            })
    result = plan076_ad_eval.assess_pilot_report(
        {"baseline": {"p95_latency_ms": 100, "p95_tokens": 100}, "tasks": tasks}
    )
    assert result["status"] == "PASS"
    assert result["latency_ratio"] == 1.1

    tasks[0]["drug_drift"] = 1
    result = plan076_ad_eval.assess_pilot_report(
        {"baseline": {"p95_latency_ms": 100, "p95_tokens": 100}, "tasks": tasks}
    )
    assert result["status"] == "FAIL"

    result = plan076_ad_eval.assess_pilot_report({"tasks": []})
    assert result["status"] == "BLOCKED"


def test_model_comparison_requires_ten_point_gain_without_new_blockers():
    baseline_row = {"case": "case-1", "metrics": {"score": 0.80}, "qa_blockers": 1}
    candidate_row = {"case": "case-1", "metrics": {"score": 0.91}, "qa_blockers": 0}
    result = plan076_ad_eval.compare_model_runs([
        {"mode": "baseline", "status": "PASS", "rows": [baseline_row]},
        {"mode": "candidate", "status": "PASS", "rows": [candidate_row]},
    ])
    assert result["status"] == "PASS"
    assert result["score_delta"] == 0.11

    candidate_row["metrics"]["score"] = 0.89
    result = plan076_ad_eval.compare_model_runs([
        {"mode": "baseline", "status": "PASS", "rows": [baseline_row]},
        {"mode": "candidate", "status": "PASS", "rows": [candidate_row]},
    ])
    assert result["status"] == "FAIL"
