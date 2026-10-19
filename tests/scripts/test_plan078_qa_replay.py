"""PLAN-078b b9: the replay tool triages hits, runs controls, and prints only aggregates."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan078-qa-replay.py"
SENTINEL = "SENTINELPROSE"


def _load():
    spec = importlib.util.spec_from_file_location("plan078_replay", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def corpus(tmp_path):
    pairs = {
        "c1": (  # translation drops the dose entirely
            f"{SENTINEL} Patients received 300 mg once. Response was 45.2% at week 16.",
            f"{SENTINEL} 患者接受一次治疗。应答率为45.2%。",
        ),
        "c2": (  # equivalent writing: must not be a hit
            f"{SENTINEL} Patients received 300 mg once. Response was 45.2% at week 16.",
            f"{SENTINEL} 患者接受 300 毫克。应答率为45.2%。",
        ),
    }
    cases = []
    for case_id, (source, target) in pairs.items():
        (tmp_path / f"{case_id}.source.txt").write_text(source, encoding="utf-8")
        (tmp_path / f"{case_id}.reference.txt").write_text(target, encoding="utf-8")
        cases.append(
            {"case_id": case_id, "direction": "en-zh", "source_ref": f"{case_id}.source.txt", "reference_ref": f"{case_id}.reference.txt"}
        )
    (tmp_path / "manifest.json").write_text(json.dumps({"schema": "x", "cases": cases}), encoding="utf-8")
    return tmp_path


def test_number_classification_separates_format_from_real_loss():
    module = _load()
    assert module.classify_number("300mg", "接受 300 毫克") == "equivalent_unit_present"
    assert module.classify_number("300mg", "接受了治疗") == "absent"
    assert module.classify_number("300mg", "剂量为 300 毫升") == "present_with_other_unit"
    assert module.classify_number("45.2%", "应答率 45.2，无单位") in {"present_elsewhere", "present_with_other_unit"}
    assert module.classify_frequency("Q2W", "每2周一次") == "localised_equivalent_present"
    assert module.classify_frequency("Q2W", "不再给药") == "absent"


def test_replay_reports_hits_coverage_and_controls(corpus, capsys):
    module = _load()
    assert module.main(["--corpus", str(corpus), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["cases"] == 2
    codes = {row["code"]: row for row in report["rules"]}
    assert codes["LITERAL_MISSING_DOSE"]["cases_hit"] == 1  # only the translation that dropped the dose
    assert report["triage"]["LITERAL_MISSING_DOSE"] == {"absent": 1}
    assert report["coverage"]["with_dose_literals"] == 2
    assert "AD_NUMBER_DRIFT/omitted_line" in report["controls"]


def test_output_never_contains_document_prose(corpus, capsys):
    module = _load()
    module.main(["--corpus", str(corpus)])
    text_output = capsys.readouterr().out
    module.main(["--corpus", str(corpus), "--json"])
    json_output = capsys.readouterr().out
    assert SENTINEL not in text_output and SENTINEL not in json_output


def test_missing_corpus_is_blocked_not_silently_empty(tmp_path, capsys):
    module = _load()
    assert module.main(["--corpus", str(tmp_path)]) == 2
    assert "BLOCKED" in capsys.readouterr().err
