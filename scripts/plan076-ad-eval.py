#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-076a/h: source-conditioned AD bilingual evaluation gate.

The evaluator intentionally blocks when the required real corpus is absent. It
never fills missing targets with shared terms and never treats a source-side
English drug name as target-language evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
from qyunslation.pipeline.ad_termbase import build_ad_term_policy

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = Path(os.environ.get("PLAN076_AD_CORPUS_ROOT") or ROOT / "tests" / "gold" / "ad")
LEDGER = ROOT / "var" / "plan076-ad-eval.json"
RUNS_ROOT = ROOT / "var" / "plan076-ad-eval" / "runs"
MANIFEST_NAME = "manifest.json"
REQUIRED_CASE_FIELDS = {
    "case_id",
    "direction",
    "document_profile",
    "source_ref",
    "reference_ref",
    "source_sha256",
    "reference_sha256",
    "annotations_ref",
    "license",
    "is_locked_test",
}
ALLOWED_DIRECTIONS = {"en-zh", "zh-en"}
ALLOWED_DOCUMENT_PROFILES = {"医学研究文献", "临床研究文档"}
ANNOTATION_GROUPS = ("concepts", "facts")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_ref(root: Path, ref: object) -> Path | None:
    if not isinstance(ref, str) or not ref.strip():
        return None
    candidate = (root / ref).resolve()
    if root.resolve() not in candidate.parents:
        return None
    return candidate


def _annotation_errors(annotations: object, prefix: str) -> list[str]:
    if not isinstance(annotations, dict):
        return [f"{prefix}:annotations_not_object"]
    errors: list[str] = []
    total = 0
    for group in ANNOTATION_GROUPS:
        items = annotations.get(group, [])
        if not isinstance(items, list):
            errors.append(f"{prefix}:{group}_not_list")
            continue
        for index, item in enumerate(items):
            item_prefix = f"{prefix}:{group}[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{item_prefix}:not_object")
                continue
            total += 1
            if not str(item.get("source_span") or "").strip():
                errors.append(f"{item_prefix}:source_span")
            targets = item.get("target_terms") or item.get("allowed_aliases")
            if isinstance(targets, str):
                targets = [targets]
            if not isinstance(targets, list) or not any(str(value).strip() for value in targets):
                errors.append(f"{item_prefix}:target_terms")
            if str(item.get("criticality") or "").strip() not in {"high", "medium", "low"}:
                errors.append(f"{item_prefix}:criticality")
    if total == 0:
        errors.append(f"{prefix}:annotations_empty")
    return errors


def check_corpus(corpus_root: Path = CORPUS_ROOT, *, direction: str = "both") -> dict:
    """Validate the manifest without exposing source, reference, or annotation text."""
    root = Path(corpus_root)
    manifest_path = root / MANIFEST_NAME
    errors: list[str] = []
    rows: list[dict] = []
    if not manifest_path.is_file():
        return {
            "valid": False,
            "manifest": False,
            "cases": 0,
            "errors": ["manifest_missing"],
            "rows": rows,
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "valid": False,
            "manifest": True,
            "cases": 0,
            "errors": ["manifest_invalid_json"],
            "rows": rows,
        }
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, list):
        return {
            "valid": False,
            "manifest": True,
            "cases": 0,
            "errors": ["cases_not_list"],
            "rows": rows,
        }
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"case[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix}:not_object")
            continue
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            errors.append(f"{prefix}:missing:{','.join(missing)}")
            continue
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in seen_ids:
            errors.append(f"{prefix}:duplicate_or_empty_case_id")
        seen_ids.add(case_id)
        item_direction = str(case.get("direction") or "")
        if item_direction not in ALLOWED_DIRECTIONS:
            errors.append(f"{prefix}:direction")
        if str(case.get("document_profile") or "") not in ALLOWED_DOCUMENT_PROFILES:
            errors.append(f"{prefix}:document_profile")
        if str(case.get("license") or "") != "public-or-internal-approved":
            errors.append(f"{prefix}:license")
        if case.get("is_locked_test") is not True:
            errors.append(f"{prefix}:not_locked_test")
        source_path = _safe_ref(root, case.get("source_ref"))
        reference_path = _safe_ref(root, case.get("reference_ref"))
        annotation_path = _safe_ref(root, case.get("annotations_ref"))
        if not source_path or not source_path.is_file():
            errors.append(f"{prefix}:source_missing_or_unsafe")
        if not reference_path or not reference_path.is_file():
            errors.append(f"{prefix}:reference_missing_or_unsafe")
        if not annotation_path or not annotation_path.is_file():
            errors.append(f"{prefix}:annotations_missing_or_unsafe")
        if source_path and source_path.is_file() and str(case.get("source_sha256")) != _sha256(source_path):
            errors.append(f"{prefix}:source_hash")
        if reference_path and reference_path.is_file() and str(case.get("reference_sha256")) != _sha256(reference_path):
            errors.append(f"{prefix}:reference_hash")
        if annotation_path and annotation_path.is_file():
            try:
                annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
                errors.extend(_annotation_errors(annotations, prefix))
            except (OSError, UnicodeError, json.JSONDecodeError):
                errors.append(f"{prefix}:annotations_invalid_json")
        if item_direction == direction or direction == "both":
            rows.append({"case_id": case_id, "direction": item_direction})
    return {
        "valid": not errors,
        "manifest": True,
        "cases": len(rows),
        "errors": sorted(set(errors)),
        "rows": rows,
    }


