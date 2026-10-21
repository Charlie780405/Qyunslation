# SPDX-License-Identifier: MPL-2.0
"""PLAN-086 language-asset authoring, release, import, and runtime bundle logic."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from qyunslation.persist.models import (
    LanguageAssetRelease,
    LanguageAssetReleaseItem,
)

ASSET_TYPES = frozenset({"termbase", "style", "pitfall"})
SCOPES = frozenset({"global", "domain", "tenant", "project"})
MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 20_000
SCOPE_RANK = {"global": 0, "domain": 1, "tenant": 2, "project": 3}


def _lang_code(value: str) -> str:
    aliases = {"english": "en", "en-us": "en", "en-gb": "en", "简体中文": "zh", "chinese": "zh", "zh-cn": "zh"}
    return aliases.get((value or "").strip().casefold(), (value or "").strip().casefold())


class AssetValidationError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_asset_type(value: str) -> str:
    asset_type = (value or "").strip().casefold()
    if asset_type not in ASSET_TYPES:
        raise AssetValidationError("ASSET_TYPE_INVALID", "asset_type must be termbase, style, or pitfall")
    return asset_type


def normalize_scope(value: str | None) -> str:
    scope = (value or "tenant").strip().casefold()
    if scope not in SCOPES:
        raise AssetValidationError("ASSET_SCOPE_INVALID", "scope must be global, domain, tenant, or project")
    return scope


def _clean(value: Any, *, limit: int = 20000) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise AssetValidationError("ASSET_FIELD_TOO_LONG", "asset field exceeds configured limit")
    return text


def _parse_csv(content: str, filename: str) -> list[dict[str, Any]]:
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in filename or "\t" in sample else csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    if not reader.fieldnames:
        raise AssetValidationError("ASSET_IMPORT_INVALID", "import requires a header row")
    rows = []
    for index, row in enumerate(reader, start=2):
        if index > MAX_IMPORT_ROWS + 1:
            raise AssetValidationError("ASSET_IMPORT_TOO_LARGE", "import exceeds the row limit")
        cleaned = {str(k or "").strip().casefold(): _clean(v) for k, v in row.items()}
        if not any(cleaned.values()):
            continue
        rows.append(cleaned)
    return rows


def _parse_tbx(content: str) -> list[dict[str, Any]]:
    # TBX-Basic is XML; ElementTree is intentionally used without resolving
    # external entities.  Unsupported XML is rejected rather than guessed.
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise AssetValidationError("ASSET_IMPORT_INVALID", "invalid TBX XML") from exc
    rows: list[dict[str, Any]] = []
    for term_entry in root.iter():
        if term_entry.tag.rsplit("}", 1)[-1] != "termEntry":
            continue
        terms: dict[str, list[str]] = {}
        for lang_set in term_entry.iter():
            if lang_set.tag.rsplit("}", 1)[-1] != "langSet":
                continue
            lang = (lang_set.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") or lang_set.attrib.get("lang") or "").casefold()
            value = next((node.text.strip() for node in lang_set.iter() if node.tag.rsplit("}", 1)[-1] == "term" and node.text and node.text.strip()), "")
            if lang and value:
                terms.setdefault(lang, []).append(value)
        langs = sorted(terms)
        if len(langs) >= 2:
            rows.append({"source": terms[langs[0]][0], "target": terms[langs[1]][0], "src_lang": langs[0], "tgt_lang": langs[1]})
    if not rows:
        raise AssetValidationError("ASSET_IMPORT_INVALID", "TBX contains no bilingual term entries")
    return rows


def parse_import_rows(asset_type: str, content: str, filename: str) -> list[dict[str, Any]]:
    if not content or len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise AssetValidationError("ASSET_IMPORT_TOO_LARGE", "import exceeds the size limit")
    if filename.casefold().endswith(".tbx"):
        rows = _parse_tbx(content)
    else:
        rows = _parse_csv(content, filename)
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if asset_type == "termbase":
            source = _clean(row.get("source") or row.get("source_term"))
            target = _clean(row.get("target") or row.get("preferred_target"))
            if not source or not target:
                raise AssetValidationError("ASSET_IMPORT_INVALID", f"row {index} requires source and target")
            normalized.append(
                {
                    "source": source,
                    "target": target,
                    "domain": _clean(row.get("domain"), limit=256),
                    "risk": _clean(row.get("risk") or "normal", limit=32),
                    "forbidden": [item.strip() for item in _clean(row.get("forbidden"), limit=2000).split("|") if item.strip()],
                    "src_lang": _clean(row.get("src_lang") or "en", limit=16),
                    "tgt_lang": _clean(row.get("tgt_lang") or "zh", limit=16),
                }
            )
        elif asset_type == "style":
            text = _clean(row.get("text") or row.get("rule"))
            if not text:
                raise AssetValidationError("ASSET_IMPORT_INVALID", f"row {index} requires text")
            normalized.append({"code": _clean(row.get("code") or f"STYLE-{index:04d}", limit=128), "text": text, "example": _clean(row.get("example"), limit=2000), "severity": _clean(row.get("severity") or "guidance", limit=32)})
        else:
            code = _clean(row.get("code"), limit=128)
            trigger = _clean(row.get("trigger") or row.get("pattern"))
            if not code or not trigger:
                raise AssetValidationError("ASSET_IMPORT_INVALID", f"row {index} requires code and trigger")
            normalized.append({"code": code, "trigger": trigger, "detector": _clean(row.get("detector") or "deterministic", limit=32), "severity": _clean(row.get("severity") or "warning", limit=32), "remediation": _clean(row.get("remediation"), limit=2000), "false_positive": _clean(row.get("false_positive"), limit=2000)})
    if not normalized:
        raise AssetValidationError("ASSET_IMPORT_INVALID", "import contains no usable rows")
    return normalized


def _visible_release_query(tenant_id: str, project_id: str | None, asset_type: str | None = None):
    visibility = or_(LanguageAssetRelease.tenant_id.is_(None), LanguageAssetRelease.tenant_id == tenant_id)
    project_visibility = or_(LanguageAssetRelease.project_id.is_(None), LanguageAssetRelease.project_id == project_id)
    stmt = select(LanguageAssetRelease).where(LanguageAssetRelease.status == "published").where(visibility).where(project_visibility)
    if asset_type:
        stmt = stmt.where(LanguageAssetRelease.asset_type == asset_type)
    return stmt.options(selectinload(LanguageAssetRelease.items))


def release_dict(release: LanguageAssetRelease, *, include_items: bool = True) -> dict[str, Any]:
    body = {
        "id": release.id,
        "tenant_id": release.tenant_id,
        "project_id": release.project_id,
        "asset_type": release.asset_type,
        "scope": release.scope,
        "version": release.version,
        "status": release.status,
        "src_lang": release.src_lang,
        "tgt_lang": release.tgt_lang,
        "document_profile": release.document_profile,
        "name": release.name,
        "content_hash": release.content_hash,
        "license": release.license,
        "provenance": release.provenance,
        "metadata": release.metadata_json or {},
        "published_by": release.published_by,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "created_at": release.created_at.isoformat() if release.created_at else None,
    }
    if include_items:
        body["items"] = [{"id": item.id, "item_key": item.item_key, "payload": item.payload, "sort_order": item.sort_order} for item in release.items]
    return body


def _release_item_key(asset_type: str, payload: dict[str, Any], index: int) -> str:
    if asset_type == "termbase":
        return f"{payload.get('src_lang', 'en')}|{payload.get('source', '').casefold()}|{payload.get('tgt_lang', 'zh')}"
    return str(payload.get("code") or f"item-{index:06d}")


def create_release(
    session: Session,
    *,
    tenant_id: str | None,
    project_id: str | None,
    actor_sub: str,
    asset_type: str,
    rows: Iterable[dict[str, Any]],
    scope: str = "tenant",
    src_lang: str = "en",
    tgt_lang: str = "zh",
    document_profile: str | None = None,
    name: str = "",
    license: str | None = None,
    provenance: str | None = None,
    source_sha256: str | None = None,
) -> LanguageAssetRelease:
    asset_type = normalize_asset_type(asset_type)
    scope = normalize_scope(scope)
    rows = [dict(row) for row in rows]
    if not rows:
        raise AssetValidationError("ASSET_IMPORT_INVALID", "release must contain at least one item")
    if not license or not license.strip():
        raise AssetValidationError("ASSET_LICENSE_BLOCKED", "license is required before publishing an asset")
    payload_hash = canonical_hash(rows)
    previous = session.scalar(
        select(LanguageAssetRelease.version)
        .where(LanguageAssetRelease.tenant_id == tenant_id, LanguageAssetRelease.project_id == project_id, LanguageAssetRelease.asset_type == asset_type, LanguageAssetRelease.scope == scope)
        .order_by(LanguageAssetRelease.version.desc())
        .limit(1)
    )
    release = LanguageAssetRelease(
        tenant_id=tenant_id,
        project_id=project_id,
        asset_type=asset_type,
        scope=scope,
        version=int(previous or 0) + 1,
        status="draft",
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        document_profile=document_profile,
        name=name or f"{asset_type} release",
        source_sha256=source_sha256,
        content_hash=payload_hash,
        license=license.strip(),
        provenance=(provenance or "").strip() or None,
        metadata_json={"item_count": len(rows)},
        created_by=actor_sub,
    )
    session.add(release)
    session.flush()
    for index, payload in enumerate(rows):
        session.add(LanguageAssetReleaseItem(release_id=release.id, item_key=_release_item_key(asset_type, payload, index), payload=payload, sort_order=index))
    session.flush()
    return release


def publish_release(session: Session, release: LanguageAssetRelease, *, actor_sub: str) -> LanguageAssetRelease:
    if release.status == "published":
        return release
    if release.status != "draft":
        raise AssetValidationError("ASSET_RELEASE_INVALID_STATE", "only draft releases can be published")
    if not release.items:
        raise AssetValidationError("ASSET_IMPORT_INVALID", "cannot publish an empty release")
    release.status = "published"
    release.published_by = actor_sub
    release.published_at = datetime.now(UTC)
    session.flush()
    return release


def build_language_asset_bundle(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None,
    src_lang: str = "en",
    tgt_lang: str = "zh",
    document_profile: str | None = None,
) -> dict[str, Any]:
    def published_sort(value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    releases = list(session.scalars(_visible_release_query(tenant_id, project_id)).unique().all())
    selected: dict[str, LanguageAssetRelease] = {}
    for release in releases:
        if release.src_lang and _lang_code(release.src_lang) != _lang_code(src_lang):
            continue
        if release.tgt_lang and _lang_code(release.tgt_lang) != _lang_code(tgt_lang):
            continue
        if release.document_profile and document_profile and release.document_profile != document_profile:
            continue
        rank = (SCOPE_RANK.get(release.scope, -1), release.version, published_sort(release.published_at))
        current = selected.get(release.asset_type)
        current_rank = (SCOPE_RANK.get(current.scope, -1), current.version, published_sort(current.published_at)) if current else None
        if current is None or rank > current_rank:
            selected[release.asset_type] = release
    body: dict[str, Any] = {
        "schema": "086-language-assets-v1",
        "source_language": src_lang,
        "target_language": tgt_lang,
        "document_profile": document_profile,
        "termbase": {"items": []},
        "style": {"rules": []},
        "pitfall": {"rules": []},
        "releases": {},
        "conflicts": [],
    }
    for asset_type, release in selected.items():
        body["releases"][asset_type] = {"id": release.id, "version": release.version, "content_hash": release.content_hash, "scope": release.scope}
        if asset_type == "termbase":
            body["termbase"]["items"] = [item.payload for item in release.items]
        elif asset_type == "style":
            body["style"]["rules"] = [item.payload for item in release.items]
        else:
            body["pitfall"]["rules"] = [item.payload for item in release.items]
    body["bundle_hash"] = canonical_hash(body)
    return body


def preview_import(*, asset_type: str, content: str, filename: str, license: str | None, provenance: str | None, scope: str) -> dict[str, Any]:
    asset_type = normalize_asset_type(asset_type)
    normalize_scope(scope)
    if not license or not license.strip():
        raise AssetValidationError("ASSET_LICENSE_BLOCKED", "license is required for controlled import")
    rows = parse_import_rows(asset_type, content, filename)
    return {"rows": rows, "row_count": len(rows), "content_hash": canonical_hash(rows), "license": license.strip(), "provenance": (provenance or "").strip() or None}


def check_pitfall_rules(bundle: dict[str, Any] | None, translated_text: str) -> list[Any]:
    """Run only answer-independent deterministic pitfall rules.

    The release payload is data, never executable code: a rule can match a
    literal trigger but cannot inject a regex or Python expression into the
    worker. Semantic rules are surfaced for later semantic QA and skipped here.
    """
    from qyunslation.pipeline.qa.engine import QaFinding

    findings: list[Any] = []
    text = translated_text or ""
    for rule in ((bundle or {}).get("pitfall") or {}).get("rules") or []:
        if str(rule.get("detector") or "deterministic").casefold() != "deterministic":
            continue
        trigger = str(rule.get("trigger") or "").strip()
        if not trigger or trigger.casefold() not in text.casefold():
            continue
        severity = str(rule.get("severity") or "warning").casefold()
        if severity not in {"blocker", "warning", "info"}:
            severity = "warning"
        findings.append(
            QaFinding(
                category="pitfall",
                severity=severity,
                code="ASSET_PITFALL_TRIGGER",
                message=f"错法表命中：{rule.get('code') or trigger}",
                evidence={"rule_code": rule.get("code"), "trigger": trigger, "remediation": rule.get("remediation") or ""},
            )
        )
    return findings


def render_prompt_asset_block(bundle: dict[str, Any] | None, *, limit: int = 80) -> str:
    """Render only the selected, bounded assets for a model prompt.

    The block is deliberately labelled as reviewed data.  It is not treated as
    executable instructions and is never populated from semantic suggestions.
    """
    bundle = bundle or {}
    lines: list[str] = []
    terms = ((bundle.get("termbase") or {}).get("items") or [])[:limit]
    if terms:
        lines.append("批准术语（必须优先使用；禁用译法不得出现）：")
        for item in terms:
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            if source and target:
                lines.append(f"- {source} → {target}")
                for forbidden in item.get("forbidden") or []:
                    if str(forbidden).strip():
                        lines.append(f"  禁用：{str(forbidden).strip()}")
    rules = ((bundle.get("style") or {}).get("rules") or [])[:limit]
    if rules:
        lines.append("风格规则（按适用文档类型执行）：")
        lines.extend(f"- {str(item.get('text') or item.get('rule') or '').strip()}" for item in rules if str(item.get("text") or item.get("rule") or "").strip())
    pitfalls = ((bundle.get("pitfall") or {}).get("rules") or [])[:limit]
    if pitfalls:
        lines.append("错法提醒（避免触发下列错误表达）：")
        lines.extend(f"- 避免：{str(item.get('trigger') or '').strip()}；改用：{str(item.get('remediation') or '').strip()}" for item in pitfalls if str(item.get("trigger") or "").strip())
    return "\n".join(lines).strip()
