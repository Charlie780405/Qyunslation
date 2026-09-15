# SPDX-License-Identifier: MPL-2.0
"""PLAN-063a：从裁决与裁定记录归纳规则提案。"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.glossary.candidate_rules import load_rules, rules_fingerprint, rules_version
from qyunslation.glossary.governance import normalize_source
from qyunslation.glossary.term_screen import DECISION_DOMAIN, screen_terms
from qyunslation.persist.models import Concept, ConceptTerm, DocumentTermCandidate, TermDecision

ROOT = Path(__file__).resolve().parents[2]
KEEP_LIST = frozenset(
    {
        normalize_source("tralokinumab"),
        normalize_source("IL-13"),
        normalize_source("NHS"),
        normalize_source("EASI"),
        normalize_source("BSA"),
        normalize_source("ABC-101"),
    }
)
INBOX = ROOT / ".cursor/skills/skill-registry/term-rules-inbox.md"
VERSIONS = ROOT / ".cursor/skills/skill-registry/term-rules-versions.md"
EXCLUSIONS = ROOT / "glossaries/term-exclusions.csv"
TOML = ROOT / "glossaries/term-candidate-rules.toml"
SCREEN_CSV = ROOT / "glossaries/term-screen-decisions.csv"
STAGING = ROOT / "glossaries/staging/plan063-promote.csv"
PREFIX_RE = re.compile(r"^(anti|non|pre)-(.+)$", re.I)
SUFFIX_RE = re.compile(r"^(.+)-(50|75|90)$", re.I)
MACHINE_PREFIXES = ("plan062-purge", "machine_")


def _is_machine(actor: str) -> bool:
    raw = (actor or "").strip()
    return raw.startswith(MACHINE_PREFIXES)


def _kills_keep(pattern: str) -> str | None:
    compiled = re.compile(pattern, re.I)
    for item in KEEP_LIST:
        if compiled.fullmatch(item) or compiled.search(item):
            return item
    return None


def _next_prop_id(inbox_text: str) -> str:
    found = [int(m.group(1)) for m in re.finditer(r"PROP-(\d+)", inbox_text)]
    return f"PROP-{max(found, default=0) + 1:03d}"


def collect_reject_rows(session: Session) -> list[dict[str, Any]]:
    stmt = (
        select(TermDecision, DocumentTermCandidate)
        .join(DocumentTermCandidate, TermDecision.candidate_id == DocumentTermCandidate.id)
        .where(TermDecision.action.in_(("reject", "do_not_translate")))
    )
    rows: list[dict[str, Any]] = []
    for decision, candidate in session.execute(stmt):
        rows.append(
            {
                "source_term": decision.source_term,
                "source_norm": candidate.source_norm,
                "job_id": candidate.job_id,
                "actor_sub": decision.actor_sub,
                "machine": _is_machine(decision.actor_sub),
                "action": decision.action,
            }
        )
    return rows


def propose_denylist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["source_norm"]].append(row)
    proposals: list[dict[str, Any]] = []
    for source_norm, items in grouped.items():
        if source_norm in KEEP_LIST:
            continue
        jobs = {item["job_id"] for item in items}
        humans = [item for item in items if not item["machine"]]
        if not humans and len(jobs) < 2:
            continue
        if len(items) < 3 or len(jobs) < 2:
            continue
        proposals.append(
            {
                "type": "denylist",
                "source": items[0]["source_term"],
                "reason": f"rejected {len(items)} times across {len(jobs)} jobs",
            }
        )
    return proposals


def propose_regex(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    norms = sorted({row["source_norm"] for row in rows if row["source_norm"] not in KEEP_LIST})
    if len(norms) < 3:
        return []
    suffix = Counter()
    for item in norms:
        if "-" in item:
            suffix[item.rsplit("-", 1)[-1]] += 1
    proposals: list[dict[str, Any]] = []
    for token, count in suffix.items():
        if count < 3 or len(token) < 3:
            continue
        pattern = rf"^[A-Za-z0-9]+-{re.escape(token)}$"
        killed = _kills_keep(pattern)
        if killed:
            proposals.append(
                {
                    "type": "exclude_regex",
                    "source": pattern,
                    "reason": f"discarded: kills keep list item {killed}",
                    "discarded": True,
                }
            )
            continue
        proposals.append(
            {
                "type": "exclude_regex",
                "source": pattern,
                "reason": f"{count} rejected terms share -{token}",
            }
        )
    return proposals


def propose_curated(session: Session) -> list[dict[str, Any]]:
    if not SCREEN_CSV.is_file():
        return []
    counts: Counter[str] = Counter()
    samples: dict[str, str] = {}
    with SCREEN_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip() != DECISION_DOMAIN:
                continue
            source = (row.get("source") or "").strip()
            if not source:
                continue
            key = normalize_source(source)
            counts[key] += 1
            samples[key] = source
    curated = {
        row[0]
        for row in session.execute(
            select(ConceptTerm.normalized_text)
            .join(Concept)
            .where(Concept.status == "curated")
        )
    }
    proposals: list[dict[str, Any]] = []
    for key, count in counts.items():
        if count < 2 or key in curated or key in KEEP_LIST:
            continue
        proposals.append(
            {
                "type": "curated",
                "source": samples[key],
                "reason": f"domain_term {count} times, not curated",
            }
        )
    return proposals


def propose_aliases(session: Session) -> list[dict[str, Any]]:
    curated = {
        row[0]: row[1]
        for row in session.execute(
            select(ConceptTerm.normalized_text, Concept.id)
            .join(Concept)
            .where(Concept.status == "curated")
        )
    }
    pending = session.scalars(
        select(DocumentTermCandidate).where(
            DocumentTermCandidate.status.in_(("pending", "pending_admin", "violation"))
        )
    ).all()
    proposals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in pending:
        source = candidate.source_term
        key = candidate.source_norm
        stem = None
        kind = ""
        prefix = PREFIX_RE.match(source)
        suffix = SUFFIX_RE.match(source)
        if prefix:
            stem = normalize_source(prefix.group(2))
            kind = "prefix"
        elif suffix:
            stem = normalize_source(suffix.group(1))
            kind = "numeric-suffix"
        if not stem or stem not in curated or key in seen:
            continue
        seen.add(key)
        proposals.append(
            {
                "type": "alias",
                "source": source,
                "reason": f"{kind} variant of curated {stem}",
                "concept_id": curated[stem],
            }
        )
    return proposals


def screen_pending(session: Session) -> list[dict[str, Any]]:
    pending = session.scalars(
        select(DocumentTermCandidate).where(
            DocumentTermCandidate.status.in_(("pending", "pending_admin"))
        )
    ).all()
    unique = list(dict.fromkeys(row.source_term for row in pending))
    if not unique:
        return []
    verdicts = screen_terms(unique, session=session, persist=False)
    proposals: list[dict[str, Any]] = []
    for source, verdict in verdicts.items():
        if verdict.decision == DECISION_DOMAIN:
            proposals.append(
                {
                    "type": "curated",
                    "source": source,
                    "reason": f"screen={verdict.decision} origin={verdict.origin}",
                }
            )
        elif verdict.decision == "noise":
            if normalize_source(source) in KEEP_LIST:
                continue
            proposals.append(
                {
                    "type": "denylist",
                    "source": source,
                    "reason": f"screen=noise origin={verdict.origin}",
                }
            )
    proposals.extend(propose_aliases(session))
    return proposals


def write_inbox(proposals: list[dict[str, Any]], *, title: str) -> str:
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    existing = INBOX.read_text(encoding="utf-8") if INBOX.is_file() else "# term-rules inbox\n\n"
    blocks: list[str] = []
    current = existing
    for item in proposals:
        if item.get("discarded"):
            blocks.append(
                f"## discarded\n\n- type: {item['type']}\n- source: `{item['source']}`\n"
                f"- reason: {item['reason']}\n"
            )
            continue
        prop_id = _next_prop_id(current + "".join(blocks))
        block = (
            f"## {prop_id}\n\n"
            f"- type: {item['type']}\n"
            f"- source: `{item['source']}`\n"
            f"- reason: {item['reason']}\n"
            f"- status: proposed\n"
        )
        if item.get("concept_id"):
            block += f"- concept_id: {item['concept_id']}\n"
        blocks.append(block + "\n")
        current += block
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    INBOX.write_text(existing + f"\n<!-- {title} {stamp} -->\n" + "".join(blocks), encoding="utf-8")
    return INBOX.as_posix()


def _parse_inbox() -> dict[str, dict[str, str]]:
    if not INBOX.is_file():
        return {}
    found: dict[str, dict[str, str]] = {}
    current = ""
    for line in INBOX.read_text(encoding="utf-8").splitlines():
        if line.startswith("## PROP-"):
            current = line[3:].strip()
            found[current] = {}
            continue
        if current and line.startswith("- "):
            key, _, value = line[2:].partition(":")
            found[current][key.strip()] = value.strip().strip("`")
    return found


def _append_exclusion(source: str, reason: str) -> None:
    exists = EXCLUSIONS.is_file()
    with EXCLUSIONS.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source",
                "reason",
                "scope",
                "tenant_slug",
                "project_slug",
                "decided_by",
                "candidate_id",
                "decided_at",
                "occurrences",
                "notes",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "source": source,
                "reason": reason,
                "scope": "global",
                "tenant_slug": "",
                "project_slug": "",
                "decided_by": "plan063-promote",
                "candidate_id": "",
                "decided_at": datetime.now(timezone.utc).date().isoformat(),
                "occurrences": "1",
                "notes": "promoted from inbox",
            }
        )


def _bump_toml_version() -> str:
    text = TOML.read_text(encoding="utf-8")
    match = re.search(r'version = "([^"]+)"', text)
    current = match.group(1) if match else "063-v1"
    prefix, _, num = current.rpartition("-v")
    nxt = f"{prefix or '063'}-v{int(num or '1') + 1}"
    TOML.write_text(text.replace(f'version = "{current}"', f'version = "{nxt}"', 1), encoding="utf-8")
    load_rules.cache_clear()
    return nxt


def _register_version(version: str) -> None:
    VERSIONS.parent.mkdir(parents=True, exist_ok=True)
    if not VERSIONS.is_file():
        VERSIONS.write_text(
            "# term-rules versions\n\n| version | fingerprint | date |\n| --- | --- | --- |\n",
            encoding="utf-8",
        )
    stamp = datetime.now(timezone.utc).date().isoformat()
    line = f"| {version} | {rules_fingerprint()} | {stamp} |\n"
    VERSIONS.write_text(VERSIONS.read_text(encoding="utf-8") + line, encoding="utf-8")


def promote(prop_id: str) -> dict[str, str]:
    items = _parse_inbox()
    item = items.get(prop_id)
    if item is None:
        raise ValueError(f"unknown proposal {prop_id}")
    if item.get("status") != "proposed":
        raise ValueError(f"{prop_id} is {item.get('status') or 'unknown'}")
    kind = item.get("type") or ""
    source = item.get("source") or ""
    if normalize_source(source) in KEEP_LIST and kind in {"denylist", "exclude_regex"}:
        raise ValueError(f"{prop_id} kills keep list")
    if kind == "denylist":
        _append_exclusion(source, item.get("reason") or "promoted")
        load_rules.cache_clear()
    elif kind == "exclude_regex":
        killed = _kills_keep(source)
        if killed:
            raise ValueError(f"{prop_id} kills keep list item {killed}")
        text = TOML.read_text(encoding="utf-8")
        needle = "patterns = ["
        idx = text.find(needle)
        if idx < 0:
            raise ValueError("patterns block missing")
        insert_at = text.find("\n", idx) + 1
        text = text[:insert_at] + f"  '{source}',\n" + text[insert_at:]
        TOML.write_text(text, encoding="utf-8")
        load_rules.cache_clear()
    elif kind == "curated":
        STAGING.parent.mkdir(parents=True, exist_ok=True)
        exists = STAGING.is_file()
        with STAGING.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source", "target", "notes"])
            if not exists:
                writer.writeheader()
            writer.writerow({"source": source, "target": source, "notes": item.get("reason") or ""})
    elif kind == "alias":
        STAGING.parent.mkdir(parents=True, exist_ok=True)
        exists = STAGING.is_file()
        with STAGING.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source", "target", "notes"])
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "source": source,
                    "target": item.get("concept_id") or "",
                    "notes": f"alias {item.get('reason') or ''}",
                }
            )
    else:
        raise ValueError(f"unsupported type {kind}")
    version = _bump_toml_version()
    _register_version(version)
    inbox = INBOX.read_text(encoding="utf-8")
    INBOX.write_text(inbox.replace(f"## {prop_id}\n", f"## {prop_id}\n\n- status: promoted\n", 1), encoding="utf-8")
    return {"prop_id": prop_id, "version": version, "fingerprint": rules_fingerprint()}


def report(session: Session) -> list[dict[str, Any]]:
    rows = collect_reject_rows(session)
    proposals = propose_denylist(rows)
    proposals.extend(propose_regex(rows))
    proposals.extend(propose_curated(session))
    proposals.extend(propose_aliases(session))
    return proposals


def current_rules_meta() -> dict[str, str]:
    return {"version": rules_version(), "fingerprint": rules_fingerprint()}
