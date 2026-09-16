# SPDX-License-Identifier: MPL-2.0
"""PLAN-061：确定性对齐实际译法，批量 LLM 只补 AI 推荐译法。"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

MATCH_TERMBASE = "termbase"
MATCH_VERBATIM = "verbatim"
MATCH_LLM = "llm"
MATCH_NONE = "none"
MATCH_CANDIDATE = "candidate"
MATCH_ALIAS = "alias"
MATCH_SEMANTIC = "semantic"
LEXICON_MATCHES = frozenset({MATCH_TERMBASE, MATCH_ALIAS, MATCH_SEMANTIC, "exact"})


@dataclass(frozen=True, slots=True)
class AlignedTerm:
    source_term: str
    observed_target: str
    suggested_target: str | None
    match_type: str
    confidence: float


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _preferred_target(source_term: str, policy: dict | None) -> str | None:
    source = (source_term or "").casefold()
    for term in (policy or {}).get("terms") or ():
        if not term.get("hard_constraint"):
            continue
        configured = str(term.get("source_term") or "").strip()
        preferred = str(term.get("preferred_target") or "").strip()
        if configured.casefold() == source and preferred:
            return preferred
    return None


def _stem_preferred(source_term: str, policy: dict | None) -> str | None:
    from qyunslation.glossary.term_morphology import morphology_stem

    stem = morphology_stem(source_term)
    if not stem:
        return None
    for term in (policy or {}).get("terms") or ():
        if not term.get("hard_constraint"):
            continue
        configured = str(term.get("source_term") or "").strip()
        preferred = str(term.get("preferred_target") or "").strip()
        if preferred and morphology_stem(configured) == stem:
            return preferred
    return None


def align_observed(
    source_term: str,
    *,
    source_context: str,
    target_context: str,
    policy: dict | None = None,
) -> AlignedTerm:
    """词库命中或原文保留；绝不按位置猜测。"""
    source = (source_term or "").strip()
    tgt_ctx = target_context or ""
    preferred = _preferred_target(source, policy)
    if preferred and preferred.casefold() in tgt_ctx.casefold():
        return AlignedTerm(source, preferred, preferred, MATCH_TERMBASE, 1.0)
    if source and source in tgt_ctx and _has_cjk(tgt_ctx):
        return AlignedTerm(source, source, None, MATCH_VERBATIM, 0.9)
    return AlignedTerm(source, "", None, MATCH_NONE, 0.0)


def prefer_explicit_observation(extracted: dict, aligned: AlignedTerm) -> AlignedTerm:
    """显式 span 的实际译法优先于窗口猜测。"""
    observed = str(extracted.get("observed_target") or "").strip()
    if not observed:
        return aligned
    if aligned.match_type == MATCH_TERMBASE:
        return AlignedTerm(
            aligned.source_term,
            observed,
            aligned.suggested_target or aligned.observed_target,
            MATCH_TERMBASE,
            1.0,
        )
    return AlignedTerm(
        aligned.source_term,
        observed,
        aligned.suggested_target,
        MATCH_CANDIDATE,
        1.0,
    )


def _suggest_enabled() -> bool:
    return os.environ.get("QYUNSLATION_TERM_SUGGEST", "1").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _suggest_limit() -> int:
    try:
        return max(0, int(os.environ.get("QYUNSLATION_TERM_SUGGEST_MAX", "60")))
    except ValueError:
        return 60


def _suggest_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("QYUNSLATION_TERM_SUGGEST_TIMEOUT", "60")))
    except ValueError:
        return 60.0


def _default_cache_dir() -> Path:
    return Path.home() / ".cache" / "qyunslation" / "term-align" / "v2"


def _cache_key(source_term: str, target_context: str) -> str:
    from qyunslation.glossary.governance import normalize_source

    payload = f"{normalize_source(source_term)}|{hashlib.sha1((target_context or '').encode('utf-8')).hexdigest()}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _read_cache(cache_dir: Path, key: str) -> AlignedTerm | None:
    path = cache_dir / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return AlignedTerm(
        source_term=str(data.get("source_term") or ""),
        observed_target=str(data.get("observed_target") or ""),
        suggested_target=data.get("suggested_target"),
        match_type=str(data.get("match_type") or MATCH_LLM),
        confidence=float(data.get("confidence") or 0.0),
    )


def _write_cache(cache_dir: Path, key: str, aligned: AlignedTerm) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    path.write_text(
        json.dumps(
            {
                "source_term": aligned.source_term,
                "observed_target": aligned.observed_target,
                "suggested_target": aligned.suggested_target,
                "match_type": aligned.match_type,
                "confidence": aligned.confidence,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if "```" in raw:
        fence = raw.split("```", 2)
        raw = fence[1]
        if raw.casefold().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return []
    return [item for item in data if isinstance(item, dict)]


def _needs_suggestion(aligned: AlignedTerm) -> bool:
    return aligned.match_type == MATCH_NONE and not aligned.suggested_target


def suggest_from_termbase(
    rows: Iterable[dict[str, Any] | AlignedTerm],
    *,
    policy: dict | None = None,
    session: Any | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> dict[str, AlignedTerm]:
    """词库精确 / 词干 alias / 语义软建议；不调用 LLM。"""
    from qyunslation.glossary.governance import normalize_source
    from qyunslation.glossary.term_morphology import morphology_stem

    staged: list[AlignedTerm] = []
    for row in rows:
        if isinstance(row, AlignedTerm):
            aligned = row
        else:
            aligned = row.get("aligned")
            if not isinstance(aligned, AlignedTerm):
                continue
        if not _needs_suggestion(aligned):
            if aligned.match_type in LEXICON_MATCHES and aligned.suggested_target:
                staged.append(aligned)
            continue
        staged.append(aligned)
    if not staged:
        return {}

    records: list[Any] = []
    if session is not None and tenant_id:
        try:
            from qyunslation.glossary.termbase import list_runtime_terms

            records = list_runtime_terms(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
            )
        except Exception:
            records = []
    by_norm: dict[str, Any] = {}
    by_stem: dict[str, Any] = {}
    for record in records:
        source = str(getattr(record, "source_term", "") or "").strip()
        target = str(getattr(record, "target_term", "") or "").strip()
        if not source or not target:
            continue
        by_norm.setdefault(normalize_source(source), record)
        by_stem.setdefault(morphology_stem(source), record)

    found: dict[str, AlignedTerm] = {}
    unresolved: list[AlignedTerm] = []
    for aligned in staged:
        source = aligned.source_term
        if aligned.match_type in LEXICON_MATCHES and aligned.suggested_target:
            found[source] = aligned
            continue
        preferred = _preferred_target(source, policy)
        if preferred:
            found[source] = AlignedTerm(source, aligned.observed_target, preferred, MATCH_TERMBASE, 1.0)
            continue
        record = by_norm.get(normalize_source(source))
        if record is not None:
            found[source] = AlignedTerm(
                source, aligned.observed_target, record.target_term, MATCH_TERMBASE, 0.98
            )
            continue
        stem = morphology_stem(source)
        record = by_stem.get(stem) if stem else None
        if record is not None:
            found[source] = AlignedTerm(
                source, aligned.observed_target, record.target_term, MATCH_ALIAS, 0.92
            )
            continue
        preferred = _stem_preferred(source, policy)
        if preferred:
            found[source] = AlignedTerm(source, aligned.observed_target, preferred, MATCH_ALIAS, 0.9)
            continue
        unresolved.append(aligned)

    if unresolved and session is not None and tenant_id:
        try:
            from qyunslation.persist.term_embedding_repo import semantic_search_concept_terms

            for aligned in unresolved:
                hits = semantic_search_concept_terms(
                    session,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    query=aligned.source_term,
                    src_lang=src_lang,
                    tgt_lang=tgt_lang,
                    limit=1,
                    threshold=0.88,
                )
                if not hits:
                    continue
                hit = hits[0]
                target = str(hit.get("target_term") or "").strip()
                if not target:
                    continue
                found[aligned.source_term] = AlignedTerm(
                    aligned.source_term,
                    aligned.observed_target,
                    target,
                    MATCH_SEMANTIC,
                    float(hit.get("score") or 0.88),
                )
        except Exception:
            pass
    return found


def suggest_targets(
    rows: Iterable[dict[str, Any] | AlignedTerm],
    *,
    provider: Any | None = None,
    limit: int | None = None,
    timeout: float | None = None,
    cache_dir: Path | str | None = None,
) -> dict[str, AlignedTerm]:
    """只处理 window/none；整篇一次 chat，失败即空。"""
    if not _suggest_enabled():
        return {}
    staged: list[tuple[str, str, AlignedTerm]] = []
    for row in rows:
        if isinstance(row, AlignedTerm):
            aligned = row
            target_context = ""
        else:
            aligned = row.get("aligned")
            extracted = row.get("extracted") or {}
            target_context = str(extracted.get("target_context") or "")
            if not isinstance(aligned, AlignedTerm):
                continue
        if not _needs_suggestion(aligned):
            continue
        staged.append((aligned.source_term, target_context, aligned))
    cap = _suggest_limit() if limit is None else max(0, limit)
    staged = staged[:cap]
    if not staged:
        return {}

    store = Path(cache_dir) if cache_dir else _default_cache_dir()
    found: dict[str, AlignedTerm] = {}
    pending: list[tuple[str, str, AlignedTerm]] = []
    for source_term, target_context, aligned in staged:
        cached = _read_cache(store, _cache_key(source_term, target_context))
        if cached is not None:
            found[source_term] = cached
        else:
            pending.append((source_term, target_context, aligned))
    if not pending:
        return found

    try:
        chat = provider
        if chat is None:
            from qyunslation.gateway.provider import get_provider

            chat = get_provider()
        chosen_timeout = timeout if timeout is not None else _suggest_timeout()
        try:
            chat = replace(chat, timeout=chosen_timeout)
        except TypeError:
            pass
        payload = [
            {
                "source_term": source_term,
                "target_context": target_context,
                "observed_hint": aligned.observed_target,
            }
            for source_term, target_context, aligned in pending
        ]
        raw = chat.translate(
            json.dumps(payload, ensure_ascii=False),
            system=(
                "You suggest Chinese medical term translations. "
                "Reply with a JSON array of objects: "
                "source_term, observed_target, suggested_target, confidence. "
                "observed_target must be a substring of target_context or empty. "
                "Do not invent numbers or units."
            ),
        )
        for item in _parse_json_array(raw):
            source_term = str(item.get("source_term") or "").strip()
            if not source_term:
                continue
            match = next((row for row in pending if row[0] == source_term), None)
            if match is None:
                continue
            _source, target_context, aligned = match
            suggested = str(item.get("suggested_target") or "").strip() or None
            observed = str(item.get("observed_target") or "").strip()
            if observed and observed not in target_context:
                observed = ""
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.5)))
            except (TypeError, ValueError):
                confidence = 0.5
            result = AlignedTerm(
                source_term=source_term,
                observed_target=observed or aligned.observed_target,
                suggested_target=suggested,
                match_type=MATCH_LLM,
                confidence=confidence,
            )
            found[source_term] = result
            _write_cache(store, _cache_key(source_term, target_context), result)
    except Exception:
        return found
    return found


def _paragraph_prompt() -> str:
    path = Path(__file__).resolve().parents[2] / "glossaries" / "prompts" / "term-align.zh.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        "Reply with a JSON array of source_term, observed_target, "
        "suggested_target, confidence. observed_target must be a substring."
    )


def _paragraph_cache_key(source_para: str, target_para: str, terms: list[str]) -> str:
    payload = f"{source_para}|{target_para}|{'|'.join(sorted(terms))}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def align_by_paragraph_batch(
    rows: Iterable[dict[str, Any]],
    *,
    batch_size: int = 15,
    provider: Any | None = None,
    cache_dir: Path | str | None = None,
) -> dict[str, AlignedTerm]:
    """按完整段落对抽双语术语；observed 必须逐字出现在该段译文。"""
    if not _suggest_enabled():
        return {}
    groups: dict[tuple[str, str], list[str]] = {}
    originals: dict[str, AlignedTerm] = {}
    for row in rows:
        aligned = row.get("aligned")
        extracted = row.get("extracted") or {}
        if not isinstance(aligned, AlignedTerm) or not _needs_suggestion(aligned):
            continue
        source_para = str(extracted.get("source_context") or "")
        target_para = str(extracted.get("target_context") or "")
        groups.setdefault((source_para, target_para), [])
        if aligned.source_term not in groups[(source_para, target_para)]:
            groups[(source_para, target_para)].append(aligned.source_term)
        originals[aligned.source_term] = aligned
    if not groups:
        return {}
    store = Path(cache_dir) if cache_dir else _default_cache_dir()
    found: dict[str, AlignedTerm] = {}
    pending_groups: list[tuple[str, str, list[str]]] = []
    for (source_para, target_para), terms in groups.items():
        cached_hit = True
        for term in terms:
            cached = _read_cache(store, _cache_key(term, target_para))
            if cached is None:
                cached_hit = False
                break
            found[term] = cached
        if not cached_hit:
            for term in terms:
                found.pop(term, None)
            pending_groups.append((source_para, target_para, terms))
    if not pending_groups:
        return found
    try:
        chat = provider
        if chat is None:
            from qyunslation.gateway.provider import get_provider

            chat = get_provider()
        size = max(1, batch_size)
        for start in range(0, len(pending_groups), size):
            chunk = pending_groups[start : start + size]
            payload = [
                {
                    "source_paragraph": source_para,
                    "target_paragraph": target_para,
                    "terms": terms,
                }
                for source_para, target_para, terms in chunk
            ]
            raw = chat.translate(json.dumps(payload, ensure_ascii=False), system=_paragraph_prompt())
            parsed = _parse_json_array(raw)
            allowed = {term: target for _src, target, terms in chunk for term in terms}
            for item in parsed:
                source_term = str(item.get("source_term") or "").strip()
                if source_term not in allowed:
                    continue
                target_para = allowed[source_term]
                suggested = str(item.get("suggested_target") or "").strip() or None
                observed = str(item.get("observed_target") or "").strip()
                if observed and observed not in target_para:
                    observed = ""
                try:
                    confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.5)))
                except (TypeError, ValueError):
                    confidence = 0.5
                result = AlignedTerm(
                    source_term=source_term,
                    observed_target=observed,
                    suggested_target=suggested,
                    match_type=MATCH_LLM,
                    confidence=confidence,
                )
                found[source_term] = result
                _write_cache(store, _cache_key(source_term, target_para), result)
    except Exception:
        return found
    return found

