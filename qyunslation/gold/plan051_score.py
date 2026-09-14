# SPDX-License-Identifier: MPL-2.0
"""PLAN-051b：从 run-manifest / QC 夹具聚成 Pharma-MQM 四键。"""
from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from qyunslation.gold.plan034 import evaluate_baseline_report, load_thresholds
from qyunslation.persist.concept_repo import detect_forbidden

MODE_FULL = "full-retranslate"
MODE_SKELETON = "catalog-skeleton"

CRITICAL_QC_CODES = (
    "TABLE_DIGIT_DRIFT",
    "REF_GLUED_LEAK",
)

DIGIT_CHECK_NAMES = (
    "numbers",
    "units",
    "percentages",
    "dates",
    "citations",
    "references",
)


class Plan051ScoreError(ValueError):
    """计分输入非法（如 skeleton）→ 应 FAIL。"""


def _git_head(repo: Path | None = None) -> str:
    root = repo or Path(__file__).resolve().parents[2]
    try:
        return (
            subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def reject_skeleton(report: dict[str, Any]) -> None:
    mode = str(report.get("mode") or "")
    if mode == MODE_SKELETON or mode != MODE_FULL:
        raise Plan051ScoreError(
            f"reject mode={mode!r}; require mode={MODE_FULL!r}"
        )


def collect_qc_codes_from_sidecar(paths: Sequence[str | Path]) -> list[str]:
    """从 sidecar JSON 收集 QC 码字符串。"""
    codes: list[str] = []
    for raw in paths:
        p = Path(raw)
        if not p.is_file() or ".json" not in p.name.lower():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        codes.extend(_walk_qc(data))
    return codes


def _walk_qc(node: Any) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        for key in ("object_qc", "qc_codes", "codes", "table_qc", "page_qc"):
            val = node.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        out.append(item.strip())
                    elif isinstance(item, dict):
                        c = item.get("code") or item.get("qc")
                        if isinstance(c, str) and c.strip():
                            out.append(c.strip())
        for v in node.values():
            out.extend(_walk_qc(v))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_qc(item))
    elif isinstance(node, str):
        # 裸字符串形如 TABLE_DIGIT_DRIFT:...
        if re.match(r"^[A-Z][A-Z0-9_]+", node):
            out.append(node.split(":", 1)[0])
    return out


def count_critical_qc(codes: Iterable[str]) -> int:
    n = 0
    for c in codes:
        base = (c or "").split(":", 1)[0]
        if base in CRITICAL_QC_CODES or any(
            base.startswith(x) for x in CRITICAL_QC_CODES
        ):
            n += 1
    return n


def hard_term_hit_rate(
    source: str,
    target: str,
    glossary: dict[str, str] | None = None,
) -> float:
    """原文出现的硬性术语，译文须含指定译法。"""
    if glossary is None:
        try:
            from qyunslation.glossary.governance import build_merged_dict

            glossary = build_merged_dict()
        except Exception:
            glossary = {}
    src = source or ""
    tgt = target or ""
    if not glossary:
        return 1.0
    need = 0
    hit = 0
    src_cf = src.casefold()
    for en, zh in glossary.items():
        needle = (en or "").strip()
        if len(needle) < 2:
            continue
        if needle.casefold() not in src_cf:
            continue
        need += 1
        expect = (zh or "").strip()
        if expect and expect in tgt:
            hit += 1
    if need == 0:
        return 1.0
    return hit / need


def forbidden_count(target: str, forbidden: Sequence[str] | None = None) -> int:
    if forbidden is None:
        forbidden = _default_forbidden()
    n = 0
    for hit in forbidden:
        if detect_forbidden(target, [hit]):
            n += 1
    return n


def _default_forbidden() -> list[str]:
    # 无库时尽量空列表；有 CSV forbidden 列则未来可扩
    return []


