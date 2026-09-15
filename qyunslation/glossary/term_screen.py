# SPDX-License-Identifier: MPL-2.0
"""PLAN-062b：词典优先 + 历史裁决 + LLM 裁定领域名词。"""
from __future__ import annotations

import csv
import json
import os
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from qyunslation.glossary.governance import normalize_source
from qyunslation.workbench.term_align import _parse_json_array

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = ROOT / "glossaries" / "term-candidate-rules.toml"
PROMPT_VERSION = "062-v1"
DECISION_DOMAIN = "domain_term"
DECISION_GENERIC = "generic"
DECISION_NOISE = "noise"


@dataclass(frozen=True, slots=True)
class ScreenVerdict:
    source_term: str
    decision: str
    term_type: str
    reason: str
    origin: str


def _screen_enabled() -> bool:
    return os.environ.get("QYUNSLATION_TERM_SCREEN", "1").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _load_screen_config(path: Path | None = None) -> dict[str, Any]:
    rules_path = path or DEFAULT_RULES
    data = tomllib.loads(rules_path.read_text(encoding="utf-8"))
    return data.get("screen") or {}


def _decisions_path(config: dict[str, Any]) -> Path:
    raw = str(config.get("decisions_csv") or "glossaries/term-screen-decisions.csv")
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _prompt_text(config: dict[str, Any]) -> str:
    raw = str(config.get("prompt") or "glossaries/prompts/term-screen.zh.md")
    path = Path(raw)
    prompt_path = path if path.is_absolute() else ROOT / path
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8")
    return "Reply with a JSON array of source_term, decision, term_type, reason."


def load_decision_map(path: Path | None = None) -> dict[str, ScreenVerdict]:
    config = _load_screen_config()
    store = path or _decisions_path(config)
    found: dict[str, ScreenVerdict] = {}
    if not store.is_file():
        return found
    with store.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            source = (row.get("source") or "").strip()
            decision = (row.get("decision") or "").strip()
            if not source or decision not in {DECISION_DOMAIN, DECISION_GENERIC, DECISION_NOISE}:
                continue
            found[normalize_source(source)] = ScreenVerdict(
                source_term=source,
                decision=decision,
                term_type=(row.get("term_type") or "general").strip() or "general",
                reason=(row.get("reason") or "").strip(),
                origin="decisions_csv",
            )
    return found


def append_decisions(rows: Iterable[ScreenVerdict], *, path: Path | None = None) -> None:
    config = _load_screen_config()
    store = path or _decisions_path(config)
    store.parent.mkdir(parents=True, exist_ok=True)
    exists = store.is_file()
    with store.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source", "decision", "term_type", "reason", "model", "ts", "prompt_version"],
        )
        if not exists:
            writer.writeheader()
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if row.origin != "llm":
                continue
            writer.writerow(
                {
                    "source": row.source_term,
                    "decision": row.decision,
                    "term_type": row.term_type,
                    "reason": row.reason,
                    "model": "llm",
                    "ts": now,
                    "prompt_version": PROMPT_VERSION,
                }
            )


def _termbase_hit(session: Any, source_term: str, *, tenant_id: str | None, project_id: str | None) -> bool:
    if session is None:
        return False
    from sqlalchemy import select

    from qyunslation.persist.models import Concept, ConceptTerm

    source_norm = normalize_source(source_term)
    stmt = (
        select(Concept.id)
        .join(ConceptTerm)
        .where(Concept.status == "curated")
        .where(ConceptTerm.normalized_text == source_norm)
    )
    return session.scalar(stmt) is not None


def screen_terms(
    terms: Iterable[str],
    *,
    session: Any = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    provider: Any = None,
    limit: int | None = None,
    decisions_path: Path | None = None,
    persist: bool = True,
) -> dict[str, ScreenVerdict]:
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        source = (term or "").strip()
        key = normalize_source(source)
        if not source or key in seen:
            continue
        seen.add(key)
        unique.append(source)
    if not unique:
        return {}
    config = _load_screen_config()
    history = load_decision_map(decisions_path)
    found: dict[str, ScreenVerdict] = {}
    pending: list[str] = []
    for source in unique:
        if _termbase_hit(session, source, tenant_id=tenant_id, project_id=project_id):
            found[source] = ScreenVerdict(source, DECISION_DOMAIN, "general", "curated termbase", "termbase")
            continue
        cached = history.get(normalize_source(source))
        if cached is not None:
            found[source] = cached
            continue
        pending.append(source)
    cap = int(config.get("max_per_doc") or 40) if limit is None else max(0, limit)
    overflow = pending[cap:]
    pending = pending[:cap]
    for source in overflow:
        found[source] = ScreenVerdict(source, DECISION_GENERIC, "general", "screen cap", "cap")
    if not pending or not _screen_enabled() or not bool(config.get("enable_llm", True)):
        for source in pending:
            found[source] = ScreenVerdict(source, DECISION_GENERIC, "general", "screen disabled", "disabled")
        return found
    try:
        chat = provider
        if chat is None:
            from qyunslation.gateway.provider import get_provider

            chat = get_provider()
        raw = chat.translate(json.dumps(pending, ensure_ascii=False), system=_prompt_text(config))
        parsed = {str(item.get("source_term") or "").strip(): item for item in _parse_json_array(raw)}
        minted: list[ScreenVerdict] = []
        for source in pending:
            item = parsed.get(source) or {}
            decision = str(item.get("decision") or DECISION_GENERIC).strip()
            if decision not in {DECISION_DOMAIN, DECISION_GENERIC, DECISION_NOISE}:
                decision = DECISION_GENERIC
            verdict = ScreenVerdict(
                source,
                decision,
                str(item.get("term_type") or "general").strip() or "general",
                str(item.get("reason") or "llm").strip() or "llm",
                "llm",
            )
            found[source] = verdict
            minted.append(verdict)
        if persist and minted:
            append_decisions(minted, path=decisions_path)
    except Exception:
        for source in pending:
            found.setdefault(
                source,
                ScreenVerdict(source, DECISION_GENERIC, "general", "screen unavailable", "error"),
            )
    return found