def _read_pairs() -> list[dict]:
    rows: list[dict] = []
    manifest_path = CORPUS_ROOT / MANIFEST_NAME
    if not manifest_path.is_file():
        return rows
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return rows
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, list):
        return rows
    for case in cases:
        if not isinstance(case, dict) or case.get("is_locked_test") is not True:
            continue
        direction = case.get("direction")
        if direction not in ALLOWED_DIRECTIONS:
            continue
        source_path = _safe_ref(CORPUS_ROOT, case.get("source_ref"))
        target_path = _safe_ref(CORPUS_ROOT, case.get("reference_ref"))
        if not source_path or not target_path or not source_path.is_file() or not target_path.is_file():
            continue
        try:
            source = source_path.read_text(encoding="utf-8")
            target = target_path.read_text(encoding="utf-8")
            annotation_path = _safe_ref(CORPUS_ROOT, case.get("annotations_ref"))
            annotations = {}
            if annotation_path and annotation_path.is_file():
                loaded = json.loads(annotation_path.read_text(encoding="utf-8"))
                annotations = loaded if isinstance(loaded, dict) else {}
        except (OSError, UnicodeError):
            continue
        except (json.JSONDecodeError, TypeError):
            continue
        rows.append(
            {
                "case": str(case.get("case_id") or source_path.name),
                "direction": direction,
                "document_profile": str(case.get("document_profile") or "医学研究文献"),
                "source": source,
                "target": target,
                "annotations": annotations,
            }
        )
    return rows


class ModelRunnerError(RuntimeError):
    """A model-backed evaluation run cannot produce trustworthy output."""


class OpenAICompatibleRunner:
    """Small, auditable runner for the configured translation gateway.

    The evaluator never inherits arbitrary application prompts or credentials;
    callers provide the endpoint/model explicitly or through the documented
    DOCUTRANSLATE/QYUNSLATION environment variables.
    """

    def __init__(self, *, base_url: str, model: str, api_key: str, temperature: float, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or "ollama"
        self.temperature = temperature
        self.timeout = timeout

    def translate(self, source: str, *, system: str) -> tuple[str, dict]:
        if not source.strip():
            raise ModelRunnerError("empty_source")
        url = f"{self.base_url}/chat/completions"
        if not self.base_url.endswith("/v1"):
            url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": source},
            ],
            "temperature": self.temperature,
        }
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelRunnerError(f"model_request_failed:{type(exc).__name__}") from exc
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ModelRunnerError("model_response_missing_choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ModelRunnerError("model_response_missing_content")
        usage = data.get("usage") if isinstance(data, dict) else {}
        return content.strip(), {
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "usage": usage if isinstance(usage, dict) else {},
        }


def _prompt_for_row(row: dict, mode: str) -> dict[str, str]:
    from qyunslation.pipeline.ad_prompt import PromptContext, compile_prompt

    domain = "ad" if mode == "candidate" else "general"
    document_profile = row.get("document_profile") or "医学研究文献"
    if domain == "general":
        document_profile = "通用医药文档"
    compiled = compile_prompt(
        PromptContext(domain, row["direction"], document_profile, "translate")
    )
    return compiled.snapshot()


def _safe_case_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:120] or "case"