def score_entry_metrics(
    *,
    qc_codes: Sequence[str] | None = None,
    source_text: str = "",
    target_text: str = "",
    glossary: dict[str, str] | None = None,
    forbidden: Sequence[str] | None = None,
    qa_findings: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """单条 entry 的四键中间结果。"""
    codes = list(qc_codes or [])
    critical = count_critical_qc(codes)
    notes: list[str] = []

    # 034f findings
    digit_checks = 0
    digit_fail = 0
    for f in qa_findings or []:
        check = str(f.get("check") or "")
        sev = str(f.get("severity") or "")
        if check in {"doses", "numbers", "references"} and sev == "critical":
            critical += 1
        if check == "negation":
            notes.append(f"negation:{f.get('message')}")
        if check in DIGIT_CHECK_NAMES:
            digit_checks += 1
            if sev == "critical":
                digit_fail += 1
                if check not in {"doses", "numbers", "references"}:
                    # units/dates/... 也计 critical_count（PM-C4）
                    critical += 1

    if source_text or target_text:
        from qyunslation.gateway.qa import run_deterministic_qa

        qa = run_deterministic_qa(
            source_text,
            target_text,
            forbidden=list(forbidden) if forbidden else None,
        )
        for f in qa.findings:
            row = {"check": f.check, "severity": f.severity, "message": f.message}
            if f.check == "negation" and f.severity != "critical":
                notes.append(f"negation:{f.message}")
                continue
            if f.check in {"doses", "numbers", "references"} and f.severity == "critical":
                critical += 1
            if f.check in DIGIT_CHECK_NAMES:
                digit_checks += 1
                if f.severity == "critical":
                    digit_fail += 1
                    if f.check not in {"doses", "numbers", "references"}:
                        critical += 1
            if f.check == "terminology" and f.severity == "critical":
                notes.append(f"terminology:{f.message}")

    forb = forbidden_count(target_text, forbidden)
    if forb:
        critical += forb  # PM-C5

    hard = hard_term_hit_rate(source_text, target_text, glossary=glossary)
    if digit_checks == 0:
        # 无文本 QA 时：有 critical QC 则 digit rate 0，否则 1
        digit_rate = 0.0 if count_critical_qc(codes) else 1.0
    else:
        digit_rate = (digit_checks - digit_fail) / digit_checks

    return {
        "critical_count": critical,
        "forbidden_translation_count": forb,
        "hard_term_hit_rate": hard,
        "digit_unit_doi_ref_pass_rate": digit_rate,
        "notes": notes,
        "qc_codes": codes,
    }


def score_entry_from_manifest(
    man: dict[str, Any],
    *,
    source_text: str = "",
    target_text: str = "",
    glossary: dict[str, str] | None = None,
    forbidden: Sequence[str] | None = None,
) -> dict[str, Any]:
    sidecar = man.get("sidecar") or []
    if not isinstance(sidecar, list):
        sidecar = []
    codes = collect_qc_codes_from_sidecar([str(p) for p in sidecar])
    # manifest 可直接带 qc_codes 夹具
    extra = man.get("qc_codes") or []
    if isinstance(extra, list):
        codes.extend(str(c) for c in extra)
    metrics = score_entry_metrics(
        qc_codes=codes,
        source_text=source_text or str(man.get("source_text") or ""),
        target_text=target_text or str(man.get("target_text") or ""),
        glossary=glossary,
        forbidden=forbidden,
        qa_findings=man.get("qa_findings")
        if isinstance(man.get("qa_findings"), list)
        else None,
    )
    metrics["entry_id"] = man.get("entry_id")
    metrics["class"] = man.get("class")
    metrics["tags"] = list(man.get("tags") or [])
    return metrics


def aggregate_report(
    entry_metrics: Sequence[dict[str, Any]],
    *,
    model_id: str = "qwen3.6:35b-a3b",
    synthetic_ran: int = 0,
) -> dict[str, Any]:
    """只聚合 real 计分集。"""
    real = [
        m
        for m in entry_metrics
        if "real" in (m.get("tags") or []) or m.get("score_as_real")
    ]
    if not real and entry_metrics:
        # 夹具可显式 score_as_real
        real = [m for m in entry_metrics if m.get("score_as_real")]

    critical = sum(int(m.get("critical_count") or 0) for m in real)
    forbidden = sum(int(m.get("forbidden_translation_count") or 0) for m in real)
    if real:
        hard_macro = sum(float(m.get("hard_term_hit_rate") or 0.0) for m in real) / len(
            real
        )
        digit_macro = sum(
            float(m.get("digit_unit_doi_ref_pass_rate") or 0.0) for m in real
        ) / len(real)
    else:
        hard_macro = 1.0
        digit_macro = 1.0

    per_class: dict[str, int] = {"L": 0, "C": 0, "R": 0}
    for m in real:
        cls = str(m.get("class") or "").upper()
        if cls in per_class:
            per_class[cls] += 1

    report: dict[str, Any] = {
        "mode": MODE_FULL,
        "critical_count": critical,
        "forbidden_translation_count": forbidden,
        "hard_term_hit_rate": hard_macro,
        "digit_unit_doi_ref_pass_rate": digit_macro,
        "real_scored": len(real),
        "synthetic_ran": synthetic_ran,
        "per_class_real": per_class,
        "git_head": _git_head(),
        "model_id": model_id,
        "pharma_mqm": "1.0.0",
        "entries": list(entry_metrics),
        "notes": [n for m in real for n in (m.get("notes") or [])],
    }
    reject_skeleton(report)
    return report


def score_manifests(
    manifests: Sequence[dict[str, Any]],
    *,
    model_id: str = "qwen3.6:35b-a3b",
    glossary: dict[str, str] | None = None,
    forbidden: Sequence[str] | None = None,
) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    synthetic_ran = 0
    for man in manifests:
        tags = list(man.get("tags") or [])
        if "synthetic" in tags and "real" not in tags:
            synthetic_ran += 1
            # 合成不进四键，但仍记条目
            row = score_entry_from_manifest(
                man, glossary=glossary, forbidden=forbidden
            )
            row["scored"] = False
            metrics.append(row)
            continue
        row = score_entry_from_manifest(man, glossary=glossary, forbidden=forbidden)
        if "real" not in tags:
            row["score_as_real"] = True  # 夹具无 tags 时默认计分
            row["tags"] = tags or ["real"]
        row["scored"] = True
        metrics.append(row)
    return aggregate_report(
        metrics, model_id=model_id, synthetic_ran=synthetic_ran
    )


def load_manifests_from_out_root(out_root: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not out_root.is_dir():
        return found
    for path in sorted(out_root.rglob("run-manifest.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            found.append(data)
    return found


def evaluate_or_fail(report: dict[str, Any]) -> str:
    reject_skeleton(report)
    return evaluate_baseline_report(report, load_thresholds())