def _is_internal_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = (parsed.hostname or "").strip().casefold()
    if not host:
        return False
    if host in {"localhost", "internal-gateway"} or host.endswith((".internal", ".local")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not address.is_global


def _new_run_dir(mode: str) -> tuple[str, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{mode}-{uuid4().hex[:10]}"
    path = RUNS_ROOT / run_id
    path.mkdir(parents=True, exist_ok=False)
    return run_id, path


def _target_contains(text: str, term: str) -> bool:
    value = str(term or "").strip()
    if not value:
        return False
    if any(ord(char) > 127 for char in value):
        return value in text
    return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])", text, re.I))


def _machine_metrics(row: dict, machine_text: str, findings: list) -> dict:
    annotations = row.get("annotations") if isinstance(row.get("annotations"), dict) else {}
    concepts = annotations.get("concepts") if isinstance(annotations.get("concepts"), list) else []
    facts = annotations.get("facts") if isinstance(annotations.get("facts"), list) else []

    def recall(items: list[dict]) -> tuple[float, int, int]:
        applicable = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source_span = str(item.get("source_span") or "").strip()
            if not source_span or source_span not in row["source"]:
                continue
            aliases = item.get("target_terms") or item.get("allowed_aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            aliases = [str(alias).strip() for alias in aliases if str(alias).strip()]
            applicable.append(aliases)
        hits = sum(1 for aliases in applicable if any(_target_contains(machine_text, alias) for alias in aliases))
        return (hits / len(applicable) if applicable else 1.0, hits, len(applicable))

    term_recall, term_hits, term_total = recall(concepts)
    fact_recall, fact_hits, fact_total = recall(facts)
    source_units = max(1, len([line for line in row["source"].splitlines() if line.strip()]))
    target_units = len([line for line in machine_text.splitlines() if line.strip()])
    completeness = 1.0 if machine_text.strip() and target_units >= 1 else 0.0
    structure = 1.0 if target_units == source_units else (0.5 if target_units else 0.0)
    score = round(
        term_recall * 0.35 + fact_recall * 0.35 + completeness * 0.20 + structure * 0.10,
        4,
    )
    return {
        "term_recall": round(term_recall, 4),
        "term_hits": term_hits,
        "term_total": term_total,
        "fact_recall": round(fact_recall, 4),
        "fact_hits": fact_hits,
        "fact_total": fact_total,
        "completeness": completeness,
        "structure": structure,
        "score": score,
        "qa_blockers": sum(item.severity == "blocker" for item in findings),
    }


def compare_model_runs(model_runs: list[dict]) -> dict:
    by_mode = {str(item.get("mode")): item for item in model_runs}
    baseline = by_mode.get("baseline")
    candidate = by_mode.get("candidate")
    if not baseline or not candidate:
        return {"status": "BLOCKED", "errors": ["baseline_or_candidate_missing"]}
    if baseline.get("status") != "PASS" or candidate.get("status") != "PASS":
        return {"status": "BLOCKED", "errors": ["model_run_incomplete"]}
    baseline_rows = {str(row.get("case")): row for row in baseline.get("rows", [])}
    candidate_rows = {str(row.get("case")): row for row in candidate.get("rows", [])}
    case_ids = sorted(set(baseline_rows) & set(candidate_rows))
    if not case_ids or set(baseline_rows) != set(candidate_rows):
        return {"status": "BLOCKED", "errors": ["baseline_candidate_case_mismatch"]}
    baseline_score = sum(float(baseline_rows[key]["metrics"]["score"]) for key in case_ids) / len(case_ids)
    candidate_score = sum(float(candidate_rows[key]["metrics"]["score"]) for key in case_ids) / len(case_ids)
    baseline_blockers = sum(int(baseline_rows[key].get("qa_blockers") or 0) for key in case_ids)
    candidate_blockers = sum(int(candidate_rows[key].get("qa_blockers") or 0) for key in case_ids)
    delta = round(candidate_score - baseline_score, 4)
    status = "PASS" if delta >= 0.10 and candidate_blockers <= baseline_blockers else "FAIL"
    return {
        "status": status,
        "cases": len(case_ids),
        "baseline_score": round(baseline_score, 4),
        "candidate_score": round(candidate_score, 4),
        "score_delta": delta,
        "baseline_qa_blockers": baseline_blockers,
        "candidate_qa_blockers": candidate_blockers,
        "required_score_delta": 0.10,
    }


def run_model_cases(
    rows: list[dict],
    *,
    mode: str,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    temperature: float,
    timeout: float,
    allow_external_endpoint: bool = False,
) -> dict:
    """Run one immutable baseline/candidate set without printing source text."""
    endpoint = (base_url or os.environ.get("QYUNSLATION_BASE_URL") or os.environ.get("DOCUTRANSLATE_BASE_URL") or "").strip()
    model_id = (model or os.environ.get("QYUNSLATION_MODEL_ID") or os.environ.get("DOCUTRANSLATE_MODEL_ID") or "").strip()
    token = api_key or os.environ.get("QYUNSLATION_API_KEY") or os.environ.get("DOCUTRANSLATE_API_KEY") or "ollama"
    if not endpoint:
        return {"status": "BLOCKED", "mode": mode, "errors": ["model_endpoint_missing"]}
    if not model_id:
        return {"status": "BLOCKED", "mode": mode, "errors": ["model_id_missing"]}
    if not allow_external_endpoint and not _is_internal_endpoint(endpoint):
        return {"status": "BLOCKED", "mode": mode, "errors": ["endpoint_external"]}
    run_id, run_dir = _new_run_dir(mode)
    output_dir = run_dir / "machine"
    output_dir.mkdir()
    runner = OpenAICompatibleRunner(
        base_url=endpoint,
        model=model_id,
        api_key=token,
        temperature=temperature,
        timeout=timeout,
    )
    rows_out: list[dict] = []
    errors: list[str] = []
    for row in rows:
        case_id = str(row["case"])
        prompt_snapshot = _prompt_for_row(row, mode)
        try:
            machine_text, run_meta = runner.translate(row["source"], system=_compiled_text_for_row(row, mode))
            output_path = output_dir / f"{_safe_case_name(case_id)}.txt"
            output_path.write_text(machine_text + "\n", encoding="utf-8")
            policy = build_ad_term_policy(row["source"], row["direction"])
            findings = run_ad_deterministic_qa(
                QaContext(row["source"], machine_text, row["direction"], policy["terms"])
            )
            metrics = _machine_metrics(row, machine_text, findings)
            rows_out.append(
                {
                    "case": case_id,
                    "direction": row["direction"],
                    "output_ref": str(output_path.relative_to(run_dir)),
                    "output_sha256": _sha256(output_path),
                    "prompt_snapshot": prompt_snapshot,
                    "qa_blockers": metrics["qa_blockers"],
                    "qa_codes": sorted({item.code for item in findings}),
                    "metrics": metrics,
                    **run_meta,
                }
            )
        except ModelRunnerError as exc:
            errors.append(f"{case_id}:{exc}")
    qa_blockers = sum(int(row.get("qa_blockers") or 0) for row in rows_out)
    status = "BLOCKED" if errors or len(rows_out) != len(rows) else ("FAIL" if qa_blockers else "PASS")
    summary = {
        "schema": "plan076-ad-model-run/v1",
        "status": status,
        "run_id": run_id,
        "mode": mode,
        "model": model_id,
        "endpoint": endpoint,
        "temperature": temperature,
        "timeout": timeout,
        "cases": len(rows_out),
        "qa_blockers": qa_blockers,
        "errors": errors,
        "rows": rows_out,
        "run_dir": str(run_dir),
    }
    (run_dir / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _compiled_text_for_row(row: dict, mode: str) -> str:
    from qyunslation.pipeline.ad_prompt import PromptContext, compile_prompt

    domain = "ad" if mode == "candidate" else "general"
    document = row.get("document_profile") if domain == "ad" else "通用医药文档"
    return compile_prompt(PromptContext(domain, row["direction"], document or "医学研究文献", "translate")).text


def evaluate(*, baseline: str = "generic", candidate: str = "ad-v1", direction: str = "both") -> dict:
    rows = _read_pairs()
    if direction != "both":
        rows = [row for row in rows if row["direction"] == direction]
    directions = ("en-zh", "zh-en") if direction == "both" else (direction,)
    by_direction = {
        item_direction: [row for row in rows if row["direction"] == item_direction]
        for item_direction in directions
    }
    scored: list[dict] = []
    for row in rows:
        policy = build_ad_term_policy(row["source"], row["direction"])
        findings = run_ad_deterministic_qa(
            QaContext(row["source"], row["target"], row["direction"], policy["terms"])
        )
        scored.append(
            {
                "case": row["case"],
                "direction": row["direction"],
                "source_chars": len(row["source"]),
                "term_count": len(policy["terms"]),
                "qa_blockers": sum(item.severity == "blocker" for item in findings),
                "qa_codes": sorted({item.code for item in findings}),
            }
        )
    thresholds = {
        "min_cases_per_direction": 12,
        "min_source_chars_per_direction": 20_000,
        "min_challenge_segments_per_direction": 100,
    }
    # A challenge segment is a source pair containing at least one protected
    # AD marker, number, negation or modality; it is counted per direction.
    challenges = {
        direction: sum(1 for row in rows if row["direction"] == direction and build_ad_term_policy(row["source"], direction)["terms"])
        for direction in by_direction
    }
    summary = {
        "schema": "plan076-ad-eval/v1",
        "baseline": baseline,
        "candidate": candidate,
        "direction": direction,
        "thresholds": thresholds,
        "cases": {direction: len(items) for direction, items in by_direction.items()},
        "source_chars": {direction: sum(len(item["source"]) for item in items) for direction, items in by_direction.items()},
        "challenge_segments": challenges,
        "qa_blockers": sum(item["qa_blockers"] for item in scored),
        "rows": scored,
    }
    deficits = []
    for direction in by_direction:
        if summary["cases"][direction] < thresholds["min_cases_per_direction"]:
            deficits.append(f"{direction}: cases")
        if summary["source_chars"][direction] < thresholds["min_source_chars_per_direction"]:
            deficits.append(f"{direction}: source_chars")
        if summary["challenge_segments"][direction] < thresholds["min_challenge_segments_per_direction"]:
            deficits.append(f"{direction}: challenge_segments")
    summary["deficits"] = deficits
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", choices=("en-zh", "zh-en", "both"), default="both")
    parser.add_argument("--baseline", default="generic")
    parser.add_argument("--candidate", default="ad-v1")
    parser.add_argument("--check-corpus", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--run-model", choices=("baseline", "candidate", "both"))
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--allow-external-endpoint", action="store_true")
    args = parser.parse_args()
    corpus_check = check_corpus(direction=args.direction)
    if args.check_corpus:
        corpus_check["direction"] = args.direction
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps({"schema": "plan076-ad-corpus-check/v1", **corpus_check}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(corpus_check, ensure_ascii=False, indent=2))
        if not corpus_check["valid"]:
            print("BLOCKED: AD corpus manifest contract incomplete: " + ", ".join(corpus_check["errors"]))
            return 2
        return 0
    summary = evaluate(baseline=args.baseline, candidate=args.candidate, direction=args.direction)
    summary["corpus_contract"] = corpus_check
    if not corpus_check["valid"]:
        summary["deficits"].append("corpus_contract")
    run_model = args.run_model or ("baseline" if args.baseline_only else None)
    if run_model:
        modes = ("baseline", "candidate") if run_model == "both" else (run_model,)
        model_runs = []
        rows = _read_pairs()
        if args.direction != "both":
            rows = [row for row in rows if row["direction"] == args.direction]
        for mode in modes:
            if not corpus_check["valid"] or summary["deficits"]:
                model_runs.append({"status": "BLOCKED", "mode": mode, "errors": ["corpus_gate_incomplete"]})
            else:
                model_runs.append(
                    run_model_cases(
                        rows,
                        mode=mode,
                        base_url=args.base_url,
                        model=args.model,
                        api_key=None,
                        temperature=args.temperature,
                        timeout=args.timeout,
                        allow_external_endpoint=args.allow_external_endpoint,
                    )
                )
        summary["model_runs"] = model_runs
        summary["mode"] = "model-run"
        if any(item.get("status") == "BLOCKED" for item in model_runs):
            summary["deficits"].append("model_run")
        if any(item.get("status") == "FAIL" for item in model_runs):
            summary.setdefault("failures", []).append("model_run")
        if run_model == "both":
            comparison = compare_model_runs(model_runs)
            summary["comparison"] = comparison
            if comparison.get("status") == "BLOCKED":
                summary["deficits"].append("model_comparison")
            elif comparison.get("status") == "FAIL":
                summary.setdefault("failures", []).append("model_comparison")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["deficits"]:
        print("BLOCKED: missing real AD bilingual evaluation corpus: " + ", ".join(summary["deficits"]))
        return 2
    if summary.get("failures") or summary["qa_blockers"]:
        print("FAIL: AD deterministic QA blockers present")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
