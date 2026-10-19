# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c/d/e/f/g：/api/v1（projects / jobs / concepts / tm / qa / review / health）。"""
from __future__ import annotations

import asyncio
import os
import re
import json
import base64
import hashlib
import secrets
import logging
import mimetypes
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, delete, event, func, literal, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from qyunslation.persist import repo
from qyunslation.persist.audit import record_audit, sanitize_extra
from qyunslation.persist.db import (
    DATABASE_URL_ENV,
    get_database_url,
    get_engine,
    init_engine,
    ping_db,
    reset_engine,
)
from qyunslation.persist.identity import IdentityContext, require_csrf, resolve_identity
from qyunslation.pipeline.preflight_probe import probe_document
from qyunslation.persist.models import (
    DocumentTermCandidate,
    Job,
    PreflightRecord,
    QaDisposition,
    QaItem,
    ReviewDecision,
    ReviewDraft,
    ReviewSegment,
    RunBatchOperation,
    RunSelection,
    TranslationArtifact,
    TranslationRunRecord,
    UploadSession,
    WebPreference,
)
from qyunslation.core.schemas import AutoWorkflowParams
from qyunslation.structure.ingest import DEFAULT_MAX_UPLOAD_BYTES

PREF_ALLOWED_KEYS = frozenset(
    {
        "direction",
        "profile",
        "bilingual",
        "density",
        "reduceMotion",
        "largeText",
        "workbench",
    }
)
PREF_DEFAULTS = {
    "direction": "English → 简体中文",
    "profile": "临床研究文档",
    "bilingual": True,
    "density": "comfortable",
    "reduceMotion": False,
    "largeText": False,
        "workbench": {
        "sourceLanguage": "English",
        "targetLanguage": "简体中文",
        "profile": "临床研究文档",
        "bilingual": True,
        "classification": "internal",
        "domainProfile": "general",
        "modelProfileId": "internal-qwen-quality",
    },
}
WORKBENCH_PREF_KEYS = frozenset(
    {
        "sourceLanguage",
        "targetLanguage",
        "profile",
        "bilingual",
        "classification",
        "domainProfile",
        "modelProfileId",
    }
)
# Mirrors the profiles the workbench UI offers; AD additionally allows 医学研究文献.
WORKBENCH_DOCUMENT_PROFILES = frozenset(
    {"临床研究文档", "监管申报材料", "通用医药文档", "医学研究文献"}
)
UPLOAD_SESSION_TTL_HOURS = 24
UPLOAD_CHUNK_MAX_BYTES = 8 * 1024 * 1024
_CONTENT_RANGE_RE = re.compile(
    r"^bytes\s+(?P<start>\d+)-(?P<end>\d+)/(?P<total>\d+)$",
    re.IGNORECASE,
)
PREFLIGHT_ALLOWED_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg"})
PREFLIGHT_TTL_HOURS = 24
SUPPORTED_LANGUAGES = frozenset({"English", "简体中文"})
SUPPORTED_DIRECTIONS = {
    "English → 简体中文": ("English", "简体中文"),
    "简体中文 → English": ("简体中文", "English"),
}


async def _stream_upload_limited(upload: UploadFile, target: Path) -> tuple[str, int]:
    """Stream an upload to a private temporary path while hashing it once.

    The previous implementation built a second in-memory copy of every upload
    before writing it to disk.  Large PDFs therefore paid both a memory and a
    disk pass.  This helper keeps the bounded read contract while making the
    temporary file the only full-size copy.
    """
    raw_limit = (os.environ.get("QYUNSLATION_MAX_UPLOAD_BYTES") or "").strip()
    try:
        limit = int(raw_limit) if raw_limit else DEFAULT_MAX_UPLOAD_BYTES
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="invalid upload limit configuration") from exc
    if limit <= 0:
        raise HTTPException(status_code=500, detail="invalid upload limit configuration")
    total = 0
    digest = hashlib.sha256()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as handle:
            while True:
                chunk = await upload.read(min(1024 * 1024, limit - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail="uploaded file exceeds configured limit")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        raise
    return digest.hexdigest(), total

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

router = APIRouter(prefix="/api/v1", tags=["API v1"])
logger = logging.getLogger(__name__)


class ProjectCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)


class JobCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    source_sha256: str = Field(min_length=64, max_length=64)
    storage_key: str | None = Field(default=None, max_length=512)
    attach_gateway_provenance: bool = False


def _job_dict(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "source_sha256": job.source_sha256,
        "status": job.status,
        "storage_key": job.storage_key,
        "provenance": job.provenance,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def ensure_engine_ready() -> None:
    if get_engine() is not None:
        return
    url = get_database_url()
    if not url:
        return
    try:
        init_engine(url)
    except Exception:
        reset_engine()


def get_db() -> Generator[Session, None, None]:
    ensure_engine_ready()
    eng = get_engine()
    if eng is None:
        raise HTTPException(
            status_code=503,
            detail=f"database unavailable: set {DATABASE_URL_ENV}",
        )
    from qyunslation.persist.db import SessionLocal

    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="database session factory missing")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_identity(request: Request) -> IdentityContext:
    require_csrf(request)
    return resolve_identity(request)


def _tenant_bundle(session: Session, identity: IdentityContext):
    tenant = repo.get_or_create_tenant(session, slug=identity.tenant_slug)
    repo.ensure_membership(session, tenant_id=tenant.id, user_sub=identity.user_sub)
    return tenant


def _owned_job(session: Session, *, job_id: str, tenant_id: str):
    """Load a job only after checking the tenant-owned project boundary."""
    from qyunslation.persist.review_repo import job_owned_by_tenant

    return job_owned_by_tenant(session, job_id=job_id, tenant_id=tenant_id)


@router.get("/health")
def api_health(request: Request) -> dict[str, Any]:
    """匿名只回 schema/db；env 与配置位只对已认证身份可见。"""
    ensure_engine_ready()
    ok = ping_db()
    body: dict[str, Any] = {
        "schema": "034h",
        "db": "ok" if ok else "unavailable",
    }
    try:
        resolve_identity(request)
    except Exception:
        return body
    body["database_url_set"] = bool(get_database_url())
    body["env"] = os.environ.get("QYUNSLATION_ENV") or "development"
    return body


@router.get("/me")
def api_me(
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the authenticated principal without exposing bearer credentials."""
    from qyunslation.pipeline.ad_runtime import ad_rollout_allowed, ad_rollout_mode

    tenant = _tenant_bundle(session, identity)
    membership = repo.ensure_membership(
        session,
        tenant_id=tenant.id,
        user_sub=identity.user_sub,
        role=_identity_role(identity),
    )
    return {
        "sub": identity.user_sub,
        "display_name": identity.display_name or identity.user_sub,
        "tenant_id": tenant.id,
        "tenant_slug": tenant.slug,
        "roles": [membership.role],
        "capabilities": {
            "can_review": membership.role in {"reviewer", "term_admin", "admin", "owner"},
            "can_manage_terms": membership.role in {"term_admin", "admin", "owner"},
            "can_manage_policy": membership.role in {"admin", "owner"},
            "workbench_v2": "workbench_v2" in identity.roles,
            "ad_enabled": ad_rollout_allowed(
                mode=ad_rollout_mode(
                    env=os.environ.get("QYUNSLATION_ENV"),
                    configured=(
                        os.environ.get("QYUNSLATION_AD_PROMPT_MODE")
                        or os.environ.get("QYUNSLATION_AD_ROLLOUT")
                    ),
                ),
                tenant=tenant.slug,
                tenants=os.environ.get("QYUNSLATION_AD_PROMPT_TENANTS"),
            ),
        },
    }


def _effective_role(session: Session, identity: IdentityContext) -> str:
    """Local membership can raise a user to admin even when OIDC only sends workbench_v2."""
    oidc_role = _identity_role(identity)
    tenant = _tenant_bundle(session, identity)
    membership = repo.ensure_membership(
        session,
        tenant_id=tenant.id,
        user_sub=identity.user_sub,
        role=oidc_role,
    )
    rank = {"member": 0, "reviewer": 1, "term_admin": 2, "admin": 3, "owner": 4}
    if rank.get(membership.role, 0) >= rank.get(oidc_role, 0):
        return membership.role
    return oidc_role


def _can_review_run(session: Session, identity: IdentityContext, run: TranslationRunRecord) -> bool:
    """Reviewers, local admins, and the run owner can decide terms on that task."""
    if _effective_role(session, identity) in {"reviewer", "term_admin", "admin", "owner"}:
        return True
    return bool(run.actor_sub) and run.actor_sub == identity.user_sub


def _identity_role(identity: IdentityContext) -> str:
    """Map provider roles to the existing persistence role vocabulary."""
    mapping = {
        "translator": "member",
        "reviewer": "reviewer",
        "termbase_admin": "term_admin",
        "system_admin": "admin",
        "owner": "owner",
        "admin": "admin",
        "term_admin": "term_admin",
    }
    for role in identity.roles:
        mapped = mapping.get(role.strip().lower())
        if mapped:
            return mapped
    return "member"


def _preflight_root() -> Path:
    raw = (os.environ.get("QYUNSLATION_PREFLIGHT_ROOT") or "var/preflights").strip()
    root = Path(raw)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def _preflight_path(record: PreflightRecord) -> Path:
    root = _preflight_root().resolve()
    path = (root / record.storage_key).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=500, detail="invalid preflight storage key")
    return path


def _preflight_text_for_domain(record: PreflightRecord) -> str:
    """Read bounded text for domain gating; binary failures remain explicit."""
    from qyunslation.pipeline.ad_text_extract import extract_preflight_text

    try:
        return extract_preflight_text(_preflight_path(record))
    except HTTPException:
        return ""


def _validate_domain_profile(
    *,
    preflight: PreflightRecord,
    domain_profile: str,
    direction: str,
    document_profile: str,
    tenant_slug: str,
) -> dict[str, Any] | None:
    domain = (domain_profile or "general").strip().casefold()
    if domain == "general":
        return None
    if domain != "ad":
        raise HTTPException(status_code=422, detail={"code": "AD_PROFILE_UNSUPPORTED", "message": "unsupported domain profile"})
    from qyunslation.pipeline.ad_runtime import ad_rollout_allowed, ad_rollout_mode

    rollout = ad_rollout_mode(
        env=os.environ.get("QYUNSLATION_ENV"),
        configured=(
            os.environ.get("QYUNSLATION_AD_PROMPT_MODE")
            or os.environ.get("QYUNSLATION_AD_ROLLOUT")
        ),
    )
    if not ad_rollout_allowed(
        mode=rollout,
        tenant=tenant_slug,
        tenants=os.environ.get("QYUNSLATION_AD_PROMPT_TENANTS"),
    ):
        raise HTTPException(
            status_code=422,
            detail={"code": "AD_ROLLOUT_DENIED", "message": "AD 专业模式尚未对该租户开放"},
        )
    if direction not in {"English → 简体中文", "简体中文 → English"} or document_profile not in {"医学研究文献", "临床研究文档"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "AD_PROFILE_UNSUPPORTED", "message": "AD 仅支持中英双向医学研究文献或临床研究文档"},
        )
    from qyunslation.pipeline.ad_prompt import detect_domain_evidence

    text = _preflight_text_for_domain(preflight)
    if not text or not detect_domain_evidence(text):
        raise HTTPException(
            status_code=422,
            detail={"code": "AD_DOMAIN_EVIDENCE_MISSING", "message": "源文缺少可验证的 AD 领域锚点"},
        )
    return {"source_chars": len(text), "evidence": True}


def _upload_root() -> Path:
    raw = (os.environ.get("QYUNSLATION_UPLOAD_ROOT") or "var/uploads").strip()
    root = Path(raw)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def _upload_path(record: UploadSession) -> Path:
    root = _upload_root().resolve()
    path = (root / record.storage_key).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=500, detail="invalid upload storage key")
    return path


def _upload_session_dict(record: UploadSession) -> dict[str, Any]:
    return {
        "id": record.id,
        "filename": record.source_filename,
        "format": record.source_format,
        "total_size": record.total_size,
        "received_bytes": record.received_bytes,
        "expected_sha256": record.expected_sha256,
        "status": record.status,
        "expires_at": record.expires_at.isoformat(),
        "created_at": record.created_at.isoformat(),
    }


def _safe_workbench_preferences(raw: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(PREF_DEFAULTS["workbench"])
    incoming = (raw or {}).get("workbench")
    if isinstance(incoming, dict):
        for key in WORKBENCH_PREF_KEYS:
            if key in incoming:
                merged[key] = incoming[key]
    if merged["sourceLanguage"] not in SUPPORTED_LANGUAGES:
        merged["sourceLanguage"] = PREF_DEFAULTS["workbench"]["sourceLanguage"]
    if merged["targetLanguage"] not in SUPPORTED_LANGUAGES:
        merged["targetLanguage"] = PREF_DEFAULTS["workbench"]["targetLanguage"]
    if merged["classification"] not in {"confidential", "internal", "public"}:
        merged["classification"] = "internal"
    if merged.get("domainProfile") not in {"general", "ad"}:
        merged["domainProfile"] = "general"
    if merged["profile"] not in WORKBENCH_DOCUMENT_PROFILES:
        merged["profile"] = PREF_DEFAULTS["workbench"]["profile"]
    if merged["domainProfile"] != "ad" and merged["profile"] == "医学研究文献":
        merged["profile"] = PREF_DEFAULTS["workbench"]["profile"]
    from qyunslation.pipeline.model_profiles import PROFILES

    model = PROFILES.get(str(merged.get("modelProfileId") or ""))
    if model is None or model.role != "translator":
        merged["modelProfileId"] = PREF_DEFAULTS["workbench"]["modelProfileId"]
    merged["bilingual"] = bool(merged.get("bilingual"))
    return merged


def _upload_session_expired(record: UploadSession) -> bool:
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _owned_upload_session(
    session: Session, *, upload_id: str, identity: IdentityContext
) -> UploadSession:
    tenant = _tenant_bundle(session, identity)
    record = session.get(UploadSession, upload_id)
    if record is None or record.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="upload session not found")
    if record.actor_sub != identity.user_sub:
        raise HTTPException(status_code=404, detail="upload session not found")
    return record


def reconcile_stale_runs(session: Session) -> int:
    """Mark ledger runs interrupted when heartbeat expired and no live executor."""
    from qyunslation.workbench.heartbeat import is_heartbeat_stale, mark_interrupted
    from qyunslation.workbench.runner import get_pdf2zh_task_state, is_pdf2zh_task

    touched = 0
    rows = list(
        session.scalars(
            select(TranslationRunRecord).where(
                TranslationRunRecord.status.in_(
                    ("queued", "scanning", "translating", "rendering")
                )
            )
        )
    )
    for run in rows:
        alive = False
        if run.external_task_id:
            if is_pdf2zh_task(run.external_task_id):
                alive = get_pdf2zh_task_state(run.external_task_id) is not None
            else:
                try:
                    from qyunslation.server import get_translation_service

                    alive = bool(
                        get_translation_service().get_task_state(run.external_task_id)
                    )
                except Exception:
                    alive = False
        if alive:
            continue
        if is_heartbeat_stale(run):
            mark_interrupted(
                session,
                run,
                reason="translation heartbeat expired; use resume to continue",
            )
            touched += 1
    return touched


def _apply_resume_snapshot(session: Session, run: TranslationRunRecord) -> None:
    from qyunslation.pipeline.event_store import completed_stages, pending_stages

    planned = [
        "validation",
        "structure",
        "ocr",
        "text",
        "table_figure",
        "layout",
        "qa",
        "review",
        "export",
    ]
    done = completed_stages(session, run_id=run.id, generation=run.generation)
    pending = pending_stages(
        session, run_id=run.id, generation=run.generation, planned=planned
    )
    snap = dict(run.settings_snapshot or {})
    snap["resume_completed_stages"] = sorted(done)
    snap["resume_pending_stages"] = pending
    run.settings_snapshot = snap


def _normalize_language_pair(
    source_language: str | None,
    target_language: str | None,
    direction: str | None,
) -> tuple[str, str, str]:
    """Return one canonical language pair while retaining direction compatibility."""
    source = (source_language or "").strip()
    target = (target_language or "").strip()
    if source or target:
        if not source or not target:
            raise HTTPException(status_code=422, detail="source_language and target_language are required together")
        if source not in SUPPORTED_LANGUAGES or target not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=422, detail="unsupported language")
        if source == target:
            raise HTTPException(status_code=422, detail="source and target language must differ")
        canonical = next(
            name for name, pair in SUPPORTED_DIRECTIONS.items() if pair == (source, target)
        )
        return source, target, canonical
    canonical = (direction or "English → 简体中文").strip()
    pair = SUPPORTED_DIRECTIONS.get(canonical)
    if pair is None:
        raise HTTPException(status_code=422, detail="unsupported language direction")
    return pair[0], pair[1], canonical


def _preflight_dict(record: PreflightRecord) -> dict[str, Any]:
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        # SQLite returns timezone-aware columns as naive values.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    expired = expires_at <= datetime.now(timezone.utc)
    metadata = dict(record.metadata_json or {})
    recommended = dict(metadata.get("recommended", {}))
    return {
        "id": record.id,
        "state": "expired" if expired else record.status,
        "filename": record.source_filename,
        "format": record.source_format,
        "size_bytes": record.size_bytes,
        "sha256": record.source_sha256,
        "manifest_summary": metadata.get("manifest_summary", {}),
        "capabilities": metadata.get("capabilities", {}),
        "issues": metadata.get("issues", []),
        "recommended": recommended,
        "source_language": recommended.get("source_language"),
        "target_language": recommended.get("target_language"),
        "domain_profile": recommended.get("domain_profile") or "general",
        "document_classification": record.document_classification or metadata.get("document_classification") or "internal",
        "model_profile_id": record.model_profile_id or metadata.get("model_profile_id"),
        "reused": False,
        "expires_at": expires_at.isoformat(),
        "created_at": record.created_at.isoformat(),
    }


async def _refresh_language_hint(
    existing: PreflightRecord, reused: dict[str, Any], source_language: str | None
) -> None:
    """A reused pre-check keeps its old issues, including the language hint computed for the language chosen
    then. When the person now picks another source language, recompute only that hint from the stored file."""
    stored = (reused.get("recommended") or {}).get("source_language")
    if not source_language or source_language == stored:
        return
    path = _preflight_path(existing)
    if not path.is_file():
        return
    probe = await asyncio.to_thread(probe_document, path, f".{existing.source_format}", source_language)
    fresh = [item for item in probe.issues if item.get("code") == "LANGUAGE_MISMATCH"]
    reused["issues"] = [
        item for item in reused.get("issues") or [] if item.get("code") != "LANGUAGE_MISMATCH"
    ] + fresh


@router.post("/preflights", status_code=201)
async def create_preflight(
    file: UploadFile = File(...),
    direction: str = Form("English → 简体中文"),
    profile: str = Form("临床研究文档"),
    source_language: str | None = Form(default=None),
    target_language: str | None = Form(default=None),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Store a bounded upload and return a reviewable preflight; never starts translation."""
    filename = Path(file.filename or "uploaded_file").name.strip()
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="filename is required")
    suffix = Path(filename).suffix.casefold()
    if suffix not in PREFLIGHT_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="unsupported document format")
    if len(filename) > 256:
        raise HTTPException(status_code=400, detail="filename is too long")
    source_language, target_language, direction = _normalize_language_pair(
        source_language, target_language, direction
    )
    if not profile.strip() or len(profile) > 128:
        raise HTTPException(status_code=400, detail="invalid document profile")

    tenant = _tenant_bundle(session, identity)
    record_id = str(uuid.uuid4())
    relative_key = f"{tenant.id}/{record_id}{suffix}"
    root = _preflight_root().resolve()
    target = (root / relative_key).resolve()
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.upload")
    if root not in target.parents or root not in temporary.parents:
        raise HTTPException(status_code=500, detail="invalid upload destination")
    try:
        digest, size_bytes = await _stream_upload_limited(file, temporary)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="upload could not be read") from exc
    if size_bytes <= 0:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    now = datetime.now(timezone.utc)
    existing_rows = list(
        session.scalars(
            select(PreflightRecord).where(
                PreflightRecord.tenant_id == tenant.id,
                PreflightRecord.actor_sub == identity.user_sub,
                PreflightRecord.source_sha256 == digest,
                PreflightRecord.status == "ready",
            )
        )
    )
    for existing in existing_rows:
        if _preflight_used_by(session, existing.id):
            continue  # a pre-check that already has a task cannot start another; make a fresh one
        expires_at = existing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        existing_path = _preflight_path(existing)
        try:
            existing_size = existing_path.stat().st_size if existing_path.is_file() else None
        except OSError:
            existing_size = None
        if expires_at > now and existing_size == size_bytes:
            temporary.unlink(missing_ok=True)
            reused = _preflight_dict(existing)
            reused["storage_key"] = existing.storage_key
            reused["reused"] = True
            reused["source_language"] = source_language
            reused["target_language"] = target_language
            await _refresh_language_hint(existing, reused, source_language)
            return reused

    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary, target)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    issues: list[dict[str, str]] = []
    if suffix in {".png", ".jpg", ".jpeg"}:
        issues.append({"severity": "warning", "code": "IMAGE_DOCUMENT", "message": "图片文档将在翻译前执行 OCR。"})
    probe = await asyncio.to_thread(probe_document, target, suffix, source_language)
    issues.extend(probe.issues)
    record = PreflightRecord(
        id=record_id,
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        source_filename=filename,
        source_format=suffix.removeprefix(".").lower(),
        source_sha256=digest,
        size_bytes=size_bytes,
        status="blocked" if probe.blocked else "ready",
        metadata_json={
            "mime": mime,
            "manifest_summary": {
                "pages": None,
                "objects": None,
                "scan_detected": suffix in {".png", ".jpg", ".jpeg"},
                **probe.manifest_summary,
            },
            "capabilities": {"source_read_only": True, "bilingual_output": True, "formal_export": False},
            "issues": issues,
            "recommended": {
                "direction": direction,
                "profile": profile.strip(),
                "source_language": source_language,
                "target_language": target_language,
            },
        },
        storage_key=relative_key,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=PREFLIGHT_TTL_HOURS),
    )
    session.add(record)
    session.flush()
    record_dict = _preflight_dict(record)
    record_dict["storage_key"] = record.storage_key
    return record_dict


@router.get("/preflights")
def list_preflights(
    limit: int = Query(default=20, ge=1, le=100),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    now = datetime.now(timezone.utc)
    stmt = (
        select(PreflightRecord)
        .where(
            PreflightRecord.tenant_id == tenant.id,
            PreflightRecord.expires_at > now,
        )
        .order_by(PreflightRecord.created_at.desc())
        .limit(limit)
    )
    if _effective_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        stmt = stmt.where(PreflightRecord.actor_sub == identity.user_sub)
    rows = list(session.scalars(stmt))
    items = []
    for row in rows:
        payload = _preflight_dict(row)
        if payload["state"] != "ready":
            continue
        payload["used_by_run_id"] = _preflight_used_by(session, row.id)
        items.append(payload)
    # Only a pre-check that no task uses can be restored as "ready to start".
    latest = next((item for item in items if item["used_by_run_id"] is None), None)
    return {"items": items, "latest": latest}


@router.get("/preflights/{preflight_id}")
def get_preflight(
    preflight_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    record = session.get(PreflightRecord, preflight_id)
    if record is None or record.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="preflight not found")
    if record.actor_sub != identity.user_sub and _effective_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        raise HTTPException(status_code=404, detail="preflight not found")
    return _preflight_dict(record)


@router.post("/preflights/{preflight_id}/copy", status_code=201)
def copy_preflight(
    preflight_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """New pre-check from the same source file, so a task can be run again with other settings."""
    tenant = _tenant_bundle(session, identity)
    record = session.get(PreflightRecord, preflight_id)
    if (
        record is None
        or record.tenant_id != tenant.id
        or (
            record.actor_sub != identity.user_sub
            and _effective_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}
        )
    ):
        raise HTTPException(status_code=404, detail="preflight not found")
    _ensure_preflight_usable(session, record, actor_sub=identity.user_sub)
    new_id = str(uuid.uuid4())
    suffix = Path(record.storage_key).suffix
    relative_key = f"{tenant.id}/{new_id}{suffix}"
    root = _preflight_root().resolve()
    target = (root / relative_key).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=500, detail="invalid copy destination")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_preflight_path(record), target)
    metadata = json.loads(json.dumps(record.metadata_json or {}))
    metadata["copied_from"] = record.id
    copy = PreflightRecord(
        id=new_id,
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        source_filename=record.source_filename,
        source_format=record.source_format,
        source_sha256=record.source_sha256,
        size_bytes=record.size_bytes,
        status="ready",
        metadata_json=metadata,
        storage_key=relative_key,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=PREFLIGHT_TTL_HOURS),
        document_classification=record.document_classification,
        model_profile_id=record.model_profile_id,
    )
    session.add(copy)
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="preflight.copy",
        extra={"preflight_id": new_id, "copied_from": record.id},
    )
    session.flush()
    payload = _preflight_dict(copy)
    payload["used_by_run_id"] = None
    return payload


@router.post("/upload-sessions", status_code=201)
def create_upload_session(
    body: UploadSessionCreateBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    filename = Path(body.filename).name.strip()
    suffix = Path(filename).suffix.casefold()
    if suffix not in PREFLIGHT_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="unsupported document format")
    now = datetime.now(timezone.utc)
    if body.expected_sha256:
        existing_rows = list(
            session.scalars(
                select(PreflightRecord).where(
                    PreflightRecord.tenant_id == tenant.id,
                    PreflightRecord.actor_sub == identity.user_sub,
                    PreflightRecord.source_sha256 == body.expected_sha256.strip().lower(),
                    PreflightRecord.status == "ready",
                    PreflightRecord.expires_at > now,
                )
            )
        )
        for existing in existing_rows:
            if _preflight_used_by(session, existing.id):
                continue
            reused = _preflight_dict(existing)
            reused["reused"] = True
            return {
                "upload_session": None,
                "reused_preflight": reused,
                "received_bytes": existing.size_bytes,
                "complete": True,
            }
    record_id = str(uuid.uuid4())
    relative_key = f"{tenant.id}/{record_id}.partial"
    root = _upload_root().resolve()
    target = (root / relative_key).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=500, detail="invalid upload destination")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"")
    record = UploadSession(
        id=record_id,
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        source_filename=filename,
        source_format=suffix.removeprefix(".").lower(),
        total_size=body.total_size,
        received_bytes=0,
        expected_sha256=(body.expected_sha256 or "").strip().lower() or None,
        storage_key=relative_key,
        status="uploading",
        metadata_json={"mime": mimetypes.guess_type(filename)[0] or "application/octet-stream"},
        expires_at=now + timedelta(hours=UPLOAD_SESSION_TTL_HOURS),
    )
    session.add(record)
    session.flush()
    payload = _upload_session_dict(record)
    payload["complete"] = False
    payload["reused_preflight"] = None
    return {"upload_session": payload, "reused_preflight": None, **payload}


@router.get("/upload-sessions/{upload_id}")
def get_upload_session(
    upload_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    record = _owned_upload_session(session, upload_id=upload_id, identity=identity)
    if _upload_session_expired(record):
        record.status = "expired"
    payload = _upload_session_dict(record)
    payload["complete"] = record.received_bytes >= record.total_size
    return payload


@router.patch("/upload-sessions/{upload_id}")
async def append_upload_session(
    upload_id: str,
    request: Request,
    content_range: str | None = Header(default=None, alias="Content-Range"),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    record = _owned_upload_session(session, upload_id=upload_id, identity=identity)
    if record.status != "uploading":
        raise HTTPException(status_code=409, detail="upload session is not accepting data")
    if _upload_session_expired(record):
        raise HTTPException(status_code=410, detail="upload session expired")
    if not content_range:
        raise HTTPException(status_code=400, detail="Content-Range header is required")
    match = _CONTENT_RANGE_RE.match(content_range.strip())
    if not match:
        raise HTTPException(status_code=400, detail="invalid Content-Range header")
    start = int(match.group("start"))
    end = int(match.group("end"))
    total = int(match.group("total"))
    if total != record.total_size:
        raise HTTPException(status_code=409, detail="upload total size mismatch")
    if start != record.received_bytes:
        raise HTTPException(
            status_code=409,
            detail=f"expected offset {record.received_bytes}, got {start}",
        )
    chunk = await request.body()
    expected_len = end - start + 1
    if len(chunk) != expected_len:
        raise HTTPException(status_code=400, detail="chunk size mismatch")
    if len(chunk) > UPLOAD_CHUNK_MAX_BYTES:
        raise HTTPException(status_code=413, detail="chunk too large")
    path = _upload_path(record)
    with path.open("r+b") as handle:
        handle.seek(start)
        handle.write(chunk)
    record.received_bytes = end + 1
    record.updated_at = datetime.now(timezone.utc)
    session.flush()
    payload = _upload_session_dict(record)
    payload["complete"] = record.received_bytes >= record.total_size
    return payload


@router.post("/upload-sessions/{upload_id}/complete", status_code=201)
async def complete_upload_session(
    upload_id: str,
    body: UploadSessionCompleteBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    record = _owned_upload_session(session, upload_id=upload_id, identity=identity)
    if record.received_bytes < record.total_size:
        raise HTTPException(status_code=409, detail="upload is incomplete")
    path = _upload_path(record)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="upload payload missing")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    digest_hex = digest.hexdigest()
    if record.expected_sha256 and record.expected_sha256 != digest_hex:
        raise HTTPException(status_code=409, detail="sha256 mismatch")
    source_language, target_language, direction = _normalize_language_pair(
        body.source_language, body.target_language, body.direction
    )
    profile = body.profile.strip()
    if not profile or len(profile) > 128:
        raise HTTPException(status_code=400, detail="invalid document profile")
    tenant = _tenant_bundle(session, identity)
    suffix = Path(record.source_filename).suffix.casefold()
    now = datetime.now(timezone.utc)
    existing_rows = list(
        session.scalars(
            select(PreflightRecord).where(
                PreflightRecord.tenant_id == tenant.id,
                PreflightRecord.actor_sub == identity.user_sub,
                PreflightRecord.source_sha256 == digest_hex,
                PreflightRecord.status == "ready",
            )
        )
    )
    for existing in existing_rows:
        expires_at = existing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now and existing.size_bytes == record.total_size:
            path.unlink(missing_ok=True)
            record.status = "completed"
            reused = _preflight_dict(existing)
            reused["reused"] = True
            reused["source_language"] = source_language
            reused["target_language"] = target_language
            await _refresh_language_hint(existing, reused, source_language)
            return reused
    preflight_id = str(uuid.uuid4())
    relative_key = f"{tenant.id}/{preflight_id}{suffix}"
    final_path = (_preflight_root().resolve() / relative_key).resolve()
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(path, final_path)
    record.status = "completed"
    preflight = PreflightRecord(
        id=preflight_id,
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        source_filename=record.source_filename,
        source_format=record.source_format,
        source_sha256=digest_hex,
        size_bytes=record.total_size,
        status="ready",
        metadata_json={
            "mime": record.metadata_json.get("mime") or "application/octet-stream",
            "manifest_summary": {
                "pages": None,
                "objects": None,
                "scan_detected": suffix in {".png", ".jpg", ".jpeg"},
            },
            "capabilities": {
                "source_read_only": True,
                "bilingual_output": True,
                "formal_export": False,
            },
            "issues": [],
            "recommended": {
                "direction": direction,
                "profile": profile,
                "source_language": source_language,
                "target_language": target_language,
            },
            "upload_session_id": record.id,
        },
        storage_key=relative_key,
        expires_at=now + timedelta(hours=PREFLIGHT_TTL_HOURS),
    )
    probe = await asyncio.to_thread(probe_document, final_path, suffix, source_language)
    if probe.blocked:
        preflight.status = "blocked"
    preflight.metadata_json = {
        **preflight.metadata_json,
        "manifest_summary": {**preflight.metadata_json["manifest_summary"], **probe.manifest_summary},
        "issues": [*preflight.metadata_json.get("issues", []), *probe.issues],
    }
    session.add(preflight)
    session.flush()
    payload = _preflight_dict(preflight)
    payload["storage_key"] = preflight.storage_key
    payload["reused"] = False
    return payload


@router.delete("/preflights/{preflight_id}", status_code=204)
def delete_preflight(
    preflight_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> Response:
    tenant = _tenant_bundle(session, identity)
    record = session.get(PreflightRecord, preflight_id)
    if record is None or record.tenant_id != tenant.id or record.actor_sub != identity.user_sub:
        raise HTTPException(status_code=404, detail="preflight not found")
    # runs reference the preflight with ON DELETE CASCADE; deleting it here would
    # silently remove every task (and its review evidence) built on this source file.
    in_use = session.scalar(
        select(TranslationRunRecord.id).where(TranslationRunRecord.preflight_id == record.id).limit(1)
    )
    if in_use is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREFLIGHT_IN_USE",
                "message": "该预检已被翻译任务引用，请删除任务而不是预检",
                "run_id": in_use,
            },
        )
    path = _preflight_path(record)
    session.delete(record)
    session.commit()
    _unlink_quietly([path])
    return Response(status_code=204)


class TranslationRunCreateBody(BaseModel):
    preflight_id: str = Field(min_length=1, max_length=36)
    direction: str | None = Field(default="English → 简体中文", max_length=64)
    source_language: str | None = Field(default=None, max_length=32)
    target_language: str | None = Field(default=None, max_length=32)
    profile: str = Field(default="临床研究文档", min_length=1, max_length=128)
    domain_profile: str = Field(default="general", max_length=32)
    bilingual: bool = True
    display_name: str | None = Field(default=None, max_length=256)
    document_classification: str | None = Field(default=None, max_length=32)
    model_profile_id: str | None = Field(default=None, max_length=128)
    term_model_profile_id: str | None = Field(default=None, max_length=128)
    # PLAN-078c: the digest the person confirmed (from /translation-runs/validate).
    config_digest: str | None = Field(default=None, max_length=64)


class PreflightPatchBody(BaseModel):
    document_classification: str | None = Field(default=None, max_length=32)
    model_profile_id: str | None = Field(default=None, max_length=128)
    term_model_profile_id: str | None = Field(default=None, max_length=128)
    source_language: str | None = Field(default=None, max_length=32)
    target_language: str | None = Field(default=None, max_length=32)
    profile: str | None = Field(default=None, max_length=128)
    domain_profile: str | None = Field(default=None, max_length=32)


class ReviewDecisionBody(BaseModel):
    decision: str = Field(min_length=1, max_length=32)
    comment: str | None = Field(default=None, max_length=2048)


class RunTermDecisionBody(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    expected_version: int = Field(ge=1)
    target_term: str | None = Field(default=None, max_length=512)
    note: str | None = Field(default=None, max_length=10000)
    scope: str = Field(default="org", max_length=32)


class RunTermBatchDecisionItem(RunTermDecisionBody):
    candidate_id: str = Field(min_length=1, max_length=36)


class RunTermBatchDecisionBody(BaseModel):
    decisions: list[RunTermBatchDecisionItem] = Field(min_length=1, max_length=200)


class AffiliationDecisionBody(BaseModel):
    expected_version: int = Field(ge=1)
    revised_text: str | None = Field(default=None, max_length=20000)


class RetryTranslationBody(BaseModel):
    pipeline: str | None = Field(default=None, max_length=32)


class UploadSessionCreateBody(BaseModel):
    filename: str = Field(min_length=1, max_length=256)
    total_size: int = Field(gt=0, le=DEFAULT_MAX_UPLOAD_BYTES)
    expected_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class UploadSessionCompleteBody(BaseModel):
    direction: str | None = Field(default="English → 简体中文", max_length=64)
    profile: str = Field(default="临床研究文档", max_length=128)
    source_language: str | None = Field(default=None, max_length=32)
    target_language: str | None = Field(default=None, max_length=32)


class ReviewDraftBody(BaseModel):
    comment: str | None = Field(default=None, max_length=2048)
    resolved_qa_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class TranslationRunPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=1000)
    reset_display_name: bool = False  # explicit "back to the original file name"
    archived: bool | None = None


# "gated" = the executor has finished and the run waits at the quality gate (QA action,
# human review, requested changes). It is not executing, so it can be archived, deleted
# or retried like any other ended run (PLAN-078a).
_RUN_EXECUTING = frozenset({"queued", "scanning", "translating", "rendering"})
_RUN_TERMINAL = frozenset(
    {"succeeded", "failed", "cancelled", "blocked", "degraded", "interrupted", "gated"}
)
_GATE_STAGE_BY_QUALITY = {
    "qa_blocked": "qa",
    "qa_unavailable": "qa",
    "review_ready": "review",
    "qa_degraded": "review",
    "changes_requested": "review",
}
_RUN_RESUMABLE = frozenset({"interrupted", "degraded", "failed", "cancelled", "blocked"})


def _run_target_language(direction: str) -> str:
    if direction == "English → 简体中文":
        return "简体中文"
    if direction == "简体中文 → English":
        return "English"
    raise HTTPException(status_code=400, detail="unsupported language direction")


def _run_stage_from_task(task_state: dict[str, Any]) -> str:
    message = str(task_state.get("status_message") or "").casefold()
    if task_state.get("download_ready"):
        return "export"
    if any(token in message for token in ("解析", "结构", "ingest", "ocr")):
        return "structure"
    if any(token in message for token in ("版式", "渲染", "render")):
        return "layout"
    if any(token in message for token in ("qa", "质量", "术语")):
        return "qa"
    return "text"


def _artifact_root() -> Path:
    raw = (os.environ.get("QYUNSLATION_ARTIFACT_ROOT") or "var/artifacts").strip()
    root = Path(raw)
    return root if root.is_absolute() else Path.cwd() / root


def _artifact_path(artifact: TranslationArtifact) -> Path:
    root = _artifact_root().resolve()
    path = (root / artifact.storage_key).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=500, detail="invalid artifact storage key")
    return path


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _artifact_dict(artifact: TranslationArtifact, run_id: str) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "run_id": run_id,
        "kind": artifact.kind,
        "file_type": artifact.file_type,
        "filename": artifact.filename,
        "media_type": artifact.media_type,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "formal_export": artifact.formal_export,
        "created_at": artifact.created_at.isoformat(),
        "download_url": f"/api/v1/translation-runs/{run_id}/artifacts/{artifact.id}",
    }


def _materialize_artifacts(
    session: Session, *, run: TranslationRunRecord, task_state: dict[str, Any]
) -> None:
    """Copy trusted runner outputs into an opaque, tenant-scoped artifact root."""
    outputs: list[tuple[str, str, str, bool]] = []
    for file_type, meta in (task_state.get("downloadable_files") or {}).items():
        if isinstance(meta, dict):
            outputs.append(("formal", str(file_type), str(meta.get("path") or ""), True))
    for identifier, meta in (task_state.get("attachment_files") or {}).items():
        if isinstance(meta, dict):
            outputs.append(("attachment", str(identifier), str(meta.get("path") or ""), False))
    for kind, key, source_raw, formal in outputs:
        source = Path(source_raw)
        if not source.is_file():
            continue
        artifact_key = f"{kind}:{key}"[:128]
        existing = session.scalar(
            select(TranslationArtifact).where(
                TranslationArtifact.run_id == run.id,
                TranslationArtifact.artifact_key == artifact_key,
            )
        )
        if existing is not None:
            continue
        filename = Path(str((task_state.get("original_filename") or source.name))).name
        meta = (
            (task_state.get("downloadable_files") or {}).get(key)
            if kind == "formal"
            else (task_state.get("attachment_files") or {}).get(key)
        ) or {}
        filename = Path(str(meta.get("filename") or filename)).name
        if not filename or filename in {".", ".."}:
            filename = f"{key}.bin"
        artifact_id = str(uuid.uuid4())
        suffix = Path(filename).suffix[:24]
        storage_key = f"{run.tenant_id}/{run.id}/{artifact_id}{suffix}"
        target = (_artifact_root() / storage_key).resolve()
        root = _artifact_root().resolve()
        if root not in target.parents:
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            sha256, size = _sha256_file(target)
        except (OSError, ValueError):
            if target.is_file():
                target.unlink()
            continue
        artifact_kind = kind
        if formal and (getattr(run, "quality_state", None) or "draft") == "legacy_unverified":
            artifact_kind = "legacy"
        session.add(
            TranslationArtifact(
                id=artifact_id,
                run_id=run.id,
                tenant_id=run.tenant_id,
                artifact_key=artifact_key,
                kind=artifact_kind,
                file_type=key,
                filename=filename[:256],
                media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                storage_key=storage_key,
                size_bytes=size,
                sha256=sha256,
                formal_export=formal,
            )
        )
    session.flush()


def _document_profile_from_run(run: TranslationRunRecord) -> str:
    snap = run.settings_snapshot or {}
    return str(snap.get("profile") or "临床研究文档")


def _inspect_run_outputs(
    session: Session,
    run: TranslationRunRecord,
    runner_state: dict[str, Any] | None,
) -> tuple[list[Any], dict[str, Any] | None, dict[str, Any] | None]:
    """PLAN-071e/h + 076i：PDF 与非 PDF 产物的 QA 取证。"""
    from qyunslation.pipeline.ad_inspection import inspect_ad_text_pair
    from qyunslation.pipeline.ad_text_extract import extract_preflight_text, extract_translated_text
    from qyunslation.pipeline.qa.engine import QaFinding
    from qyunslation.pipeline.qa.pdf_inspect import inspect_pdf_pair

    domain_ad = str((run.settings_snapshot or {}).get("domain_profile") or "general").casefold() == "ad"
    files = (runner_state or {}).get("downloadable_files") or {}
    mono: Path | None = None
    dual: Path | None = None
    text_artifact: Path | None = None
    for key, meta in files.items():
        if not isinstance(meta, dict) or not meta.get("path"):
            continue
        path = Path(str(meta["path"]))
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        if suffix == ".pdf":
            if "dual" in str(key).casefold() or "dual" in path.name.casefold():
                dual = dual or path
            else:
                mono = mono or path
        elif suffix in {".txt", ".md", ".docx"} and text_artifact is None:
            if "dual" not in str(key).casefold():
                text_artifact = path
    preflight = session.get(PreflightRecord, run.preflight_id)
    if preflight is None:
        return [], None, None
    try:
        source_path = _preflight_path(preflight)
    except HTTPException:
        return [], None, None

    if mono is None and dual is None and not (domain_ad and text_artifact):
        if domain_ad:
            findings = [
                QaFinding(
                    category="ad",
                    severity="unavailable",
                    code="AD_QA_SOURCE_UNAVAILABLE",
                    message="AD 任务缺少可 QA 的译文产物",
                )
            ]
            return findings, {"status": "unavailable"}, None
        return [], None, None

    target = str(getattr(run, "direction", "") or "").split("→")[-1]
    facts: dict[str, Any] = {}
    findings: list[Any] = []
    summary: dict[str, Any] = {}
    if mono is not None or dual is not None:
        findings, summary = inspect_pdf_pair(
            source_path=source_path,
            mono_path=mono,
            dual_path=dual,
            target_is_chinese=("中" in target or target.casefold().startswith("zh") or not target),
            facts_out=facts,
        )
    elif domain_ad and text_artifact is not None:
        source_text = extract_preflight_text(source_path)
        target_text = extract_translated_text(text_artifact)
        ad_findings, snapshot, _ = inspect_ad_text_pair(
            source_text=source_text,
            target_text=target_text,
            direction_label=run.direction,
            settings_snapshot=run.settings_snapshot,
        )
        if snapshot.get("semantic_degraded"):
            snapshot = dict(snapshot)
        # Always leave an inspection record so a clean AD run still has a
        # persisted qa_item (the auto-QA idempotency guard relies on it).
        ad_findings = list(ad_findings)
        ad_findings.append(
            QaFinding(
                category="consistency",
                severity="info",
                code="QA_INSPECTION_SUMMARY",
                message="确定性 QA 取证摘要",
                evidence={
                    "artifact": text_artifact.name,
                    "source_chars": len(source_text),
                    "target_chars": len(target_text),
                    "ad_findings": len(ad_findings),
                },
            )
        )
        return ad_findings, snapshot, None

    snapshot: dict[str, Any] | None = None
    semantic_degraded = False
    if facts:
        if domain_ad:
            ad_findings, snapshot, semantic_degraded = inspect_ad_text_pair(
                source_text=facts["source"].text,
                target_text=facts["translated"].text,
                direction_label=run.direction,
                settings_snapshot=run.settings_snapshot,
                source_pages=facts["source"].pages,
                target_pages=facts["translated"].pages,
            )
            findings.extend(ad_findings)
        else:
            try:
                from qyunslation.pipeline.term_snapshot import (
                    build_term_snapshot,
                    check_terms_in_translation,
                )

                snapshot = build_term_snapshot(
                    session,
                    tenant_id=run.tenant_id,
                    project_id=None,
                    source_text=facts["source"].text,
                    document_profile=_document_profile_from_run(run),
                )
                findings.extend(
                    check_terms_in_translation(
                        snapshot,
                        facts["translated"].text,
                        source_pages=facts["source"].pages,
                        translated_pages=facts["translated"].pages,
                    )
                )
            except Exception:
                snapshot = None
    if snapshot is not None:
        snapshot = dict(snapshot)
        snapshot["semantic_degraded"] = semantic_degraded
    findings.append(
        QaFinding(
            category="consistency",
            severity="info",
            code="QA_INSPECTION_SUMMARY",
            message="确定性 QA 取证摘要",
            evidence=summary,
        )
    )
    return findings, snapshot, facts if facts else None


_EXECUTOR_OUTPUT_DIR = "executor-outputs"


def _executor_output_dir(run: TranslationRunRecord) -> Path | None:
    try:
        from qyunslation.workbench.runner import get_pdf2zh_runner

        return (
            get_pdf2zh_runner()._run_dir(
                tenant_id=run.tenant_id, run_id=run.id, generation=run.generation
            )
            / _EXECUTOR_OUTPUT_DIR
        )
    except Exception:
        return None


def _persist_executor_outputs(run: TranslationRunRecord, task_state: dict[str, Any]) -> None:
    """Copy in-memory (Office/image) executor outputs beside the run.

    The Office service keeps outputs in memory and temp dirs and releases them after a
    TTL or restart. A run waiting at the quality gate may be approved long after that,
    so the files and their manifest must outlive the executor (PLAN-078a, H2).
    """
    base = _executor_output_dir(run)
    if base is None or (base / "manifest.json").is_file():
        return
    manifest: dict[str, Any] = {
        "downloadable_files": {},
        "attachment_files": {},
        "original_filename": task_state.get("original_filename"),
    }
    for group in ("downloadable_files", "attachment_files"):
        for key, meta in (task_state.get(group) or {}).items():
            if not isinstance(meta, dict) or not meta.get("path"):
                continue
            source = Path(str(meta["path"]))
            if not source.is_file():
                continue
            safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", str(key))[:64] or "file"
            target = base / group / safe_key / Path(str(meta.get("filename") or source.name)).name
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            except OSError:
                logger.warning("could not persist executor output %s", source, exc_info=True)
                continue
            manifest[group][str(key)] = {
                "path": str(target.relative_to(base)),
                "filename": target.name,
            }
    if not manifest["downloadable_files"]:
        return
    (base / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _persisted_executor_state(run: TranslationRunRecord) -> dict[str, Any] | None:
    base = _executor_output_dir(run)
    if base is None or not (base / "manifest.json").is_file():
        return None
    try:
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    state: dict[str, Any] = {
        "download_ready": True,
        "is_processing": False,
        "error_flag": False,
        "persisted": True,
        "original_filename": manifest.get("original_filename"),
    }
    for group in ("downloadable_files", "attachment_files"):
        state[group] = {
            key: {"path": str(base / meta["path"]), "filename": meta.get("filename")}
            for key, meta in (manifest.get(group) or {}).items()
            if isinstance(meta, dict) and meta.get("path")
        }
    if not any(Path(meta["path"]).is_file() for meta in state["downloadable_files"].values()):
        return None
    return state


def _clear_persisted_executor_outputs(run: TranslationRunRecord) -> None:
    base = _executor_output_dir(run)
    if base is not None and base.is_dir():
        shutil.rmtree(base, ignore_errors=True)


def _maybe_run_auto_qa(
    session: Session,
    run: TranslationRunRecord,
    runner_state: dict[str, Any] | None = None,
) -> None:
    """PLAN-071e：layout 完成后跑确定性 QA，写入 qa_item 与 quality_state。"""
    if (run.quality_state or "draft") != "draft":
        # Only the evaluators move a run off "draft"; a run that already has a verdict
        # must not be re-evaluated on every poll (it floods the event ledger).
        return
    existing = session.scalar(
        select(QaItem.id).where(
            QaItem.run_id == run.id,
            QaItem.generation == run.generation,
            QaItem.is_current.is_(True),
        ).limit(1)
    )
    if existing:
        return
    _run_qa_pass(session, run, runner_state, trigger="auto")


_CLOSING_ACTIONS = frozenset(
    {"grant_waiver", "revoke_waiver", "confirm_false_positive", "reject_false_positive", "acknowledge"}
)
_CLOSED_BY = frozenset({"grant_waiver", "confirm_false_positive", "acknowledge"})
_QA_GATE_STATES = frozenset({"qa_blocked", "review_ready", "qa_degraded", "qa_unavailable"})


def _current_output_digest(session: Session, run: TranslationRunRecord) -> str | None:
    """Digest of the output the run's current verdict was produced for."""
    from qyunslation.persist.models import QaCheckRound

    return session.scalar(
        select(QaCheckRound.artifact_digest)
        .where(
            QaCheckRound.run_id == run.id,
            QaCheckRound.generation == run.generation,
            QaCheckRound.status == "succeeded",
        )
        .order_by(QaCheckRound.round_no.desc())
        .limit(1)
    )


def _qa_dispositions_by_fingerprint(
    session: Session, run: TranslationRunRecord
) -> dict[str, list[QaDisposition]]:
    rows = session.scalars(
        select(QaDisposition)
        .where(QaDisposition.run_id == run.id, QaDisposition.generation == run.generation)
        .order_by(QaDisposition.created_at, QaDisposition.id)
    )
    grouped: dict[str, list[QaDisposition]] = {}
    for row in rows:
        grouped.setdefault(row.fingerprint, []).append(row)
    return grouped


def _effective_item_state(
    history: list[QaDisposition], digest: str | None
) -> dict[str, Any]:
    """What the dispositions say about one finding *for the current output*.

    Only dispositions made against the same output count; an exception granted for earlier
    output never silently covers different output.
    """
    valid = [row for row in history if row.artifact_digest == digest]
    closing = next((row for row in reversed(valid) if row.action in _CLOSING_ACTIONS), None)
    report = next((row for row in reversed(valid) if row.action == "report_false_positive"), None)
    closed = closing is not None and closing.action in _CLOSED_BY
    pending_report = (
        report is not None and not closed and (closing is None or closing.created_at < report.created_at)
    )
    if closed:
        status = {
            "grant_waiver": "waived",
            "confirm_false_positive": "false_positive_confirmed",
            "acknowledge": "acknowledged",
        }[closing.action]
    elif pending_report:
        status = "false_positive_reported"
    else:
        status = "open"
    last = valid[-1] if valid else None
    return {
        "status": status,
        "closed": closed,
        "pending_report": report if pending_report else None,
        "last": last,
        "closing": closing,
        "previous": bool(history) and not valid,
    }


def _reconcile_with_dispositions(session: Session, run: TranslationRunRecord) -> None:
    """Recompute what is still open after a check or a disposition, and the verdict that follows.

    ``qa_summary.blocker`` stays what the checker found; ``open_blocker`` is what still stands
    between the run and delivery once valid dispositions are applied. The delivery gate reads
    the latter. Nothing here deletes or edits a finding.
    """
    session.flush()
    items = list(
        session.scalars(
            select(QaItem).where(
                QaItem.run_id == run.id,
                QaItem.generation == run.generation,
                QaItem.is_current.is_(True),
            )
        )
    )
    digest = _current_output_digest(session, run)
    grouped = _qa_dispositions_by_fingerprint(session, run)
    open_blockers = waived = confirmed = acknowledged = unavailable = 0
    for item in items:
        state = _effective_item_state(grouped.get(_item_fingerprint(item), []), digest)
        if item.severity == "blocker":
            if state["closed"]:
                waived += state["status"] == "waived"
                confirmed += state["status"] == "false_positive_confirmed"
            else:
                open_blockers += 1
        elif item.severity == "unavailable":
            unavailable += 1
        elif item.severity == "warning" and state["status"] == "acknowledged":
            acknowledged += 1
    summary = dict(run.qa_summary or {})
    summary.update(
        {"open_blocker": open_blockers, "waived": waived, "false_positive_confirmed": confirmed,
         "acknowledged": acknowledged}
    )
    run.qa_summary = summary
    if run.status != "gated" or (run.quality_state or "draft") not in _QA_GATE_STATES:
        return
    semantic_degraded = bool((run.term_summary or {}).get("semantic_degraded")) or any(
        item.code == "AD_QA_DEGRADED" for item in items
    )
    if open_blockers:
        new_state = "qa_blocked"
    elif unavailable:
        new_state = "qa_unavailable"
    elif semantic_degraded:
        new_state = "qa_degraded"
    else:
        new_state = "review_ready"
    if new_state != run.quality_state:
        run.quality_state = new_state
        run.stage = _GATE_STAGE_BY_QUALITY.get(new_state, run.stage)
        run.updated_at = datetime.now(timezone.utc)
        try:
            from qyunslation.pipeline.event_store import persist_buffer
            from qyunslation.pipeline.events import StageEventBuffer

            buf = StageEventBuffer()
            if new_state == "review_ready":
                buf.emit("qa", "completed", message="质量问题已处理完毕，无未处理的阻断项", progress=100.0)
                buf.emit("review", "running", message="等待人工审校")
            elif new_state == "qa_blocked":
                buf.emit("qa", "blocked", message=f"仍有 {open_blockers} 项阻断问题未处理", progress=100.0)
            persist_buffer(session, run_id=run.id, generation=run.generation, buffer=buf)
        except Exception:
            pass


class StaleQaResult(Exception):
    """The output being checked changed while the check ran; its verdict must not be stored."""


def _artifact_digest(state: dict[str, Any] | None) -> str | None:
    """Digest of the output files a check looks at; None when there is nothing to hash."""
    files = (state or {}).get("downloadable_files") or {}
    digest = hashlib.sha256()
    seen = False
    for key in sorted(files):
        meta = files[key]
        path = Path(str(meta.get("path") or "")) if isinstance(meta, dict) else None
        if path is None or not path.is_file():
            continue
        seen = True
        digest.update(str(key).encode("utf-8"))
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    return digest.hexdigest() if seen else None


def _finding_location(finding: Any, info: Any) -> dict[str, Any]:
    location = dict(getattr(finding, "location", None) or {})
    location.setdefault("anchors", [])
    if not location["anchors"]:
        location.setdefault(
            "unlocatable_reason",
            info.unlocatable_reason if info.locatable == "none" else "检查没有返回具体位置",
        )
    return location


def _new_qa_item(run: TranslationRunRecord, finding: Any, *, round_id: str | None, trigger: str) -> QaItem:
    from qyunslation.pipeline.qa import registry

    info = registry.rule_for(finding.code)
    evidence = dict(finding.evidence or {})
    evidence.setdefault("direction", run.direction)
    evidence.setdefault(
        "prompt_version",
        dict((run.settings_snapshot or {}).get("prompt_snapshot") or {}).get("version"),
    )
    evidence.setdefault("rule_version", registry.rule_set_version())
    evidence.setdefault("repair_attempt", 0)
    evidence.setdefault("trigger", trigger)
    location = _finding_location(finding, info)
    return QaItem(
        run_id=run.id,
        generation=run.generation,
        category=finding.category,
        severity=finding.severity,
        code=finding.code,
        message=finding.message,
        object_id=finding.object_id,
        evidence_json=evidence,
        round_id=round_id,
        fingerprint=registry.fingerprint(finding.code, finding.object_id, evidence, location),
        location_json=location,
        rule_class=info.rule_class,
        is_current=True,
    )


_DIFF_SEVERITIES = {"blocker", "unavailable", "warning"}


def _item_fingerprint(item: QaItem) -> str:
    from qyunslation.pipeline.qa import registry

    return item.fingerprint or registry.fingerprint(
        item.code, item.object_id, item.evidence_json, item.location_json
    )


def _swap_current_items(
    session: Session, run: TranslationRunRecord, new_items: list[QaItem]
) -> dict[str, Any]:
    """Replace the run's current verdict with ``new_items`` and describe what changed.

    Older items are kept as history (is_current = False); nothing is deleted.
    """
    from qyunslation.pipeline.qa import registry

    previous = list(
        session.scalars(
            select(QaItem).where(
                QaItem.run_id == run.id,
                QaItem.generation == run.generation,
                QaItem.is_current.is_(True),
            )
        )
    )
    baseline = "previous_round" if previous else None
    if not previous:
        origin = (run.settings_snapshot or {}).get("revision_of") or {}
        if origin.get("run_id"):
            previous_version = list(
                session.scalars(
                    select(QaItem).where(
                        QaItem.run_id == origin["run_id"],
                        QaItem.generation == int(origin.get("generation") or 1),
                        QaItem.is_current.is_(True),
                    )
                )
            )
            if previous_version:
                baseline = "previous_version"
                previous = []  # nothing of *this* version to retire
                compare = previous_version
            else:
                compare = []
        else:
            compare = []
    else:
        compare = previous
    old = {_item_fingerprint(i): i for i in compare if i.severity in _DIFF_SEVERITIES}
    new = {i.fingerprint: i for i in new_items if i.severity in _DIFF_SEVERITIES}

    def describe(item: QaItem) -> dict[str, Any]:
        return {
            "code": item.code,
            "fingerprint": _item_fingerprint(item),
            "title": registry.rule_for(item.code).title,
            "severity": item.severity,
        }

    for item in previous:
        item.is_current = False
    for item in new_items:
        session.add(item)
    return {
        "baseline": baseline,
        "new": len([fp for fp in new if fp not in old]),
        "resolved": len([fp for fp in old if fp not in new]),
        "persisting": len([fp for fp in new if fp in old]),
        "new_items": [describe(new[fp]) for fp in new if fp not in old][:20],
        "resolved_items": [describe(old[fp]) for fp in old if fp not in new][:20],
    }


def _run_qa_pass(
    session: Session,
    run: TranslationRunRecord,
    runner_state: dict[str, Any] | None = None,
    *,
    trigger: str = "auto",
    round_row: Any | None = None,
) -> None:
    """One QA evaluation for the run's current output: first check and re-check share it."""
    from qyunslation.pipeline.qa import (
        QaFinding,
        quality_state_from_findings,
        run_deterministic_qa,
        summarize,
    )
    from qyunslation.pipeline.qa.term_review import term_gate_mode

    if runner_state is None and run.external_task_id:
        try:
            from qyunslation.workbench.runner import get_pdf2zh_task_state

            runner_state = get_pdf2zh_task_state(run.external_task_id)
        except Exception:
            runner_state = None
    if runner_state is None:
        runner_state = _persisted_executor_state(run)
    digest_before = _artifact_digest(runner_state)

    inspected, term_snapshot, facts = _inspect_run_outputs(session, run, runner_state)
    if term_snapshot is not None:
        run.term_summary = term_snapshot
    preflight = session.get(PreflightRecord, run.preflight_id)
    if facts and preflight is not None:
        try:
            from qyunslation.workbench.term_extract import extract_candidates_from_text

            extract_candidates_from_text(
                session,
                run=run,
                preflight=preflight,
                source_text=facts["source"].text,
                translated_text=facts["translated"].text,
                require_structured_model=True,
            )
        except Exception as exc:
            run.term_summary = {
                **dict(run.term_summary or {}),
                "extraction_status": "degraded",
                "degradation_reason": type(exc).__name__,
            }
            # The checker (term model / evidence) failed; the translation itself was not judged.
            inspected.append(
                QaFinding(
                    category="terminology",
                    severity="unavailable",
                    code="TERM_EXTRACTION_DEGRADED",
                    message="术语抽取服务未能完成检查（不代表译文有问题），服务恢复后请重新检查",
                    evidence={"reason": type(exc).__name__},
                )
            )
    if term_gate_mode() == "shadow":
        # Shadow must be harmless: a bug here may not turn a healthy QA round into a failed one.
        try:
            _term_review_findings(session, run, inspected)
        except Exception:
            logger.warning("plan079 shadow evaluation failed for run %s", run.id, exc_info=True)
    else:
        # ``enforce`` fails closed: an error fails the round ("check not completed"), never a silent pass.
        inspected.extend(_term_review_findings(session, run, inspected))
    findings = run_deterministic_qa(
        manifest={"objects": [{"id": "placeholder"}]} if run.manifest_version else {},
        term_summary=run.term_summary,
        settings_snapshot={**(run.settings_snapshot or {}), "generation": run.generation},
        translated_text_sample=None,
        logo_present=None,
    )
    findings.extend(inspected)
    if _artifact_digest(runner_state) != digest_before:
        # The output was replaced while we were checking it (e.g. a resume): do not store a
        # verdict for output that no longer exists.
        raise StaleQaResult()
    diff = _swap_current_items(
        session,
        run,
        [
            _new_qa_item(run, finding, round_id=getattr(round_row, "id", None), trigger=trigger)
            for finding in findings
        ],
    )
    if round_row is not None:
        from qyunslation.pipeline.qa import registry as _registry

        round_row.rule_set_version = _registry.rule_set_version()
        round_row.artifact_digest = digest_before
        round_row.diff_json = diff
    run.qa_summary = summarize(findings)
    semantic_degraded = bool((term_snapshot or {}).get("semantic_degraded"))
    run.quality_state = quality_state_from_findings(findings, semantic_degraded=semantic_degraded)
    run.stage = _GATE_STAGE_BY_QUALITY.get(run.quality_state, "review")
    run.updated_at = datetime.now(timezone.utc)
    # Dispositions made against this same output (waivers, confirmed false positives) still apply.
    _reconcile_with_dispositions(session, run)
    try:
        from qyunslation.pipeline.event_store import persist_buffer
        from qyunslation.pipeline.events import StageEventBuffer

        buf = StageEventBuffer()
        summary = run.qa_summary or {}
        blockers = int(summary.get("blocker") or 0)
        unavailable = int(summary.get("unavailable") or 0)
        if trigger == "auto":
            buf.emit("layout", "completed", message="版式完成")
        prefix = "重新检查：" if trigger == "requalify" else ""
        if diff.get("baseline"):
            round_no = getattr(round_row, "round_no", None)
            label = f"第 {round_no} 轮检查：" if round_no else prefix
            buf.emit(
                "qa",
                "running",
                message=f"{label}新增 {diff['new']}、已解决 {diff['resolved']}、仍存在 {diff['persisting']}",
            )
        if run.quality_state == "qa_blocked":
            buf.emit("qa", "blocked", message=f"{prefix}QA 拦截 {blockers} 项", progress=100.0)
        elif run.quality_state == "qa_unavailable":
            buf.emit(
                "qa",
                "blocked",
                message=f"{prefix}质量检查未完成（{unavailable} 项检查无法运行），不代表译文有问题",
                progress=100.0,
            )
        else:
            buf.emit("qa", "completed", message=f"{prefix}确定性 QA 通过", progress=100.0)
            buf.emit("review", "running", message="等待人工审校")
        persist_buffer(session, run_id=run.id, generation=run.generation, buffer=buf)
    except Exception:
        pass


def _record_round_failure(
    session: Session, run: TranslationRunRecord, error_name: str, round_row: Any | None = None
) -> None:
    """The check itself crashed: say so, instead of leaving the run "checking" forever."""
    from qyunslation.pipeline.qa import QaFinding

    failure = QaFinding(
        category="integrity",
        severity="unavailable",
        code="QA_ROUND_FAILED",
        message="质量检查执行失败（系统错误，不代表译文有问题），请重新检查；反复出现请联系管理员",
        evidence={"error": error_name},
    )
    _swap_current_items(
        session,
        run,
        [_new_qa_item(run, failure, round_id=getattr(round_row, "id", None), trigger="failure")],
    )
    run.qa_summary = {"blocker": 0, "unavailable": 1, "warning": 0, "info": 0}
    run.quality_state = "qa_unavailable"
    run.stage = "qa"
    run.updated_at = datetime.now(timezone.utc)


def _execute_qa_round(session: Session, run: TranslationRunRecord, round_row: Any) -> None:
    """Run one registered round (exactly one worker can claim it)."""
    from qyunslation.pipeline.qa import rounds

    if not rounds.claim_round(session, round_row.id):
        return
    if (
        run.status != "gated"
        or run.generation != round_row.generation
        or (run.quality_state or "draft") != "draft"
    ):
        # The run moved on (discarded, retried, deleted...); a stale verdict must not land.
        rounds.finish_round(session, round_row.id, ok=False, error_code="superseded")
        return
    try:
        _run_qa_pass(session, run, None, trigger=round_row.trigger, round_row=round_row)
        rounds.finish_round(session, round_row.id, ok=True)
    except StaleQaResult:
        # Output changed under the check; the run will be checked again once it settles.
        rounds.finish_round(session, round_row.id, ok=False, error_code="output_changed")
    except Exception as exc:
        logger.exception("QA round failed for run %s", run.id)
        _record_round_failure(session, run, type(exc).__name__, round_row)
        rounds.finish_round(session, round_row.id, ok=False, error_code=type(exc).__name__[:64])


def _execute_qa_round_background(run_id: str, round_id: str) -> None:
    """Worker entry point: own session, commit when done."""
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.models import QaCheckRound

    if persist_db.SessionLocal is None:
        return
    with persist_db.SessionLocal() as session:
        try:
            run = session.get(TranslationRunRecord, run_id)
            round_row = session.get(QaCheckRound, round_id)
            if run is None or round_row is None:
                return
            _execute_qa_round(session, run, round_row)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("QA round %s could not be completed", round_id)


def _schedule_qa_round(session: Session, run: TranslationRunRecord, *, trigger: str) -> None:
    """Register a QA round and arrange for it to run; safe to call from a read path."""
    from qyunslation.pipeline.qa import rounds

    round_row, created = rounds.ensure_round(session, run.id, run.generation, trigger=trigger)
    if round_row is None or not created:
        return  # a live round already owns this check
    if rounds.qa_mode() == "inline":
        _execute_qa_round(session, run, round_row)
        return
    run_id, round_id = run.id, round_row.id

    def _dispatch(_session: Session) -> None:
        rounds.submit_background(_execute_qa_round_background, run_id, round_id)

    # Dispatch only after the request's transaction commits, so the worker can see the round.
    event.listen(session, "after_commit", _dispatch, once=True)


def _gate_run(
    session: Session, run: TranslationRunRecord, executor_state: dict[str, Any] | None
) -> None:
    """The executor has finished: park the run at the quality gate and make sure it is checked.

    Before PLAN-078a the run stayed "translating" here, so the UI kept animating progress
    and offered only "cancel" while the task was really waiting for a person. The QA pass
    also ran inside whichever GET happened to notice first; it now runs as a registered
    round (see qyunslation.pipeline.qa.rounds) so it happens once, off the request path.
    """
    run.progress = None
    if (run.stage or "") in {"", "validation", "structure", "ocr", "text", "table_figure"}:
        run.stage = "layout"
    run.status = "gated"
    if (run.quality_state or "draft") == "draft":
        has_verdict = session.scalar(
            select(QaItem.id).where(
                QaItem.run_id == run.id,
                QaItem.generation == run.generation,
                QaItem.is_current.is_(True),
            ).limit(1)
        )
        if not has_verdict:
            run.stage = "qa"
            _schedule_qa_round(session, run, trigger="auto")
    stage = _GATE_STAGE_BY_QUALITY.get(run.quality_state or "")
    if stage:
        run.stage = stage
    run.updated_at = datetime.now(timezone.utc)


def _refresh_translation_run(session: Session, run: TranslationRunRecord) -> str | None:
    if run.status == "interrupted":
        return run.degradation_reason
    if run.status == "cancelled":
        return run.degradation_reason or "translation cancelled by user"
    if run.status == "failed" and run.degradation_reason == "rejected by reviewer":
        # A reviewer's reject is terminal; the executor's lingering
        # download_ready state must not revive the run (retry needs terminal).
        return run.degradation_reason
    if not run.external_task_id:
        return None
    # PDF runs are owned by the durable non-GUI runner.  Consult its atomic
    # state file before the legacy in-memory adapter so a process restart does
    # not make the web ledger appear to lose the task.
    try:
        from qyunslation.workbench.runner import get_pdf2zh_task_state

        runner_state = get_pdf2zh_task_state(run.external_task_id)
    except Exception:
        runner_state = None
    if runner_state:
        progress_message = runner_state.get("progress_message")
        status = str(runner_state.get("status") or "degraded")
        if status in {"layout_complete", "succeeded"} and run.quality_state == "approved":
            # PLAN-071e：人工批准后才把执行器输出物化为正式产物。
            run.status = "succeeded"
            run.stage = "export"
            run.progress = 100
            run.completed_at = run.completed_at or datetime.now(timezone.utc)
            _materialize_artifacts(session, run=run, task_state=runner_state)
            run.updated_at = datetime.now(timezone.utc)
            return str(progress_message) if progress_message else None
        if status == "layout_complete":
            # PLAN-071b：执行器完成 ≠ 正式产物；禁止伪装 export/100%。
            # PLAN-078a：也不再伪装成“翻译中”，而是停在质量闸门（gated）。
            _gate_run(session, run, runner_state)
            return str(progress_message) if progress_message else None
        if status == "succeeded":
            from qyunslation.pipeline import run_pipeline_mode

            if run_pipeline_mode(run.settings_snapshot) == "v2":
                _gate_run(session, run, runner_state)
                return str(progress_message) if progress_message else None
            run.status = "succeeded"
            run.stage = "export"
            run.progress = 100
            run.completed_at = run.completed_at or datetime.now(timezone.utc)
            # Legacy path has no QA/review gate; mark unverified rather than approved.
            if (run.quality_state or "draft") in {"draft", ""}:
                run.quality_state = "legacy_unverified"
            _materialize_artifacts(session, run=run, task_state=runner_state)
        elif status in {"failed", "degraded"}:
            run.status = status
            run.stage = str(runner_state.get("stage") or "qa")
            run.progress = runner_state.get("progress_percent")
            run.degradation_reason = str(
                runner_state.get("status_message") or "translation runner failed"
            )[:512]
            run.completed_at = run.completed_at or datetime.now(timezone.utc)
        elif status == "cancelled":
            run.status = "cancelled"
            run.stage = "qa"
            run.progress = runner_state.get("progress_percent")
            run.completed_at = run.completed_at or datetime.now(timezone.utc)
        else:
            run.status = status if status in {"queued", "scanning", "translating", "rendering"} else "translating"
            run.stage = str(runner_state.get("stage") or "structure")
            progress = runner_state.get("progress_percent")
            run.progress = int(progress) if isinstance(progress, (int, float)) else None
        run.updated_at = datetime.now(timezone.utc)
        return str(progress_message) if progress_message else None
    try:
        from qyunslation.server import get_translation_service

        task_state = get_translation_service().get_task_state(run.external_task_id)
    except Exception:
        task_state = None
    if not task_state:
        # The Office service forgets finished tasks after a restart or its TTL. A run that
        # already reached the gate keeps its outputs on disk and must stay where it is.
        task_state = _persisted_executor_state(run)
    if not task_state:
        from qyunslation.workbench.heartbeat import is_heartbeat_stale, mark_interrupted

        if run.status in _RUN_EXECUTING and is_heartbeat_stale(run):
            mark_interrupted(
                session,
                run,
                reason="translation executor lost; use resume to continue",
            )
        return None
    progress_message = task_state.get("progress_message") or task_state.get("status_message")
    if task_state.get("error_flag"):
        run.status = "failed"
        run.degradation_reason = str(task_state.get("status_message") or "translation failed")[:512]
        run.stage = "qa"
    elif task_state.get("download_ready"):
        from qyunslation.pipeline import run_pipeline_mode

        if run_pipeline_mode(run.settings_snapshot) == "v2":
            # Office (docx/pptx/txt/image) executor under v2: mirror the PDF
            # runner's layout_complete handling, otherwise the run stays in
            # translating/layout forever and approval never materialises.
            if run.quality_state == "approved":
                run.status = "succeeded"
                run.stage = "export"
                run.progress = 100
                run.completed_at = run.completed_at or datetime.now(timezone.utc)
                _materialize_artifacts(session, run=run, task_state=task_state)
            else:
                if not task_state.get("persisted"):
                    _persist_executor_outputs(run, task_state)
                _gate_run(session, run, task_state)
        else:
            run.status = "succeeded"
            run.stage = "export"
            run.progress = 100
            run.completed_at = run.completed_at or datetime.now(timezone.utc)
            if (run.quality_state or "draft") in {"draft", ""}:
                run.quality_state = "legacy_unverified"
            _materialize_artifacts(session, run=run, task_state=task_state)
    elif task_state.get("is_processing"):
        run.status = "translating"
        run.stage = _run_stage_from_task(task_state)
        progress = task_state.get("progress_percent")
        run.progress = int(progress) if isinstance(progress, (int, float)) else None
    run.updated_at = datetime.now(timezone.utc)
    return str(progress_message) if progress_message else None


_FINAL_TERM_STATUSES = frozenset({"approved", "rejected", "applied"})


@dataclass
class _ListContext:
    """Everything the projection of a page of runs needs, fetched with a handful of queries
    instead of several per row (PLAN-078d)."""

    preflights: dict[str, PreflightRecord]
    artifacts: dict[str, list[TranslationArtifact]]
    terms: dict[str, list[str]]
    chains: dict[str, list[tuple[int, str]]]  # preflight id -> [(generation, run id)] ascending
    qa_checks: dict[str, Any]  # run id -> latest QaCheckRound of its current generation


def _build_list_context(session: Session, runs: list[TranslationRunRecord]) -> _ListContext:
    from qyunslation.persist.models import QaCheckRound

    run_ids = [run.id for run in runs]
    preflight_ids = list({run.preflight_id for run in runs})
    if not run_ids:
        return _ListContext({}, {}, {}, {}, {})
    preflights = {
        row.id: row for row in session.scalars(select(PreflightRecord).where(PreflightRecord.id.in_(preflight_ids)))
    }
    artifacts: dict[str, list[TranslationArtifact]] = {}
    for row in session.scalars(
        select(TranslationArtifact)
        .where(TranslationArtifact.run_id.in_(run_ids))
        .order_by(TranslationArtifact.created_at)
    ):
        artifacts.setdefault(row.run_id, []).append(row)
    terms: dict[str, list[str]] = {}
    for run_id, term_id in session.execute(
        select(DocumentTermCandidate.translation_run_id, DocumentTermCandidate.id).where(
            DocumentTermCandidate.translation_run_id.in_(run_ids),
            DocumentTermCandidate.status.not_in(_FINAL_TERM_STATUSES),
        )
    ):
        terms.setdefault(run_id, []).append(term_id)
    chains: dict[str, list[tuple[int, str]]] = {}
    for preflight_id, generation, run_id in session.execute(
        select(TranslationRunRecord.preflight_id, TranslationRunRecord.generation, TranslationRunRecord.id)
        .where(TranslationRunRecord.preflight_id.in_(preflight_ids))
        .order_by(TranslationRunRecord.generation)
    ):
        chains.setdefault(preflight_id, []).append((generation, run_id))
    generation_of = {run.id: run.generation for run in runs}
    qa_checks: dict[str, Any] = {}
    for row in session.scalars(
        select(QaCheckRound)
        .where(QaCheckRound.run_id.in_([run.id for run in runs if run.status == "gated"]))
        .order_by(QaCheckRound.round_no)
    ):
        if row.generation == generation_of.get(row.run_id):
            qa_checks[row.run_id] = row
    return _ListContext(preflights, artifacts, terms, chains, qa_checks)


def _term_review_findings(session: Session, run: TranslationRunRecord, existing: list[Any]) -> list[Any]:
    """PLAN-079: document-level term risks as C4 QA items (``enforce`` only; ``shadow`` just records them)."""
    from qyunslation.pipeline.qa.term_review import review_required_findings, term_gate_mode, violation_findings

    mode = term_gate_mode()
    if mode == "legacy":
        return []
    if str((run.term_summary or {}).get("extraction_status") or "").casefold() == "degraded":
        return []  # the term checker did not run; nothing can be concluded either way
    candidates = list(
        session.scalars(
            select(DocumentTermCandidate)
            .where(DocumentTermCandidate.translation_run_id == run.id)
            .options(selectinload(DocumentTermCandidate.occurrences))
        )
    )
    findings, overflow = review_required_findings(candidates, (run.term_summary or {}).get("terms"))
    covered = [
        str((f.evidence or {}).get("concept_id"))
        for f in existing
        if f.severity == "blocker" and f.code.startswith("TERM_") and (f.evidence or {}).get("concept_id")
    ]
    violations = violation_findings(candidates, covered)
    findings = [*findings, *violations]
    unresolved = [c.id for c in candidates if c.status not in _FINAL_TERM_STATUSES]
    # Only what the term policy itself decides. The rest of the gate (``qa_checking``, the previous round's
    # blocker count, ...) is in flux while this round runs and is identical under both policies.
    legacy_reasons = ["unresolved_terms"] if unresolved else []
    new_reasons = ["qa_blockers"] if findings else []
    summary = dict(run.term_summary or {})
    summary["gate_shadow"] = {
        "mode": mode,
        "legacy_term_reasons": legacy_reasons,
        "new_term_reasons": new_reasons,
        "review_required": len(findings) - len(violations),
        "violation_findings": len(violations),
        "review_overflow": overflow,
        "unresolved_candidates": len(unresolved),
    }
    run.term_summary = summary
    logger.info(
        "plan079.gate_shadow run_id=%s generation=%s mode=%s legacy=%s new=%s review_required=%s",
        run.id, run.generation, mode, ",".join(legacy_reasons), ",".join(new_reasons), len(findings),
    )
    return findings if mode == "enforce" else []


def _needs_refresh(run: TranslationRunRecord) -> bool:
    """Only a run whose state can still change underneath us is re-read from its executor."""
    return run.status in _RUN_EXECUTING or (
        run.status == "gated" and (run.quality_state or "draft") == "draft"
    )


def _formal_gate(
    session: Session, run: TranslationRunRecord, ctx: _ListContext | None = None
) -> dict[str, Any]:
    """Unified publication gate for QA, terms, and generations."""
    if ctx is not None:
        unresolved_terms = list(ctx.terms.get(run.id, []))
        newer = [item for item in ctx.chains.get(run.preflight_id, []) if item[0] > run.generation]
        superseding_run_id = newer[-1][1] if newer else None
        return _gate_from(run, unresolved_terms, superseding_run_id)
    unresolved_terms = list(
        session.scalars(
            select(DocumentTermCandidate.id).where(
                DocumentTermCandidate.translation_run_id == run.id,
                DocumentTermCandidate.status.not_in(_FINAL_TERM_STATUSES),
            )
        )
    )
    superseding_run_id = session.scalar(
        select(TranslationRunRecord.id)
        .where(
            TranslationRunRecord.preflight_id == run.preflight_id,
            TranslationRunRecord.generation > run.generation,
        )
        .order_by(TranslationRunRecord.generation.desc())
        .limit(1)
    )
    return _gate_from(run, unresolved_terms, superseding_run_id)


def _gate_from(
    run: TranslationRunRecord,
    unresolved_terms: list[str],
    superseding_run_id: str | None,
    *,
    mode: str | None = None,
) -> dict[str, Any]:
    summary = run.qa_summary or {}
    # PLAN-078b: findings closed by a valid disposition no longer block; raw counts stay visible.
    qa_blockers = int(summary["open_blocker"] if "open_blocker" in summary else (summary.get("blocker") or 0))
    extraction_degraded = (
        str((run.term_summary or {}).get("extraction_status") or "").casefold() == "degraded"
    )
    from qyunslation.pipeline.qa.term_review import term_gate_mode

    # PLAN-079: in ``enforce`` the delivery gate reads QA items only; undecided vocabulary candidates
    # (``unresolved_terms``) stay visible as a count but no longer block. ``legacy`` and ``shadow``
    # keep the old decision; ``shadow`` additionally records what ``enforce`` would have decided.
    gate_mode = mode or term_gate_mode()
    reasons: list[str] = []
    if qa_blockers:
        reasons.append("qa_blockers")
    if unresolved_terms and gate_mode != "enforce":
        reasons.append("unresolved_terms")
    if superseding_run_id:
        reasons.append("superseded_artifact")
    if extraction_degraded:
        reasons.append("term_extraction_degraded")
    if (run.quality_state or "") == "qa_degraded":
        reasons.append("qa_degraded")
    if (run.quality_state or "") == "qa_unavailable":
        reasons.append("qa_unavailable")
    if run.status == "gated" and (run.quality_state or "draft") == "draft":
        reasons.append("qa_checking")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "qa_blockers": qa_blockers,
        "qa_unavailable": int((run.qa_summary or {}).get("unavailable") or 0),
        "unresolved_term_count": len(unresolved_terms),
        "unresolved_term_ids": unresolved_terms,
        # Keep the response keys at zero for older clients while removing affiliation review.
        "unconfirmed_affiliation_count": 0,
        "unconfirmed_affiliation_ids": [],
        "superseding_run_id": superseding_run_id,
        "term_extraction_degraded": extraction_degraded,
        "term_gate_mode": gate_mode,
    }


def _cached_role(session: Session, identity: IdentityContext) -> str:
    """Role lookup hits the database; a list response needs it once, not once per row."""
    cache = session.info.setdefault("qy_roles", {})
    key = (identity.tenant_slug if hasattr(identity, "tenant_slug") else "", identity.user_sub)
    if key not in cache:
        cache[key] = _effective_role(session, identity)
    return cache[key]


_LIFECYCLE_BY_QUALITY = {
    "qa_blocked": "qa_action",
    "qa_unavailable": "qa_unavailable",
    "review_ready": "review",
    "qa_degraded": "review",
    "changes_requested": "changes_requested",
}


def _run_lifecycle(run: TranslationRunRecord) -> str:
    """One user-facing phase derived from status + quality_state (single source for the UI)."""
    status = run.status
    quality = run.quality_state or "draft"
    if status in _RUN_EXECUTING:
        return "executing"
    if status == "gated":
        return "qa_checking" if quality == "draft" else _LIFECYCLE_BY_QUALITY.get(quality, "review")
    if status == "succeeded":
        return "completed"
    if status in {"failed", "blocked", "degraded"}:
        return "failed"
    if status in {"interrupted", "cancelled"}:
        return status
    return "failed"


_NEXT_ACTION_BY_LIFECYCLE = {
    "qa_action": "fix_quality_issues",
    "qa_unavailable": "retry_qa",
    "changes_requested": "create_revision",
    "interrupted": "resume",
    "failed": "retry",
    "cancelled": "retry",
    "completed": "download",
}


def _qa_check_info(
    session: Session, run: TranslationRunRecord, ctx: _ListContext | None = None
) -> dict[str, Any] | None:
    if run.status != "gated":
        return None
    from qyunslation.pipeline.qa import rounds

    latest = ctx.qa_checks.get(run.id) if ctx is not None else rounds.latest_round(session, run.id, run.generation)
    if latest is None:
        return None
    return {
        "round_no": latest.round_no,
        "status": latest.status,
        "trigger": latest.trigger,
        "error_code": latest.error_code,
        "rule_set_version": latest.rule_set_version,
        "diff": latest.diff_json,
    }


def _superseding_run_id(
    session: Session, run: TranslationRunRecord, ctx: _ListContext | None = None
) -> str | None:
    if ctx is not None:
        newer = [item for item in ctx.chains.get(run.preflight_id, []) if item[0] > run.generation]
        return newer[0][1] if newer else None
    return session.scalar(
        select(TranslationRunRecord.id)
        .where(
            TranslationRunRecord.preflight_id == run.preflight_id,
            TranslationRunRecord.generation > run.generation,
        )
        .order_by(TranslationRunRecord.generation)
        .limit(1)
    )


def _run_next_action(lifecycle: str, gate: dict[str, Any]) -> str | None:
    if lifecycle == "review":
        return "review" if gate.get("passed") else "resolve_gate_items"
    return _NEXT_ACTION_BY_LIFECYCLE.get(lifecycle)


def _run_allowed_actions(
    session: Session,
    identity: IdentityContext,
    run: TranslationRunRecord,
    lifecycle: str,
    gate: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> list[str]:
    """What this caller may do now. The server enforces the same rules on each endpoint."""
    role = _cached_role(session, identity)
    writer = run.actor_sub == identity.user_sub or role in {"admin", "owner"}
    reviewer = role in {"reviewer", "term_admin", "admin", "owner"}
    ended = lifecycle not in {"executing", "qa_checking"}
    at_gate = lifecycle in {"qa_action", "qa_unavailable", "review", "changes_requested"}
    archived = run.archived_at is not None
    actions: list[str] = []

    def add(name: str, condition: bool) -> None:
        if condition and name not in actions:
            actions.append(name)

    if run.deleted_at is not None:  # in the recycle bin: only the bin's own actions
        add("restore_from_trash", writer and not run.purge_status)
        add("purge", role in {"admin", "owner"})
        return actions

    add("open", True)
    add("rename", writer)
    add("restore", writer and archived)
    add("archive", writer and ended and not archived)
    add("delete", writer and ended)
    add("cancel", writer and lifecycle == "executing")
    add("discard", writer and at_gate)
    add("resume", run.status == "interrupted")
    add("retry", ended)
    add("revise", ended and lifecycle != "completed")
    add("requalify", lifecycle in {"qa_action", "qa_unavailable", "review"})
    add("open_qa", lifecycle in {"qa_action", "qa_unavailable"})
    add("approve", reviewer and lifecycle == "review" and bool(gate.get("passed")))
    add("request_changes", reviewer and lifecycle == "review")
    add("reject", reviewer and lifecycle == "review")
    add("download", lifecycle == "completed" and any(item.get("formal_export") for item in artifacts))
    return actions


def _translation_run_dict(
    session: Session,
    run: TranslationRunRecord,
    identity: IdentityContext | None = None,
    ctx: _ListContext | None = None,
) -> dict[str, Any]:
    """Project the durable ledger plus current legacy-service state.

    With ``ctx`` (a page of runs) the caller has already refreshed what needed refreshing and
    everything else comes from the preloaded context.
    """
    progress_message = None if ctx is not None else _refresh_translation_run(session, run)
    preflight = ctx.preflights.get(run.preflight_id) if ctx is not None else session.get(PreflightRecord, run.preflight_id)
    settings = dict(run.settings_snapshot or {})
    source_language, target_language, _ = _normalize_language_pair(
        settings.get("source_language"), settings.get("target_language"), run.direction
    )
    if ctx is not None:
        artifacts = ctx.artifacts.get(run.id, [])
    else:
        artifacts = list(
            session.scalars(
                select(TranslationArtifact)
                .where(
                    TranslationArtifact.run_id == run.id,
                    TranslationArtifact.tenant_id == run.tenant_id,
                )
                .order_by(TranslationArtifact.created_at)
            )
        )
    gate = _formal_gate(session, run, ctx)
    artifact_rows = [_artifact_dict(item, run.id) for item in artifacts]
    lifecycle = _run_lifecycle(run)
    return {
        "lifecycle": lifecycle,
        "next_action": _run_next_action(lifecycle, gate),
        "superseded_by": _superseding_run_id(session, run, ctx),
        "qa_check": _qa_check_info(session, run, ctx),
        "pending_counts": {
            "qa_blockers": gate["qa_blockers"],
            "qa_unavailable": gate["qa_unavailable"],
            "unresolved_terms": gate["unresolved_term_count"],
            "unconfirmed_affiliations": gate["unconfirmed_affiliation_count"],
        },
        "allowed_actions": (
            _run_allowed_actions(session, identity, run, lifecycle, gate, artifact_rows)
            if identity is not None
            else []
        ),
        "id": run.id,
        "actor_sub": run.actor_sub,
        "project_id": None,
        "preflight_id": run.preflight_id,
        "generation": run.generation,
        "filename": preflight.source_filename if preflight else None,
        "format": preflight.source_format if preflight else None,
        "direction": run.direction,
        "source_language": source_language,
        "target_language": target_language,
        "profile": run.profile,
        "domain_profile": settings.get("domain_profile") or "general",
        "prompt_snapshot": dict(settings.get("prompt_snapshot") or {}) or None,
        "settings": settings,
        "display_name": run.display_name,
        "name_version": run.name_version or 0,
        "deleted_at": run.deleted_at.isoformat() if run.deleted_at else None,
        "purge_after": run.purge_after.isoformat() if run.purge_after else None,
        "trash_days_left": _trash_days_left(run),
        "purge_status": run.purge_status,
        "archived": run.archived_at is not None,
        "archived_at": run.archived_at.isoformat() if run.archived_at else None,
        "status": run.status,
        "stage": run.stage,
        "progress": run.progress,
        "progress_message": progress_message or (
            run.degradation_reason if run.status in {"failed", "degraded"} else None
        ),
        "manifest_version": run.manifest_version,
        "quality_state": getattr(run, "quality_state", None) or "draft",
        "document_classification": getattr(run, "document_classification", None),
        "model_profile_id": getattr(run, "model_profile_id", None),
        "qa_summary": run.qa_summary or {},
        "term_summary": run.term_summary or {},
        "formal_gate": gate,
        "artifacts": artifact_rows,
        "degradation_reason": run.degradation_reason,
        "external_task_id": run.external_task_id,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _run_owned(
    session: Session, *, run_id: str, identity: IdentityContext, include_trashed: bool = False
) -> TranslationRunRecord:
    """Visibility only. A task in the recycle bin does not exist for anything but the bin itself."""
    tenant = _tenant_bundle(session, identity)
    run = session.scalar(
        select(TranslationRunRecord).where(
            TranslationRunRecord.id == run_id,
            TranslationRunRecord.tenant_id == tenant.id,
        )
    )
    if run is not None and run.deleted_at is not None and not include_trashed:
        raise HTTPException(status_code=404, detail="translation run not found")
    if run is None or (
        run.actor_sub != identity.user_sub
        and _effective_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}
    ):
        raise HTTPException(status_code=404, detail="translation run not found")
    return run


_WRITER_ACTIONS = frozenset({"rename", "archive", "restore", "delete", "cancel", "discard", "restore_from_trash"})
_EXECUTING_LIFECYCLES = frozenset({"executing", "qa_checking"})


def _is_run_admin(session: Session, identity: IdentityContext) -> bool:
    return _cached_role(session, identity) in {"admin", "owner"}


def _is_run_writer(session: Session, identity: IdentityContext, run: TranslationRunRecord) -> bool:
    return run.actor_sub == identity.user_sub or _is_run_admin(session, identity)


def _require_run_writer(session: Session, identity: IdentityContext, run: TranslationRunRecord) -> None:
    if not _is_run_writer(session, identity, run):
        raise _disposition_error(
            403, "RUN_OWNER_REQUIRED", "仅任务提交人或管理员可以修改、归档、取消或删除该任务"
        )


def _authorize_run_action(
    session: Session, identity: IdentityContext, run: TranslationRunRecord, action: str
) -> None:
    """The server-side twin of ``allowed_actions``: who may do what, in which state (PLAN-078d/e).

    Seeing a task is not authority over it. Writer actions need the submitter or an admin; and
    every action must make sense for the task's current phase, so a running task is never
    archived or deleted underneath its executor. Permanent purge is for administrators only.
    """
    if run.deleted_at is not None:
        if action == "purge":
            if not _is_run_admin(session, identity):
                raise _disposition_error(403, "ADMIN_REQUIRED", "仅管理员可以永久清除任务")
            return
        if action == "restore_from_trash":
            _require_run_writer(session, identity, run)
            if run.purge_status == "pending":
                raise _disposition_error(409, "PURGE_IN_PROGRESS", "该任务正在被清除，不能恢复")
            if run.purge_status == "failed":
                raise _disposition_error(
                    409, "PURGE_FAILED", "该任务清除失败，文件可能已被部分删除，不能恢复；请管理员重试清除"
                )
            return
        raise _disposition_error(409, "RUN_IN_TRASH", "任务在回收站中，请先恢复")
    if action in {"restore_from_trash", "purge"}:
        raise _disposition_error(409, "NOT_IN_TRASH", "任务不在回收站中")
    lifecycle = _run_lifecycle(run)
    if action in _run_allowed_actions(session, identity, run, lifecycle, {"passed": False}, []):
        return
    if action in _WRITER_ACTIONS:
        _require_run_writer(session, identity, run)
    if action == "delete" and lifecycle in _EXECUTING_LIFECYCLES:
        raise _disposition_error(409, "RUN_STILL_EXECUTING", "任务仍在运行，请先取消后再删除")
    raise _disposition_error(
        409,
        "ACTION_NOT_ALLOWED_IN_STATE",
        f"任务当前处于“{lifecycle}”阶段，不能执行该操作",
    )


def _clean_task_name(raw: str) -> str:
    import unicodedata

    name = (raw or "").strip()
    if not name:
        raise _disposition_error(
            422, "NAME_REQUIRED", "任务名称不能为空；要使用原文件名请选择“恢复为原文件名”"
        )
    if len(name) > 120 or any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} for ch in name):
        raise _disposition_error(422, "NAME_INVALID", "任务名称最长 120 个字符，且不能包含换行或控制字符")
    return name


def _parse_if_match(raw: str) -> int:
    text = raw.strip()
    if text.startswith("W/"):
        text = text[2:]
    try:
        return int(text.strip('"'))
    except ValueError as exc:
        raise _disposition_error(400, "INVALID_IF_MATCH", "If-Match 必须是任务名称的版本号") from exc


async def _start_legacy_translation(
    *,
    service: Any,
    task_id: str,
    payload: AutoWorkflowParams,
    content: bytes,
    filename: str,
    declared_mime: str,
) -> dict[str, Any]:
    return await service.start_translation(
        task_id=task_id,
        payload=payload,
        file_contents=content,
        original_filename=filename,
        declared_mime=declared_mime,
    )


async def _launch_translation_run(
    *,
    run: TranslationRunRecord,
    preflight: PreflightRecord,
    target_language: str,
    session: Session | None = None,
    resume: bool = False,
) -> None:
    """Launch the appropriate non-GUI runner and persist an honest state.

    PLAN-071b：``QYUNSLATION_PIPELINE=v2`` 时四类格式统一进 DocumentPipeline。
    默认 ``legacy`` 保持原 PDF CLI / Office sidecar 分叉，便于灰度回滚。
    """
    from qyunslation.pipeline import run_pipeline_mode
    from qyunslation.workbench.heartbeat import touch_run_heartbeat

    # Compile the protected prompt at launch time.  The durable API snapshot
    # contains only the digest/metadata; the raw prompt exists only in this
    # process and the private PDF runner config.
    launch_settings = dict(run.settings_snapshot or {})
    if str(launch_settings.get("domain_profile") or "general").casefold() == "ad":
        from qyunslation.pipeline.ad_prompt_store import load_frozen_prompt, verify_frozen_digest
        from qyunslation.workbench.runner import get_pdf2zh_runner

        expected_digest = str(dict(launch_settings.get("prompt_snapshot") or {}).get("digest") or "")
        run_dir = get_pdf2zh_runner()._run_dir(
            tenant_id=run.tenant_id,
            run_id=run.id,
            generation=run.generation,
        )
        if not verify_frozen_digest(run_dir, expected_digest):
            run.status = "blocked"
            run.stage = "validation"
            run.degradation_reason = "AD prompt digest mismatch"
            return
        loaded = load_frozen_prompt(run_dir)
        if loaded is None:
            run.status = "blocked"
            run.stage = "validation"
            run.degradation_reason = "AD prompt unavailable"
            return
        launch_settings["ad_prompt_text"] = loaded[0]

    if resume and session is not None:
        _apply_resume_snapshot(session, run)
        if preflight.source_format.casefold() == "pdf":
            try:
                from qyunslation.workbench.runner import get_pdf2zh_runner

                await get_pdf2zh_runner().prepare_resume(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    generation=run.generation,
                )
            except Exception:
                pass

    if session is not None:
        try:
            from qyunslation.workbench.runner import get_pdf2zh_runner
            from qyunslation.workbench.term_inject import build_run_glossary_path

            run_dir = get_pdf2zh_runner()._run_dir(
                tenant_id=run.tenant_id,
                run_id=run.id,
                generation=run.generation,
            )
            run_dir.mkdir(parents=True, exist_ok=True)
            overrides = (run.settings_snapshot or {}).get("review_overrides")
            if isinstance(overrides, dict) and overrides:
                from qyunslation.structure.translation_trace import OVERRIDES_FILE

                (run_dir / OVERRIDES_FILE).write_text(
                    json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            glossary_path, inject_meta = build_run_glossary_path(
                session,
                run=run,
                preflight=preflight,
                run_dir=run_dir,
            )
            snap = dict(run.settings_snapshot or {})
            if glossary_path:
                existing = str(
                    snap.get("glossaries")
                    or os.environ.get("QYUNSLATION_PDF2ZH_GLOSSARIES")
                    or ""
                ).strip()
                paths = [item for item in existing.split(",") if item.strip()]
                if glossary_path not in paths:
                    paths.append(glossary_path)
                snap["glossaries"] = ",".join(paths)
            for key in ("termbase_version", "injected_terms", "glossary_path"):
                if inject_meta.get(key) is not None:
                    snap[key] = inject_meta[key]
            run.settings_snapshot = snap
        except Exception:
            pass

    if run_pipeline_mode(run.settings_snapshot) == "v2":
        try:
            from qyunslation.pipeline.document_pipeline import get_document_pipeline

            content_path = _preflight_path(preflight)
            meta = preflight.metadata_json or {}
            launch = await get_document_pipeline().start(
                tenant_id=run.tenant_id,
                run_id=run.id,
                generation=run.generation,
                source_path=content_path,
                source_format=preflight.source_format,
                original_filename=preflight.source_filename,
                direction=run.direction,
                target_language=target_language,
                settings={**dict(run.settings_snapshot or {}), "ad_prompt_text": launch_settings.get("ad_prompt_text")},
                declared_mime=str(meta.get("mime") or "application/octet-stream"),
                scanned_hint=bool(meta.get("scanned") or meta.get("needs_ocr")),
            )
            run.external_task_id = launch.external_task_id
            run.status = launch.status
            run.stage = launch.stage
            run.manifest_version = launch.manifest_version
            run.started_at = datetime.now(timezone.utc)
            snap = dict(run.settings_snapshot or {})
            snap["pipeline"] = "v2"
            snap["pipeline_events"] = launch.events
            snap["sealed_source_sha256"] = launch.sealed_sha256
            snap["executor_kind"] = launch.executor_kind
            run.settings_snapshot = snap
            try:
                from qyunslation.pipeline.event_store import persist_buffer
                from qyunslation.pipeline.events import StageEventBuffer

                buf = StageEventBuffer()
                for item in launch.events:
                    buf.emit(
                        item["stage"],
                        item["state"],
                        message=item.get("message") or "",
                        progress=item.get("progress"),
                    )
                if session is not None:
                    persist_buffer(
                        session,
                        run_id=run.id,
                        generation=run.generation,
                        buffer=buf,
                    )
            except Exception:
                pass
            return
        except Exception:
            run.status = "blocked"
            run.stage = "validation"
            run.degradation_reason = "document pipeline unavailable"
            return

    if preflight.source_format.casefold() == "pdf" and (
        (os.environ.get("QYUNSLATION_PDF_RUNNER") or "cli").strip().casefold() != "legacy"
    ):
        try:
            from qyunslation.workbench.runner import get_pdf2zh_runner

            content_path = _preflight_path(preflight)
            launch = await get_pdf2zh_runner().start(
                tenant_id=run.tenant_id,
                run_id=run.id,
                generation=run.generation,
                input_path=content_path,
                direction=run.direction,
                original_filename=preflight.source_filename,
                settings={**dict(run.settings_snapshot or {}), "ad_prompt_text": launch_settings.get("ad_prompt_text")},
            )
            run.external_task_id = launch.task_id
            run.status = "translating"
            run.stage = "structure"
            run.started_at = datetime.now(timezone.utc)
            return
        except Exception:
            # Do not fall back to the legacy PDF/Gradio route.  A missing CLI
            # is an honest blocked run and can be retried after deployment.
            run.status = "blocked"
            run.stage = "validation"
            run.degradation_reason = "translation runner unavailable"
            return
    try:
        from qyunslation.server import get_translation_service

        service = get_translation_service()
        if service.main_event_loop is None:
            raise RuntimeError("translation service is not initialized")
        content_path = _preflight_path(preflight)
        content = content_path.read_bytes()
        task_id = uuid.uuid4().hex[:16]
        payload = AutoWorkflowParams(
            workflow_type="auto",
            to_lang=target_language,
            domain_profile=str(launch_settings.get("domain_profile") or "general"),
            document_profile=str(launch_settings.get("profile") or "通用医药文档"),
            custom_prompt=str(launch_settings.get("ad_prompt_text") or "") or None,
        )
        result = await _start_legacy_translation(
            service=service,
            task_id=task_id,
            payload=payload,
            content=content,
            filename=preflight.source_filename,
            declared_mime=str(
                (preflight.metadata_json or {}).get("mime") or "application/octet-stream"
            ),
        )
        run.external_task_id = str(result.get("task_id") or task_id)
        run.status = "translating"
        run.stage = "structure"
        run.started_at = datetime.now(timezone.utc)
    except Exception:
            run.status = "blocked"
            run.stage = "validation"
            run.degradation_reason = "translation runner unavailable"
    if session is not None:
        touch_run_heartbeat(session, run)


def _run_config_digest(
    *,
    preflight_id: str,
    direction: str,
    profile: str,
    domain_profile: str,
    bilingual: bool,
    classification: str,
    model_profile_id: str | None,
    term_model_profile_id: str | None,
) -> str:
    """Stable digest of every setting that shapes a run (see create_translation_run).

    v2 (PLAN-078c) takes the *resolved* term model, so a change in which model will really be
    used between confirmation and submission is noticed.
    """
    canonical = json.dumps(
        {
            "v": 2,
            "preflight_id": preflight_id,
            "direction": direction,
            "profile": profile,
            "domain_profile": domain_profile,
            "bilingual": bool(bilingual),
            "classification": classification,
            "model_profile_id": model_profile_id or "",
            "term_model_profile_id": term_model_profile_id or "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ResolvedRunConfig:
    source_language: str
    target_language: str
    direction: str
    profile: str
    domain_profile: str
    classification: str
    model_profile_id: str | None
    term_profile_id: str | None
    bilingual: bool
    bilingual_effective: bool
    display_name: str | None
    digest: str


@dataclass
class ConfigCheck:
    tenant: Any
    preflight: PreflightRecord | None
    cfg: ResolvedRunConfig | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _config_issue(code: str, message: str, *, field_name: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "field": field_name, **extra}


_SELECTION_CODES = (
    ("invalid document_classification", "CLASSIFICATION_INVALID", "document_classification", "资料等级无效"),
    ("deepseek not configured", "MODEL_NOT_CONFIGURED", "model_profile_id", "该外部模型当前没有配置，无法使用"),
    ("term model not allowed", "TERM_MODEL_NOT_ALLOWED", "term_model_profile_id", "该资料等级不允许使用所选术语模型"),
    ("confidential forbids external term model", "TERM_MODEL_NOT_ALLOWED", "term_model_profile_id", "机密资料不允许使用外部术语模型"),
    ("model_profile_id not allowed", "MODEL_NOT_ALLOWED", "model_profile_id", "该资料等级不允许使用所选翻译模型"),
    ("forbids external", "MODEL_EGRESS_CONFLICT", "model_profile_id", "所选模型会把全文发送到外部，与资料等级冲突"),
)


def _collect_run_config(
    session: Session, identity: IdentityContext, body: TranslationRunCreateBody, *, check_occupied: bool
) -> ConfigCheck:
    """Resolve and check everything that decides what a run will do, collecting every problem.

    Creating a run and validating a confirmation use this one function, so what a person is
    shown is what the server will execute (PLAN-078c). ``errors[*]["status"/"detail"]`` carry
    the HTTP error the create endpoint raises for the first problem.
    """
    from qyunslation.pipeline.model_profiles import PROFILES, default_term_profile_id, validate_selection
    from qyunslation.pipeline.run_snapshot import egress_scope

    tenant = _tenant_bundle(session, identity)
    check = ConfigCheck(tenant=tenant, preflight=None)

    def fail(code: str, message: str, *, status: int, detail: Any, field_name: str | None = None, **extra: Any) -> None:
        issue = _config_issue(code, message, field_name=field_name, **extra)
        issue["status"], issue["detail"] = status, detail
        check.errors.append(issue)

    languages: tuple[str, str, str] | None = None
    try:
        languages = _normalize_language_pair(body.source_language, body.target_language, body.direction)
    except HTTPException as exc:
        same = "must differ" in str(exc.detail)
        fail(
            "LANGUAGE_SAME" if same else "LANGUAGE_UNSUPPORTED",
            "源语言和目标语言不能相同" if same else "不支持所选语言或方向",
            status=exc.status_code, detail=exc.detail, field_name="language",
        )

    preflight = session.get(PreflightRecord, body.preflight_id)
    visible = (
        preflight is not None
        and preflight.tenant_id == tenant.id
        and (
            preflight.actor_sub == identity.user_sub
            or _effective_role(session, identity) in {"reviewer", "term_admin", "admin", "owner"}
        )
    )
    usable_preflight = False
    if not visible:
        preflight = None
        fail("PREFLIGHT_NOT_FOUND", "找不到该预检", status=404, detail="preflight not found", field_name="preflight_id")
    else:
        state = _preflight_dict(preflight)["state"]
        if state != "ready":
            expired = state == "expired"
            fail(
                "PREFLIGHT_EXPIRED" if expired else "PREFLIGHT_NOT_READY",
                "预检已过期，请重新预检" if expired else "预检未通过，不能开始翻译",
                status=409, detail="preflight is not ready", field_name="preflight_id",
            )
        else:
            usable_preflight = True
    check.preflight = preflight

    domain_profile = (body.domain_profile or "general").strip().casefold()
    if usable_preflight and languages is not None:
        try:
            _validate_domain_profile(
                preflight=preflight,
                domain_profile=domain_profile,
                direction=languages[2],
                document_profile=body.profile,
                tenant_slug=tenant.slug,
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            code = str(detail.get("code") or "DOMAIN_INVALID")
            fail(
                "DOMAIN_UNSUPPORTED" if code == "AD_PROFILE_UNSUPPORTED" and domain_profile != "ad" else code,
                str(detail.get("message") or "专业领域设置无效"),
                status=exc.status_code, detail=exc.detail, field_name="domain_profile",
            )

    classification = body.document_classification or (preflight.document_classification if preflight else None) or "internal"
    model_profile_id = body.model_profile_id or (preflight.model_profile_id if preflight else None)
    term_profile_id = body.term_model_profile_id
    if term_profile_id is None:
        term_profile_id = default_term_profile_id(classification)
    selection_ok = True
    try:
        classification, model_profile_id, term_profile_id = validate_selection(
            classification=classification, model_profile_id=model_profile_id, term_profile_id=term_profile_id
        )
    except ValueError as exc:
        selection_ok = False
        text = str(exc)
        code, field_name, message = next(
            ((c, f, m) for needle, c, f, m in _SELECTION_CODES if needle in text),
            ("MODEL_INVALID", "model_profile_id", "模型选择无效"),
        )
        fail(code, message, status=400, detail=text, field_name=field_name)

    if check_occupied and usable_preflight:
        occupied = session.scalar(
            select(TranslationRunRecord.id).where(
                TranslationRunRecord.preflight_id == preflight.id, TranslationRunRecord.generation == 1
            )
        )
        if occupied is not None:
            fail(
                "PREFLIGHT_ALREADY_RUN",
                "该文件已用这份预检创建过任务；可复制预检后用新参数翻译，原任务不受影响",
                status=409,
                detail={"code": "PREFLIGHT_ALREADY_RUN", "run_id": occupied},
                field_name="preflight_id",
                run_id=occupied,
                can_copy=True,
            )

    if languages is None or preflight is None or not selection_ok:
        return check

    source_language, target_language, direction = languages
    pdf = preflight.source_format.casefold() == "pdf"
    check.cfg = ResolvedRunConfig(
        source_language=source_language,
        target_language=target_language,
        direction=direction,
        profile=body.profile,
        domain_profile=domain_profile,
        classification=classification,
        model_profile_id=model_profile_id,
        term_profile_id=term_profile_id,
        bilingual=bool(body.bilingual),
        bilingual_effective=bool(body.bilingual) and pdf,
        display_name=(body.display_name or "").strip() or None,
        digest=_run_config_digest(
            preflight_id=preflight.id,
            direction=direction,
            profile=body.profile,
            domain_profile=domain_profile,
            bilingual=body.bilingual,
            classification=classification,
            model_profile_id=model_profile_id,
            term_model_profile_id=term_profile_id,
        ),
    )

    if body.bilingual and not pdf:
        check.warnings.append(
            _config_issue("BILINGUAL_NOT_SUPPORTED", "该格式只输出译文，不会生成源译对照稿", field_name="bilingual")
        )
    egress = egress_scope(classification=classification, translator_id=model_profile_id, term_id=term_profile_id)
    if egress == "full_document":
        check.warnings.append(_config_issue("EGRESS_FULL_DOCUMENT", "全文将发送到外部模型，请确认资料等级允许", field_name="model_profile_id"))
    elif egress == "redacted_term_snippets":
        check.warnings.append(_config_issue("EGRESS_REDACTED_TERMS", "脱敏后的术语片段将发送到外部术语模型", field_name="term_model_profile_id"))
    term_profile = PROFILES.get(term_profile_id or "")
    if term_profile is not None and term_profile.provider == "ollama":
        try:
            from qyunslation.gateway.config import resolve_profile

            endpoint = resolve_profile(None).get("endpoint")
        except Exception:
            endpoint = None
        if not endpoint:
            check.warnings.append(
                _config_issue("TERM_MODEL_NOT_CONFIGURED", "内网模型地址未配置，术语检查可能无法完成", field_name="term_model_profile_id")
            )
    if domain_profile == "ad":
        check.warnings.append(_config_issue("AD_PREVIEW", "AD 专业模式为内部测试版", field_name="domain_profile"))
    return check


def _model_info(profile_id: str | None) -> dict[str, Any] | None:
    from qyunslation.pipeline.model_profiles import PROFILES

    profile = PROFILES.get(profile_id or "")
    if profile is None:
        return None
    return {
        "profile_id": profile.profile_id,
        "label": profile.label,
        "provider": profile.provider,
        "model_id": profile.model_id,
        "experimental": profile.experimental,
    }


def _preflight_used_by(session: Session, preflight_id: str) -> str | None:
    return session.scalar(
        select(TranslationRunRecord.id)
        .where(TranslationRunRecord.preflight_id == preflight_id, TranslationRunRecord.generation == 1)
        .limit(1)
    )


@router.post("/translation-runs/validate")
def validate_translation_run(
    body: TranslationRunCreateBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dry run of run creation: what would execute, what is wrong, and the digest to confirm."""
    from qyunslation.pipeline.run_snapshot import egress_scope

    check = _collect_run_config(session, identity, body, check_occupied=True)
    if any(error["code"] == "PREFLIGHT_NOT_FOUND" for error in check.errors):
        raise HTTPException(status_code=404, detail="preflight not found")
    cfg, preflight = check.cfg, check.preflight
    config: dict[str, Any] | None = None
    if cfg is not None:
        config = {
            "preflight_id": preflight.id,
            "filename": preflight.source_filename,
            "format": preflight.source_format,
            "display_name": cfg.display_name,
            "source_language": cfg.source_language,
            "target_language": cfg.target_language,
            "direction": cfg.direction,
            "profile": cfg.profile,
            "domain_profile": cfg.domain_profile,
            "document_classification": cfg.classification,
            "model_profile_id": cfg.model_profile_id,
            "term_model_profile_id": cfg.term_profile_id,
            "model": _model_info(cfg.model_profile_id),
            "term_model": _model_info(cfg.term_profile_id),
            "egress_scope": egress_scope(
                classification=cfg.classification, translator_id=cfg.model_profile_id, term_id=cfg.term_profile_id
            ),
            "bilingual": cfg.bilingual,
            "bilingual_effective": cfg.bilingual_effective,
            "qa_policy": {
                "deterministic": True,
                "term_extraction": True,
                "term_model_profile_id": cfg.term_profile_id,
                "semantic_qa_mode": (os.environ.get("QYUNSLATION_AD_SEMANTIC_QA_MODE") or "shadow").strip().casefold()
                if cfg.domain_profile == "ad"
                else None,
            },
        }
    public_errors = [
        {key: value for key, value in error.items() if key not in {"status", "detail"}} for error in check.errors
    ]
    return {
        "ok": not check.errors,
        "errors": public_errors,
        "warnings": check.warnings,
        "config": config,
        "config_digest": cfg.digest if cfg is not None else None,
        "preflight": (
            {
                "id": preflight.id,
                "state": _preflight_dict(preflight)["state"],
                "filename": preflight.source_filename,
                "format": preflight.source_format,
                "size_bytes": preflight.size_bytes,
                "expires_at": _preflight_dict(preflight)["expires_at"],
                "used_by_run_id": _preflight_used_by(session, preflight.id),
            }
            if preflight is not None
            else None
        ),
    }


@router.post("/translation-runs", status_code=201)
async def create_translation_run(
    body: TranslationRunCreateBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    check = _collect_run_config(session, identity, body, check_occupied=False)
    if check.errors:
        first = check.errors[0]
        raise HTTPException(status_code=first["status"], detail=first["detail"])
    cfg = check.cfg
    tenant, preflight = check.tenant, check.preflight
    source_language, target_language, direction = cfg.source_language, cfg.target_language, cfg.direction
    domain_profile, classification = cfg.domain_profile, cfg.classification
    model_profile_id, term_profile_id = cfg.model_profile_id, cfg.term_profile_id
    config_digest = cfg.digest
    key = (idempotency_key or f"preflight:{preflight.id}").strip()
    if not key or len(key) > 256:
        raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
    key_material = f"{key}|domain_profile={domain_profile}"
    key_hash = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(TranslationRunRecord).where(
            TranslationRunRecord.tenant_id == tenant.id,
            TranslationRunRecord.idempotency_key_hash == key_hash,
        )
    )
    if existing is not None:
        existing_snapshot = existing.settings_snapshot or {}
        recorded = existing_snapshot.get("config_digest")
        versioned = existing_snapshot.get("config_digest_v") == 2
        existing_domain = str(existing_snapshot.get("domain_profile") or "general").casefold()
        if (versioned and recorded != config_digest) or (not versioned and existing_domain != domain_profile):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_CONFIG_MISMATCH",
                    "message": "该请求编号已用于不同的翻译参数，请重新确认参数后再提交",
                    "run_id": existing.id,
                },
            )
        return _translation_run_dict(session, existing, identity=identity)
    if body.config_digest and body.config_digest != config_digest:
        # The person confirmed one configuration; what would run now is another one (a model
        # became unavailable, the default term model changed, ...). Ask again instead of guessing.
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFIG_STALE",
                "message": "确认之后配置已发生变化，请重新确认参数",
                "current_digest": config_digest,
            },
        )
    # (preflight_id, generation) is unique; a second run for the same preflight
    # must surface as a conflict rather than an IntegrityError 500.
    occupied = session.scalar(
        select(TranslationRunRecord).where(
            TranslationRunRecord.preflight_id == preflight.id,
            TranslationRunRecord.generation == 1,
        )
    )
    if occupied is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREFLIGHT_ALREADY_RUN",
                "message": "该预检已创建翻译任务，请重新预检后再翻译",
                "run_id": occupied.id,
            },
        )
    from qyunslation.glossary.termbase import runtime_termbase_version
    from qyunslation.pipeline import resolve_pipeline_mode
    from qyunslation.pipeline.run_snapshot import build_run_model_snapshot

    try:
        termbase_version = runtime_termbase_version(session, tenant_id=tenant.id, project_id=None)
    except Exception:
        termbase_version = None
    mode_snapshot = build_run_model_snapshot(
        classification=classification,
        translator_id=model_profile_id,
        term_id=term_profile_id,
        termbase_version=termbase_version,
        pipeline=resolve_pipeline_mode(getattr(tenant, "slug", None)),
    )
    prompt_snapshot: dict[str, Any] | None = None
    ad_prompt_text: str | None = None
    if domain_profile == "ad":
        try:
            from qyunslation.pipeline.ad_runtime import compile_runtime_settings

            compiled = compile_runtime_settings(
                {
                    "domain_profile": domain_profile,
                    "direction": direction,
                    "profile": body.profile,
                    "target_language": target_language,
                },
                termbase_version=termbase_version,
                model_profile_id=model_profile_id,
            )
            prompt_snapshot = compiled.get("prompt_snapshot")
            ad_prompt_text = str(compiled.get("custom_prompt") or "")
        except ValueError as exc:
            message = str(exc)
            code = "AD_CUSTOM_PROMPT_FORBIDDEN" if "custom_prompt" in message else "AD_PROMPT_UNAVAILABLE"
            raise HTTPException(
                status_code=422 if code == "AD_CUSTOM_PROMPT_FORBIDDEN" else 503,
                detail={"code": code, "message": message},
            ) from exc
    run = TranslationRunRecord(
        preflight_id=preflight.id,
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        idempotency_key_hash=key_hash,
        direction=direction,
        profile=body.profile,
        display_name=(body.display_name or "").strip() or None,
        document_classification=classification,
        model_profile_id=model_profile_id,
        quality_state="draft",
        settings_snapshot={
            "direction": direction,
            "source_language": source_language,
            "target_language": target_language,
            "profile": body.profile,
            "domain_profile": domain_profile,
            "prompt_snapshot": prompt_snapshot,
            "ad_prompt_text": ad_prompt_text,
            "semantic_qa_mode": (os.environ.get("QYUNSLATION_AD_SEMANTIC_QA_MODE") or "shadow").strip().casefold(),
            "bilingual": body.bilingual,
            # Only the PDF executor can emit a source/translation pair; other formats
            # always produce the translation alone, and the snapshot must say so.
            "bilingual_effective": cfg.bilingual_effective,
            "config_digest": config_digest,
            "config_digest_v": 2,
            "auto_ocr_workaround": True,
            "document_classification": classification,
            "model_profile_id": model_profile_id,
            "term_model_profile_id": term_profile_id,
            **mode_snapshot,
        },
        status="queued",
        stage="validation",
        term_summary={"status": "snapshot_pending"},
        qa_summary={"blocker": 0, "warning": 0, "info": 0},
    )
    session.add(run)
    session.flush()
    if domain_profile == "ad" and ad_prompt_text and prompt_snapshot:
        try:
            from qyunslation.pipeline.ad_prompt_store import write_frozen_prompt
            from qyunslation.workbench.runner import get_pdf2zh_runner

            run_dir = get_pdf2zh_runner()._run_dir(
                tenant_id=tenant.id,
                run_id=run.id,
                generation=run.generation,
            )
            write_frozen_prompt(run_dir, text=ad_prompt_text, snapshot=prompt_snapshot)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "AD_PROMPT_UNAVAILABLE", "message": f"failed to freeze prompt: {exc}"},
            ) from exc
    if domain_profile == "ad":
        from qyunslation.pipeline.ad_observability import record_ad_event

        record_ad_event(
            "ad_task_created",
            run_id=run.id,
            tenant=tenant.slug,
            direction=direction,
            document_profile=body.profile,
            prompt_digest=str((prompt_snapshot or {}).get("digest") or ""),
            termbase_version=termbase_version,
        )
        record_audit(
            session,
            actor_sub=identity.user_sub,
            action="translation_run.ad_created",
            extra={"run_id": run.id, "prompt_digest": str((prompt_snapshot or {}).get("digest") or "")},
        )
    egress = str((mode_snapshot.get("model_snapshot") or {}).get("egress_scope") or "none")
    if egress != "none":
        record_audit(
            session,
            actor_sub=identity.user_sub,
            action="translation_run.egress",
            extra={
                "run_id": run.id,
                "egress_scope": egress,
                "model_profile_id": model_profile_id,
                "document_classification": classification,
            },
        )
    await _launch_translation_run(
        run=run, preflight=preflight, target_language=target_language, session=session
    )
    return _translation_run_dict(session, run, identity=identity)


_LIFECYCLE_NAMES = (
    "executing", "qa_checking", "qa_action", "qa_unavailable", "review", "changes_requested",
    "failed", "interrupted", "cancelled", "completed",
)


def _lifecycle_sql(status: Any, quality: Any) -> Any:
    """SQL twin of _run_lifecycle, so the list can filter and count by the same phases the UI shows."""
    q = func.coalesce(quality, "draft")
    gated = status == "gated"
    return case(
        (status.in_(tuple(_RUN_EXECUTING)), "executing"),
        (and_(gated, q == "draft"), "qa_checking"),
        (and_(gated, q == "qa_blocked"), "qa_action"),
        (and_(gated, q == "qa_unavailable"), "qa_unavailable"),
        (and_(gated, q == "changes_requested"), "changes_requested"),
        (gated, "review"),
        (status == "succeeded", "completed"),
        (status.in_(("failed", "blocked", "degraded")), "failed"),
        (status == "interrupted", "interrupted"),
        (status == "cancelled", "cancelled"),
        else_="failed",
    )


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _split_values(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        out.extend(part.strip() for part in str(value).split(",") if part.strip())
    return out


def _encode_cursor(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")


def _decode_cursor(raw: str) -> dict[str, Any]:
    try:
        return json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": "分页游标无效，请从第一页重新开始"}) from exc


def _run_query_filters(
    *,
    session: Session,
    identity: IdentityContext,
    q: str | None,
    formats: list[str],
    direction: str | None,
    domain: str | None,
    created_from: date | None,
    created_to: date | None,
    trash: bool = False,
) -> list[Any]:
    """Conditions that describe *which runs match*, applied before versions are grouped."""
    tenant = _tenant_bundle(session, identity)
    conditions: list[Any] = [
        TranslationRunRecord.tenant_id == tenant.id,
        TranslationRunRecord.deleted_at.is_not(None) if trash else TranslationRunRecord.deleted_at.is_(None),
    ]
    if _cached_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        conditions.append(TranslationRunRecord.actor_sub == identity.user_sub)
    if q and q.strip():
        needle = _like_escape(q.strip().lower())
        conditions.append(
            or_(
                func.lower(TranslationRunRecord.display_name).like(f"%{needle}%", escape="\\"),
                func.lower(PreflightRecord.source_filename).like(f"%{needle}%", escape="\\"),
                func.lower(TranslationRunRecord.id).like(f"{needle}%", escape="\\"),
            )
        )
    if formats:
        conditions.append(func.lower(PreflightRecord.source_format).in_([f.lower().lstrip(".") for f in formats]))
    if direction:
        conditions.append(TranslationRunRecord.direction == direction)
    if domain:
        conditions.append(
            func.coalesce(TranslationRunRecord.settings_snapshot["domain_profile"].as_string(), "general") == domain.lower()
        )
    if created_from:
        conditions.append(TranslationRunRecord.created_at >= datetime.combine(created_from, dtime.min, tzinfo=timezone.utc))
    if created_to:
        conditions.append(
            TranslationRunRecord.created_at < datetime.combine(created_to + timedelta(days=1), dtime.min, tzinfo=timezone.utc)
        )
    return conditions


def _task_query(
    session: Session,
    identity: IdentityContext,
    *,
    q: str | None,
    lifecycle: Any,
    format: Any,
    direction: str | None,
    domain: str | None,
    created_from: date | None,
    created_to: date | None,
    archived_mode: str,
    status: str | None,
    sort: str,
    group_versions: bool,
    trash: bool,
) -> tuple[Any, list[Any], list[Any], Any] | None:
    """The one place that says which tasks a set of list filters selects.

    The list, its counts and the "select every match" snapshot all go through here, so they
    cannot disagree. Returns None when a lifecycle name is unknown (nothing can match).
    """
    TR, PF = TranslationRunRecord, PreflightRecord
    wanted_lifecycles = _split_values(lifecycle)
    if any(name not in _LIFECYCLE_NAMES for name in wanted_lifecycles):
        return None
    if trash:
        archived_mode = "all"  # the bin is not split by archive state
    sort_expression = {
        "created": TR.created_at,
        "updated": TR.updated_at,
        "name": func.lower(func.coalesce(TR.display_name, PF.source_filename, "")),
    }[sort]
    ranking = (
        func.row_number().over(partition_by=TR.preflight_id, order_by=TR.generation.desc())
        if group_versions
        else literal(1)
    )
    ranked = (
        select(
            TR.id.label("id"),
            TR.status.label("st"),
            TR.quality_state.label("qs"),
            TR.archived_at.label("ar"),
            sort_expression.label("sk"),
            ranking.label("rn"),
        )
        .select_from(TR)
        .join(PF, PF.id == TR.preflight_id, isouter=True)
        .where(
            *_run_query_filters(
                session=session, identity=identity, q=q, formats=_split_values(format), direction=direction,
                domain=domain, created_from=created_from, created_to=created_to, trash=trash,
            )
        )
        .subquery()
    )
    task_state = [ranked.c.rn == 1]
    if archived_mode == "active":
        task_state.append(ranked.c.ar.is_(None))
    elif archived_mode == "archived":
        task_state.append(ranked.c.ar.is_not(None))
    if status:
        task_state.append(ranked.c.st == status)
    phase = _lifecycle_sql(ranked.c.st, ranked.c.qs)
    conditions = list(task_state)
    if wanted_lifecycles:
        conditions.append(phase.in_(wanted_lifecycles))

    return ranked, conditions, task_state, phase


@router.get("/translation-runs")
def list_translation_runs(
    q: str | None = Query(default=None, max_length=200),
    lifecycle: list[str] | None = Query(default=None),
    format: list[str] | None = Query(default=None),
    direction: str | None = Query(default=None, max_length=64),
    domain: str | None = Query(default=None, max_length=32),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    archived: str | None = Query(default=None, pattern="^(active|archived|all)$"),
    sort: str = Query(default="created", pattern="^(created|updated|name)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    cursor: str | None = Query(default=None, max_length=512),
    group_versions: bool = Query(default=True),
    trash: bool = Query(default=False),
    status: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    page_size: int = Query(default=100, ge=1, le=100),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Search, filter, sort and page the tenant's tasks on the server (PLAN-078d).

    Matching (``q``, format, direction, domain, dates) is applied to every version of a task;
    the versions are then grouped so each task shows its newest matching version, and the
    task's *state* (lifecycle, archived) is that version's. Pagination is keyset-based, so it
    stays stable while tasks are being created or changed.
    """
    TR, PF = TranslationRunRecord, PreflightRecord
    query = _task_query(
        session, identity, q=q, lifecycle=lifecycle, format=format, direction=direction, domain=domain,
        created_from=created_from, created_to=created_to,
        archived_mode=archived or ("all" if include_archived else "active"),
        status=status, sort=sort, group_versions=group_versions, trash=trash,
    )
    if query is None:
        return {"items": [], "next_cursor": None, "total": 0, "facets": {"lifecycle": {}, "total": 0}, "page_size": page_size}
    ranked, conditions, task_state, phase = query

    total = session.scalar(select(func.count()).select_from(ranked).where(*conditions)) or 0
    facet_rows = session.execute(
        select(phase.label("phase"), func.count()).select_from(ranked).where(*task_state).group_by(phase)
    ).all()
    facets = {name: count for name, count in facet_rows if count}

    sort_column, id_column = ranked.c.sk, ranked.c.id
    page_query = select(ranked.c.id, ranked.c.sk).where(*conditions)
    if cursor:
        position = _decode_cursor(cursor)
        if position.get("sort") != sort or position.get("order") != order:
            raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": "分页游标与当前排序不一致，请从第一页重新开始"})
        value: Any = position.get("sk")
        if sort in {"created", "updated"}:
            try:
                value = datetime.fromisoformat(str(value))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": "分页游标无效"}) from exc
        marker = tuple_(sort_column, id_column)
        point = tuple_(value, position.get("id"))
        page_query = page_query.where(marker < point if order == "desc" else marker > point)
    ordering = (sort_column.desc(), id_column.desc()) if order == "desc" else (sort_column.asc(), id_column.asc())
    rows = session.execute(page_query.order_by(*ordering).limit(page_size + 1)).all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = None
    if has_more and rows:
        last_id, last_sort = rows[-1]
        next_cursor = _encode_cursor(
            {
                "sort": sort,
                "order": order,
                "id": last_id,
                "sk": last_sort.isoformat() if isinstance(last_sort, datetime) else last_sort,
            }
        )

    ids = [row[0] for row in rows]
    by_id = {run.id: run for run in session.scalars(select(TR).where(TR.id.in_(ids)))} if ids else {}
    runs = [by_id[i] for i in ids if i in by_id]
    for run in runs:
        if _needs_refresh(run):
            _refresh_translation_run(session, run)
    ctx = _build_list_context(session, runs)
    items = []
    for run in runs:
        payload = _translation_run_dict(session, run, identity=identity, ctx=ctx)
        if group_versions:
            payload["version_count"] = len(ctx.chains.get(run.preflight_id, [])) or 1
        items.append(payload)
    return {
        "items": items,
        "next_cursor": next_cursor,
        "total": total,
        "facets": {"lifecycle": facets, "total": sum(facets.values())},
        "page_size": page_size,
    }


@router.get("/translation-runs/{run_id}/versions")
def list_translation_run_versions(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Every version (generation) of the task this run belongs to, oldest first."""
    run = _run_owned(session, run_id=run_id, identity=identity)
    chain = list(
        session.scalars(
            select(TranslationRunRecord)
            .where(TranslationRunRecord.preflight_id == run.preflight_id, TranslationRunRecord.tenant_id == run.tenant_id)
            .order_by(TranslationRunRecord.generation)
        )
    )
    items = []
    for index, version in enumerate(chain):
        items.append(
            {
                "id": version.id,
                "generation": version.generation,
                "status": version.status,
                "quality_state": version.quality_state or "draft",
                "lifecycle": _run_lifecycle(version),
                "display_name": version.display_name,
                "archived": version.archived_at is not None,
                "created_at": version.created_at.isoformat(),
                "superseded_by": chain[index + 1].id if index + 1 < len(chain) else None,
                "current": version.id == run.id,
            }
        )
    return {"items": items}


@router.get("/translation-runs/{run_id}")
def get_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    return _translation_run_dict(session, _run_owned(session, run_id=run_id, identity=identity), identity=identity)


@router.patch("/translation-runs/{run_id}")
def patch_translation_run(
    run_id: str,
    body: TranslationRunPatchBody,
    if_match: str | None = Header(default=None, alias="If-Match"),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    changes: dict[str, Any] = {}
    if body.display_name is not None or body.reset_display_name:
        _authorize_run_action(session, identity, run, "rename")
        if if_match is not None and _parse_if_match(if_match) != (run.name_version or 0):
            current = run.display_name
            if current is None:
                preflight = session.get(PreflightRecord, run.preflight_id)
                current = preflight.source_filename if preflight else None
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "NAME_CONFLICT",
                    "message": "该任务的名称已在其他页面被修改",
                    "current_name": current,
                    "current_version": run.name_version or 0,
                },
            )
        new_name = None if body.reset_display_name else _clean_task_name(body.display_name or "")
        if new_name != run.display_name:
            run.display_name = new_name
            run.name_version = (run.name_version or 0) + 1
            changes["display_name"] = "reset" if new_name is None else "changed"
    if body.archived is not None:
        if (run.archived_at is not None) != body.archived:
            _authorize_run_action(session, identity, run, "archive" if body.archived else "restore")
            if body.archived:
                run.archived_at = datetime.now(timezone.utc)
                run.archived_by = identity.user_sub
            else:
                run.archived_at = None
                run.archived_by = None
            changes["archived"] = body.archived
        else:
            _require_run_writer(session, identity, run)  # already in that state: nothing to do, but not for strangers
    if changes:
        record_audit(
            session,
            actor_sub=identity.user_sub,
            action="translation_run.update",
            extra={"run_id": run.id, "changes": changes},
        )
    return _translation_run_dict(session, run, identity=identity)


@router.post("/translation-runs/{run_id}/restore")
def restore_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _require_run_writer(session, identity, run)
    if run.archived_at is not None:
        run.archived_at = None
        run.archived_by = None
        record_audit(
            session,
            actor_sub=identity.user_sub,
            action="translation_run.restore",
            extra={"run_id": run.id},
        )
    return _translation_run_dict(session, run, identity=identity)


# ---------------------------------------------------------------------------------------------------
# PLAN-078e: recycle bin, permanent purge, and batch actions.
#
# A "task" is the chain of versions that share one pre-check (what the list shows as one row). Moving
# to the bin, restoring and purging act on the whole chain, so deleting a task never makes an older
# version of it reappear in the list.
# ---------------------------------------------------------------------------------------------------

TRASH_BATCH_MAX_IDS = 200
SELECTION_MAX = 1000
SELECTION_TTL = timedelta(minutes=15)


def _trash_retention() -> timedelta:
    try:
        days = int(os.environ.get("QYUNSLATION_TRASH_RETENTION_DAYS") or 30)
    except ValueError:
        days = 30
    return timedelta(days=max(days, 1))


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _trash_days_left(run: TranslationRunRecord) -> int | None:
    due = _aware(run.purge_after)
    if run.deleted_at is None or due is None:
        return None
    return max(0, -(-int((due - datetime.now(timezone.utc)).total_seconds()) // 86400))


def _task_chain(session: Session, run: TranslationRunRecord) -> list[TranslationRunRecord]:
    return list(
        session.scalars(
            select(TranslationRunRecord)
            .where(
                TranslationRunRecord.tenant_id == run.tenant_id,
                TranslationRunRecord.preflight_id == run.preflight_id,
            )
            .order_by(TranslationRunRecord.generation)
        )
    )


def _move_task_to_trash(
    session: Session, identity: IdentityContext, chain: list[TranslationRunRecord], now: datetime
) -> None:
    head = chain[-1]
    for member in chain:
        if member is head or _needs_refresh(member):
            _refresh_translation_run(session, member)
    if any(_run_lifecycle(member) in _EXECUTING_LIFECYCLES for member in chain):
        raise _disposition_error(409, "RUN_STILL_EXECUTING", "任务仍在运行，请先取消后再删除")
    due = now + _trash_retention()
    for member in chain:
        if member.deleted_at is None:
            member.deleted_at = now
            member.deleted_by = identity.user_sub
            member.purge_after = due
            member.purge_status = None
            member.purge_error = None
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="translation_run.trash",
        extra={"run_id": head.id, "run_ids": [member.id for member in chain], "purge_after": due.isoformat()},
    )


def _restore_task_from_trash(
    session: Session, identity: IdentityContext, chain: list[TranslationRunRecord]
) -> None:
    for member in chain:
        member.deleted_at = None
        member.deleted_by = None
        member.purge_after = None
        member.purge_status = None
        member.purge_error = None
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="translation_run.restore_from_trash",
        extra={"run_id": chain[-1].id, "run_ids": [member.id for member in chain]},
    )


@router.delete("/translation-runs/{run_id}", status_code=204)
def delete_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> Response:
    """Move a task to the recycle bin. Nothing is removed: files stay until the bin is purged."""
    run = _run_owned(session, run_id=run_id, identity=identity)
    chain = _task_chain(session, run)
    _refresh_translation_run(session, chain[-1])
    _authorize_run_action(session, identity, chain[-1], "delete")
    _move_task_to_trash(session, identity, chain, datetime.now(timezone.utc))
    session.commit()
    return Response(status_code=204)


@router.post("/translation-runs/{run_id}/restore-from-trash")
def restore_translation_run_from_trash(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity, include_trashed=True)
    chain = _task_chain(session, run)
    head = chain[-1]
    if head.deleted_at is None:  # nothing to restore: the same answer as a successful restore
        _require_run_writer(session, identity, head)
    else:
        _authorize_run_action(session, identity, head, "restore_from_trash")
        _restore_task_from_trash(session, identity, chain)
    session.commit()
    return _translation_run_dict(session, head, identity=identity)


# ----- purge: commit the decision first, remove files second, delete rows last -----------------------


def _run_work_dirs(chain: list[TranslationRunRecord]) -> list[Path]:
    from qyunslation.workbench.runner import _root_from_env

    root = _root_from_env()
    out: list[Path] = []
    for member in chain:
        directory = (root / member.tenant_id / member.id).resolve()
        if root in directory.parents:  # never a path that escapes the runner root
            out.append(directory)
    return out


def _purge_files(
    session: Session, chain: list[TranslationRunRecord], preflight: PreflightRecord | None
) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    for member in chain:
        for artifact in session.scalars(
            select(TranslationArtifact).where(
                TranslationArtifact.run_id == member.id, TranslationArtifact.tenant_id == member.tenant_id
            )
        ):
            try:
                files.append(_artifact_path(artifact))
            except HTTPException:
                logger.warning("skipping artifact with an invalid storage key: %s", artifact.id)
    if preflight is not None:
        # A source file is removed only when no other pre-check points at the same stored file.
        shared = session.scalar(
            select(func.count())
            .select_from(PreflightRecord)
            .where(PreflightRecord.storage_key == preflight.storage_key, PreflightRecord.id != preflight.id)
        )
        if not shared:
            try:
                files.append(_preflight_path(preflight))
            except HTTPException:
                logger.warning("skipping preflight with an invalid storage key: %s", preflight.id)
    return files, _run_work_dirs(chain)


def _remove_purged_files(files: list[Path], directories: list[Path]) -> list[str]:
    """Delete what a purge owns. A file that is already gone is fine; anything else is reported."""
    errors: list[str] = []
    for path in files:
        try:
            if path.is_file():
                path.unlink()
        except Exception as exc:
            logger.warning("purge: could not remove %s", path, exc_info=True)
            errors.append(f"{path.name}: {exc}")
    for directory in directories:
        try:
            if directory.is_dir():
                shutil.rmtree(directory)
        except Exception as exc:
            logger.warning("purge: could not remove %s", directory, exc_info=True)
            errors.append(f"{directory.name}: {exc}")
    return errors


def _begin_purge(session: Session, actor_sub: str, chain: list[TranslationRunRecord]) -> None:
    """Phase one: mark the task as being purged and write the tombstone. The caller commits."""
    head = chain[-1]
    if any(member.deleted_at is None for member in chain):
        raise _disposition_error(409, "NOT_IN_TRASH", "任务不在回收站中")
    preflight = session.get(PreflightRecord, head.preflight_id)
    decisions = list(
        session.scalars(
            select(ReviewDecision)
            .where(ReviewDecision.run_id.in_([member.id for member in chain]))
            .order_by(ReviewDecision.created_at)
        )
    )
    filename = preflight.source_filename if preflight is not None else ""
    for member in chain:
        member.purge_status = "pending"
        member.purge_error = None
    # The tombstone keeps what an audit still needs after the task is gone: who decided what.
    record_audit(
        session,
        actor_sub=actor_sub,
        action="translation_run.purge",
        source_sha256=preflight.source_sha256 if preflight is not None else None,
        extra={
            "run_id": head.id,
            "preflight_id": head.preflight_id,
            "source_filename_digest": hashlib.sha256(filename.encode("utf-8")).hexdigest()[:16],
            "runs": [
                {
                    "run_id": member.id,
                    "generation": member.generation,
                    "status": member.status,
                    "quality_state": member.quality_state,
                    "deleted_at": member.deleted_at.isoformat() if member.deleted_at else None,
                    "deleted_by": member.deleted_by,
                }
                for member in chain
            ],
            "review_decisions": [
                {
                    "run_id": row.run_id,
                    "generation": row.generation,
                    "decision": row.decision,
                    "user_id": row.user_id,
                    "comment": row.comment,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in decisions
            ],
        },
    )


def _complete_purge(
    session: Session, *, tenant_id: str, preflight_id: str, actor_sub: str
) -> tuple[bool, str | None]:
    """Phase two and three, after the mark has been committed: remove files, then the rows.

    Safe to repeat. If the files cannot all be removed the rows stay, marked ``failed``, and the
    next attempt picks up where this one stopped. Rows are never deleted while files remain.
    """
    chain = list(
        session.scalars(
            select(TranslationRunRecord)
            .where(TranslationRunRecord.tenant_id == tenant_id, TranslationRunRecord.preflight_id == preflight_id)
            .order_by(TranslationRunRecord.generation)
        )
    )
    if not chain:
        return True, None
    if any(member.deleted_at is None or not member.purge_status for member in chain):
        return False, "任务没有被标记为清除"
    preflight = session.get(PreflightRecord, preflight_id)
    files, directories = _purge_files(session, chain, preflight)
    errors = _remove_purged_files(files, directories)
    if errors:
        message = "；".join(errors)[:1000]
        for member in chain:
            member.purge_status = "failed"
            member.purge_error = message
        record_audit(
            session,
            actor_sub=actor_sub,
            action="translation_run.purge_failed",
            extra={"run_id": chain[-1].id, "error": message},
        )
        session.commit()
        return False, message
    run_ids = [member.id for member in chain]
    for artifact in session.scalars(select(TranslationArtifact).where(TranslationArtifact.run_id.in_(run_ids))):
        session.delete(artifact)
    for member in chain:
        session.delete(member)
    session.flush()  # children first: the database cascades from the pre-check to its runs
    if preflight is not None:
        session.delete(preflight)
    record_audit(
        session,
        actor_sub=actor_sub,
        action="translation_run.purged",
        extra={"run_ids": run_ids, "preflight_id": preflight_id},
    )
    session.commit()
    return True, None


def _purge_chain(session: Session, actor_sub: str, chain: list[TranslationRunRecord]) -> tuple[bool, str | None]:
    head = chain[-1]
    tenant_id, preflight_id = head.tenant_id, head.preflight_id
    _begin_purge(session, actor_sub, chain)
    session.commit()  # the decision is durable before the first file is touched
    try:
        return _complete_purge(session, tenant_id=tenant_id, preflight_id=preflight_id, actor_sub=actor_sub)
    except Exception as exc:
        session.rollback()
        logger.exception("purge of %s stopped; it stays marked pending and can be retried", preflight_id)
        return False, str(exc)[:500]


@router.post("/translation-runs/{run_id}/purge")
def purge_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Permanently remove a task that is in the recycle bin. Administrators only; safe to retry."""
    run = _run_owned(session, run_id=run_id, identity=identity, include_trashed=True)
    chain = _task_chain(session, run)
    _authorize_run_action(session, identity, chain[-1], "purge")
    done, error = _purge_chain(session, identity.user_sub, chain)
    return {"id": run_id, "purged": done, "purge_status": "done" if done else "failed", "error": error}


def purge_expired_runs(
    session: Session, *, now: datetime | None = None, execute: bool = False, actor_sub: str = "system:purge"
) -> dict[str, Any]:
    """Tasks whose bin retention has run out (and earlier purges that did not finish).

    With ``execute=False`` this only reports. Automatic purging is not scheduled in the first
    release; an administrator runs scripts/plan078e-purge-expired.py.
    """
    now = now or datetime.now(timezone.utc)
    rows = list(
        session.scalars(
            select(TranslationRunRecord)
            .where(
                TranslationRunRecord.deleted_at.is_not(None),
                or_(TranslationRunRecord.purge_after <= now, TranslationRunRecord.purge_status.is_not(None)),
            )
            .order_by(TranslationRunRecord.tenant_id, TranslationRunRecord.preflight_id, TranslationRunRecord.generation)
        )
    )
    chains: dict[tuple[str, str], list[TranslationRunRecord]] = {}
    for row in rows:
        chains.setdefault((row.tenant_id, row.preflight_id), []).append(row)
    report: dict[str, Any] = {"due": len(chains), "purged": 0, "failed": 0, "executed": execute, "items": []}
    for (tenant_id, preflight_id), members in chains.items():
        chain = _task_chain(session, members[0])
        entry = {"run_id": chain[-1].id, "tenant_id": tenant_id, "purge_status": chain[-1].purge_status}
        if execute:
            if chain[-1].purge_status:
                tenant_id_, preflight_id_ = chain[-1].tenant_id, chain[-1].preflight_id
                try:
                    done, error = _complete_purge(
                        session, tenant_id=tenant_id_, preflight_id=preflight_id_, actor_sub=actor_sub
                    )
                except Exception as exc:
                    session.rollback()
                    done, error = False, str(exc)[:500]
            else:
                done, error = _purge_chain(session, actor_sub, chain)
            entry["result"] = "purged" if done else "failed"
            entry["error"] = error
            report["purged" if done else "failed"] += 1
        report["items"].append(entry)
    return report


# ----- batch actions ----------------------------------------------------------------------------------


class RunSelectionBody(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    lifecycle: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    direction: str | None = Field(default=None, max_length=64)
    domain: str | None = Field(default=None, max_length=32)
    created_from: date | None = None
    created_to: date | None = None
    archived: Literal["active", "archived", "all"] = "active"
    trash: bool = False
    group_versions: bool = True


@router.post("/translation-runs/selection")
def create_run_selection(
    body: RunSelectionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Freeze "everything the current filters match" so a later batch acts on exactly those tasks."""
    query = _task_query(
        session, identity, q=body.q, lifecycle=body.lifecycle, format=body.format, direction=body.direction,
        domain=body.domain, created_from=body.created_from, created_to=body.created_to,
        archived_mode=body.archived, status=None, sort="created", group_versions=body.group_versions,
        trash=body.trash,
    )
    ids: list[str] = []
    if query is not None:
        ranked, conditions, _task_state, _phase = query
        ids = list(
            session.scalars(
                select(ranked.c.id).where(*conditions).order_by(ranked.c.sk.desc(), ranked.c.id.desc()).limit(SELECTION_MAX + 1)
            )
        )
    if len(ids) > SELECTION_MAX:
        raise _disposition_error(
            422, "SELECTION_TOO_LARGE", f"筛选结果超过 {SELECTION_MAX} 条，请缩小范围后再批量操作"
        )
    tenant = _tenant_bundle(session, identity)
    now = datetime.now(timezone.utc)
    session.execute(delete(RunSelection).where(RunSelection.expires_at < now))
    selection = RunSelection(
        id=secrets.token_urlsafe(24),
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        scope="trash" if body.trash else "active",
        run_ids=ids,
        created_at=now,
        expires_at=now + SELECTION_TTL,
    )
    session.add(selection)
    session.commit()
    return {
        "selection_token": selection.id,
        "count": len(ids),
        "scope": selection.scope,
        "expires_at": selection.expires_at.isoformat(),
    }


class RunBatchBody(BaseModel):
    action: Literal["archive", "unarchive", "trash", "restore_from_trash", "purge"]
    ids: list[str] | None = None
    selection_token: str | None = Field(default=None, max_length=128)
    exclude_ids: list[str] = Field(default_factory=list, max_length=SELECTION_MAX)


_BATCH_AUTHORIZE_AS = {
    "archive": "archive",
    "unarchive": "restore",
    "trash": "delete",
    "restore_from_trash": "restore_from_trash",
    "purge": "purge",
}


def _http_reason(exc: HTTPException) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("code") or "ERROR"), str(detail.get("message") or detail.get("code") or "")
    return "ERROR", str(detail)


def _apply_batch_action(
    session: Session,
    identity: IdentityContext,
    action: str,
    chain: list[TranslationRunRecord],
    now: datetime,
) -> tuple[str, str, str]:
    """One task, one action: (outcome, reason_code, message). Raises HTTPException when refused."""
    head = chain[-1]
    trashed = head.deleted_at is not None
    if action == "trash":
        if trashed:
            return "skipped", "ALREADY_IN_TRASH", "任务已在回收站中"
        _refresh_translation_run(session, head)
        _authorize_run_action(session, identity, head, "delete")
        _move_task_to_trash(session, identity, chain, now)
        return "succeeded", "", ""
    if action in {"archive", "unarchive"}:
        if trashed:
            raise _disposition_error(409, "RUN_IN_TRASH", "任务在回收站中，请先恢复")
        _require_run_writer(session, identity, head)
        archiving = action == "archive"
        if (head.archived_at is not None) == archiving:
            return "skipped", "ALREADY_ARCHIVED" if archiving else "NOT_ARCHIVED", (
                "任务已归档" if archiving else "任务没有归档"
            )
        _refresh_translation_run(session, head)
        _authorize_run_action(session, identity, head, "archive" if archiving else "restore")
        head.archived_at = now if archiving else None
        head.archived_by = identity.user_sub if archiving else None
        record_audit(
            session,
            actor_sub=identity.user_sub,
            action="translation_run.archive" if archiving else "translation_run.restore",
            extra={"run_id": head.id, "batch": True},
        )
        return "succeeded", "", ""
    if action == "restore_from_trash":
        if not trashed:
            return "skipped", "NOT_IN_TRASH", "任务不在回收站中"
        _authorize_run_action(session, identity, head, "restore_from_trash")
        _restore_task_from_trash(session, identity, chain)
        return "succeeded", "", ""
    # purge: only the decision is made here; files go after the batch has been committed.
    _authorize_run_action(session, identity, head, "purge")
    _begin_purge(session, identity.user_sub, chain)
    return "succeeded", "", ""


@router.post("/translation-runs/batch")
def batch_translation_runs(
    body: RunBatchBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Apply one action to many tasks, each checked on its own against its latest state.

    The answer lists every task's outcome (succeeded, skipped or failed with a reason); one task
    failing never undoes another. The same Idempotency-Key replays the first answer.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise _disposition_error(400, "IDEMPOTENCY_KEY_REQUIRED", "批量操作需要 Idempotency-Key")
    if (body.ids is None) == (body.selection_token is None):
        raise _disposition_error(422, "SELECTION_REQUIRED", "请提供任务 ID 列表，或提供选择令牌（二选一）")
    if body.action == "purge" and not _is_run_admin(session, identity):
        raise _disposition_error(403, "ADMIN_REQUIRED", "仅管理员可以永久清除任务")
    tenant = _tenant_bundle(session, identity)
    now = datetime.now(timezone.utc)

    requested: list[str]
    if body.selection_token is not None:
        selection = session.get(RunSelection, body.selection_token)
        if selection is None or selection.tenant_id != tenant.id or selection.actor_sub != identity.user_sub:
            raise _disposition_error(404, "SELECTION_NOT_FOUND", "找不到这次选择，请重新选择")
        if _aware(selection.expires_at) < now:
            raise _disposition_error(410, "SELECTION_EXPIRED", "这次选择已过期，请重新选择")
        in_trash = body.action in {"restore_from_trash", "purge"}
        if (selection.scope == "trash") != in_trash:
            raise _disposition_error(422, "SELECTION_SCOPE_MISMATCH", "选择的任务范围与操作不匹配，请重新选择")
        excluded = set(body.exclude_ids)
        requested = [run_id for run_id in selection.run_ids if run_id not in excluded]
    else:
        if len(body.ids or []) > TRASH_BATCH_MAX_IDS:
            raise _disposition_error(422, "TOO_MANY_IDS", f"一次最多操作 {TRASH_BATCH_MAX_IDS} 个任务")
        requested = list(dict.fromkeys(body.ids or []))

    key_hash = hashlib.sha256(idempotency_key.strip().encode("utf-8")).hexdigest()
    digest = hashlib.sha256(
        json.dumps(
            {"action": body.action, "ids": sorted(requested), "token": body.selection_token}, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    existing = session.scalar(
        select(RunBatchOperation).where(
            RunBatchOperation.tenant_id == tenant.id,
            RunBatchOperation.actor_sub == identity.user_sub,
            RunBatchOperation.key_hash == key_hash,
        )
    )
    if existing is not None:
        if existing.request_digest != digest:
            raise _disposition_error(422, "IDEMPOTENCY_KEY_REUSED", "该 Idempotency-Key 已用于另一个不同的批量请求")
        return {**existing.result, "replayed": True}

    # Lock every affected task up front, in a fixed order, so two batches cannot deadlock.
    by_id: dict[str, TranslationRunRecord] = {}
    chains: dict[str, list[TranslationRunRecord]] = {}
    for start in range(0, len(requested), 400):
        part = requested[start : start + 400]
        preflight_ids = set(
            session.scalars(
                select(TranslationRunRecord.preflight_id).where(
                    TranslationRunRecord.tenant_id == tenant.id, TranslationRunRecord.id.in_(part)
                )
            )
        )
        if not preflight_ids:
            continue
        for row in session.scalars(
            select(TranslationRunRecord)
            .where(TranslationRunRecord.tenant_id == tenant.id, TranslationRunRecord.preflight_id.in_(preflight_ids))
            .order_by(TranslationRunRecord.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ):
            by_id[row.id] = row
            chains.setdefault(row.preflight_id, []).append(row)
    for members in chains.values():
        members.sort(key=lambda member: member.generation)
    names = {
        preflight.id: preflight.source_filename
        for preflight in session.scalars(select(PreflightRecord).where(PreflightRecord.id.in_(list(chains))))
    } if chains else {}
    reviewer_roles = {"reviewer", "term_admin", "admin", "owner"}
    role = _cached_role(session, identity)

    items: list[dict[str, Any]] = []
    purge_chains: list[tuple[int, str, str]] = []
    for run_id in requested:
        run = by_id.get(run_id)
        item: dict[str, Any] = {"id": run_id, "name": "", "outcome": "failed", "reason_code": "", "message": ""}
        items.append(item)
        if run is None or (run.actor_sub != identity.user_sub and role not in reviewer_roles):
            item.update(reason_code="NOT_FOUND", message="任务不存在或你无权访问")
            continue
        chain = chains[run.preflight_id]
        item["name"] = chain[-1].display_name or names.get(run.preflight_id) or ""
        try:
            with session.begin_nested():
                outcome, code, message = _apply_batch_action(session, identity, body.action, chain, now)
        except HTTPException as exc:
            code, message = _http_reason(exc)
            item.update(outcome="failed", reason_code=code, message=message)
            continue
        except Exception:
            logger.exception("batch %s failed for %s", body.action, run_id)
            item.update(reason_code="INTERNAL_ERROR", message="处理这个任务时出错，其他任务不受影响")
            continue
        item.update(outcome=outcome, reason_code=code, message=message)
        if body.action == "purge" and outcome == "succeeded":
            purge_chains.append((len(items) - 1, chain[-1].tenant_id, chain[-1].preflight_id))

    def tally() -> dict[str, Any]:
        return {
            "action": body.action,
            "requested": len(items),
            "succeeded": sum(1 for item in items if item["outcome"] == "succeeded"),
            "failed": sum(1 for item in items if item["outcome"] == "failed"),
            "skipped": sum(1 for item in items if item["outcome"] == "skipped"),
            "items": items,
        }

    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="translation_run.batch",
        extra={key: value for key, value in tally().items() if key != "items"},
    )
    operation = RunBatchOperation(
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        key_hash=key_hash,
        request_digest=digest,
        result=tally(),
    )
    session.add(operation)
    try:
        session.commit()
    except IntegrityError:
        # Another request with the same key finished first: its answer is the answer.
        session.rollback()
        winner = session.scalar(
            select(RunBatchOperation).where(
                RunBatchOperation.tenant_id == tenant.id,
                RunBatchOperation.actor_sub == identity.user_sub,
                RunBatchOperation.key_hash == key_hash,
            )
        )
        if winner is None:
            raise
        return {**winner.result, "replayed": True}

    if purge_chains:
        # The purge decisions are committed; now the files, one task at a time.
        for index, purge_tenant, purge_preflight in purge_chains:
            try:
                done, error = _complete_purge(
                    session, tenant_id=purge_tenant, preflight_id=purge_preflight, actor_sub=identity.user_sub
                )
            except Exception as exc:
                session.rollback()
                done, error = False, str(exc)[:500]
            if not done:
                items[index].update(
                    outcome="failed",
                    reason_code="PURGE_FILES_FAILED",
                    message="文件没有全部删除，任务保留在回收站并标记为清除失败，可由管理员重试",
                )
        refreshed = session.get(RunBatchOperation, operation.id)
        if refreshed is not None:
            refreshed.result = tally()
            session.commit()
    return {**tally(), "replayed": False}


def _unlink_quietly(paths: list[Path]) -> None:
    """Best-effort file cleanup after a committed delete; leftovers are orphan-GC work
    (scripts/plan072-gc-orphans.py) and must not turn a completed delete into an error."""
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            logger.warning("could not remove file after delete: %s", path, exc_info=True)


@router.get("/translation-runs/{run_id}/artifacts")
def list_translation_artifacts(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    rows = list(
        session.scalars(
            select(TranslationArtifact)
            .where(
                TranslationArtifact.run_id == run.id,
                TranslationArtifact.tenant_id == run.tenant_id,
            )
            .order_by(TranslationArtifact.created_at)
        )
    )
    return {"items": [_artifact_dict(row, run.id) for row in rows]}


@router.patch("/preflights/{preflight_id}")
def patch_preflight(
    preflight_id: str,
    body: PreflightPatchBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    record = session.get(PreflightRecord, preflight_id)
    if record is None or record.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="preflight not found")
    if record.actor_sub != identity.user_sub and _effective_role(session, identity) not in {
        "reviewer",
        "term_admin",
        "admin",
        "owner",
    }:
        raise HTTPException(status_code=404, detail="preflight not found")
    from qyunslation.pipeline.model_profiles import validate_selection

    classification = body.document_classification or record.document_classification or "internal"
    try:
        classification, model_profile_id, term_profile_id = validate_selection(
            classification=classification,
            model_profile_id=body.model_profile_id or record.model_profile_id,
            term_profile_id=body.term_model_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record.document_classification = classification
    record.model_profile_id = model_profile_id
    meta = dict(record.metadata_json or {})
    recommended = dict(meta.get("recommended") or {})
    if body.source_language:
        recommended["source_language"] = body.source_language
    if body.target_language:
        recommended["target_language"] = body.target_language
    if body.profile:
        recommended["profile"] = body.profile
    if body.domain_profile:
        source_language, target_language, direction = _normalize_language_pair(
            recommended.get("source_language"),
            recommended.get("target_language"),
            recommended.get("direction"),
        )
        _validate_domain_profile(
            preflight=record,
            domain_profile=body.domain_profile,
            direction=direction,
            document_profile=body.profile or recommended.get("profile") or "临床研究文档",
            tenant_slug=tenant.slug,
        )
        recommended["domain_profile"] = body.domain_profile.strip().casefold()
    if term_profile_id:
        recommended["term_model_profile_id"] = term_profile_id
    meta["recommended"] = recommended
    meta["document_classification"] = classification
    meta["model_profile_id"] = model_profile_id
    record.metadata_json = meta
    record.updated_at = datetime.now(timezone.utc)
    return _preflight_dict(record)


@router.get("/model-profiles")
def list_model_profiles(
    classification: str = Query(default="internal"),
    identity: IdentityContext = Depends(require_identity),
) -> dict[str, Any]:
    _ = identity
    from qyunslation.pipeline.model_profiles import profiles_payload

    return {"items": profiles_payload(classification), "classification": classification}


@router.get("/settings/schema")
def settings_schema(identity: IdentityContext = Depends(require_identity)) -> dict[str, Any]:
    _ = identity
    return {
        "sections": [
            {"key": "preferences", "title": "偏好"},
            {"key": "reading", "title": "阅读与交互"},
            {"key": "policy", "title": "系统策略", "requires": "can_manage_policy"},
        ],
        "keys": sorted(PREF_ALLOWED_KEYS),
        # One list of accepted formats and the size limit, so the upload box never disagrees with the server.
        "upload": {
            "allowed_extensions": sorted(PREFLIGHT_ALLOWED_EXTENSIONS),
            "max_bytes": DEFAULT_MAX_UPLOAD_BYTES,
        },
    }


def _tenant_policies(session: Session, tenant_id: str) -> dict[str, Any]:
    from qyunslation.persist.models import TenantPolicy

    rows = session.scalars(select(TenantPolicy).where(TenantPolicy.tenant_id == tenant_id))
    return {row.key: row for row in rows}


def _policy_value(row: Any) -> Any:
    value = row.value
    return value.get("v") if isinstance(value, dict) and "v" in value else value


def _validate_pref_value(key: str, value: Any) -> Any:
    probe = _safe_preferences({key: value})[key]
    if key in {"direction", "profile", "density"} and probe != value:
        raise HTTPException(status_code=400, detail=f"invalid value for {key}")
    return probe


@router.get("/settings/effective")
def settings_effective(
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    pref = session.scalar(
        select(WebPreference).where(
            WebPreference.tenant_id == tenant.id,
            WebPreference.user_sub == identity.user_sub,
        )
    )
    user_vals = dict((pref.preferences if pref else {}) or {})
    policies = _tenant_policies(session, tenant.id)
    effective = {}
    for key, default in PREF_DEFAULTS.items():
        policy = policies.get(key)
        if policy is not None and policy.locked:
            effective[key] = {
                "value": _policy_value(policy),
                "source": "system",
                "locked": True,
                "lock_reason": policy.reason or "由系统策略锁定",
            }
        elif key in user_vals:
            effective[key] = {
                "value": user_vals[key],
                "source": "user",
                "locked": False,
                "lock_reason": None,
            }
        elif policy is not None:
            effective[key] = {
                "value": _policy_value(policy),
                "source": "system",
                "locked": False,
                "lock_reason": None,
            }
        else:
            effective[key] = {
                "value": default,
                "source": "default",
                "locked": False,
                "lock_reason": None,
            }
    return {"effective": effective}


def _require_policy_admin(session: Session, identity: IdentityContext) -> Any:
    tenant = _tenant_bundle(session, identity)
    membership = repo.ensure_membership(
        session,
        tenant_id=tenant.id,
        user_sub=identity.user_sub,
        role=_identity_role(identity),
    )
    if membership.role not in {"admin", "owner"}:
        raise HTTPException(status_code=403, detail="admin policy access denied")
    return tenant


def _policies_payload(session: Session, tenant_id: str) -> dict[str, Any]:
    return {
        "pipeline_default": os.environ.get("QYUNSLATION_PIPELINE") or "legacy",
        "deepseek_configured": bool(
            (os.environ.get("QYUNSLATION_DEEPSEEK_API_KEY") or "").strip()
        ),
        "policies": {
            key: {
                "value": _policy_value(row),
                "locked": bool(row.locked),
                "reason": row.reason,
                "updated_by": row.updated_by,
            }
            for key, row in sorted(_tenant_policies(session, tenant_id).items())
        },
    }


@router.get("/admin/egress-audit")
def list_egress_audit(
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """PLAN-075d：按租户查询任务外发记录（模型档、外发范围、片段统计）。"""
    tenant = _require_policy_admin(session, identity)
    rows = list(
        session.scalars(
            select(TranslationRunRecord)
            .where(TranslationRunRecord.tenant_id == tenant.id)
            .order_by(TranslationRunRecord.created_at.desc())
            .limit(page_size * 4)
        ).all()
    )
    items: list[dict[str, Any]] = []
    for run in rows:
        snap = dict((run.settings_snapshot or {}).get("model_snapshot") or {})
        scope = str(snap.get("egress_scope") or "none")
        if scope == "none":
            continue
        term_summary = dict(run.term_summary or {})
        items.append(
            {
                "run_id": run.id,
                "generation": run.generation,
                "status": run.status,
                "quality_state": run.quality_state,
                "document_classification": run.document_classification,
                "model_profile_id": run.model_profile_id,
                "egress_scope": scope,
                "provider": snap.get("provider"),
                "model_id": snap.get("model_id"),
                "term_profile_id": snap.get("term_profile_id"),
                "fragment_count": term_summary.get("egress_fragment_count"),
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
        )
        if len(items) >= page_size:
            break
    return {"items": items, "count": len(items)}


@router.get("/admin/policies")
def get_admin_policies(
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _require_policy_admin(session, identity)
    return _policies_payload(session, tenant.id)


@router.put("/admin/policies")
def put_admin_policies(
    body: dict[str, Any],
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    from qyunslation.persist.models import TenantPolicy

    tenant = _require_policy_admin(session, identity)
    requested = body.get("policies") or {}
    if not isinstance(requested, dict):
        raise HTTPException(status_code=400, detail="policies must be an object")
    existing = _tenant_policies(session, tenant.id)
    for key, spec in requested.items():
        if key not in PREF_DEFAULTS:
            raise HTTPException(status_code=400, detail=f"unknown policy key: {key}")
        if spec is None:
            if key in existing:
                session.delete(existing[key])
            continue
        if not isinstance(spec, dict) or "value" not in spec:
            raise HTTPException(status_code=400, detail=f"policy {key} needs a value")
        value = _validate_pref_value(key, spec["value"])
        locked = bool(spec.get("locked"))
        reason = str(spec.get("reason") or "")[:256] or None
        if locked and not reason:
            raise HTTPException(status_code=400, detail=f"locked policy {key} requires a reason")
        row = existing.get(key)
        if row is None:
            session.add(
                TenantPolicy(
                    tenant_id=tenant.id,
                    key=key,
                    value={"v": value},
                    locked=locked,
                    reason=reason,
                    updated_by=identity.user_sub,
                )
            )
        else:
            row.value = {"v": value}
            row.locked = locked
            row.reason = reason
            row.updated_by = identity.user_sub
            row.updated_at = datetime.now(timezone.utc)
    session.flush()
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="web.policy.update",
        extra={"keys": sorted(requested)},
    )
    return _policies_payload(session, tenant.id)


@router.get("/translation-runs/{run_id}/events")
def list_translation_run_events(
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    generation: int | None = Query(default=None),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    from qyunslation.pipeline.event_store import event_to_dict, list_events

    rows = list_events(
        session,
        run_id=run.id,
        generation=generation if generation is not None else run.generation,
        after_sequence=after_sequence,
    )
    return {"items": [event_to_dict(row) for row in rows], "generation": run.generation}


def _qa_item_payload(
    row: QaItem,
    *,
    history: list[QaDisposition] | None = None,
    digest: str | None = None,
    viewer: tuple[str, str] | None = None,
    run: TranslationRunRecord | None = None,
    prior: dict[str, QaDisposition] | None = None,
) -> dict[str, Any]:
    from qyunslation.pipeline.qa import registry

    info = registry.rule_for(row.code)
    rule_class = row.rule_class or info.rule_class
    location = dict(row.location_json or {})
    location.setdefault("anchors", [])
    if not location["anchors"]:
        location.setdefault(
            "unlocatable_reason",
            info.unlocatable_reason if info.locatable == "none" else "检查没有返回具体位置",
        )
    history = history or []
    state = _effective_item_state(history, digest)
    last = state["last"]
    allowed: list[str] = []
    if viewer is not None and run is not None and run.status == "gated" and (run.quality_state or "draft") in _QA_GATE_STATES:
        allowed = registry.allowed_actions(rule_class, viewer[1], is_writer=run.actor_sub == viewer[0])
    return {
        "id": row.id,
        "category": row.category,
        "severity": row.severity,
        "code": row.code,
        "message": row.message,
        "object_id": row.object_id,
        "evidence": row.evidence_json,
        "resolved": bool(state["closed"] or row.resolved),
        "title": info.title,
        "why": info.why,
        "how": info.how,
        "rule_class": rule_class,
        "fingerprint": _item_fingerprint(row),
        "location": location,
        "round_id": row.round_id,
        "is_current": bool(row.is_current),
        "batchable": info.batchable,
        "status": state["status"],
        "previous_disposition": state["previous"],
        # An exception granted for the previous *version* is shown, never silently inherited.
        "prior_version_disposition": (
            _disposition_dict(prior[_item_fingerprint(row)])
            if prior and not state["closed"] and _item_fingerprint(row) in prior
            else None
        ),
        "disposition": _disposition_dict(last) if last is not None else None,
        "history": [_disposition_dict(h) for h in history],
        "allowed_dispositions": allowed,
    }


def _prior_version_dispositions(session: Session, run: TranslationRunRecord) -> dict[str, QaDisposition]:
    """Latest *closing* disposition per finding on the version this one was revised from."""
    origin = (run.settings_snapshot or {}).get("revision_of") or {}
    if not origin.get("run_id"):
        return {}
    rows = session.scalars(
        select(QaDisposition)
        .where(
            QaDisposition.run_id == origin["run_id"],
            QaDisposition.generation == int(origin.get("generation") or 1),
            QaDisposition.action.in_(tuple(_CLOSING_ACTIONS)),
        )
        .order_by(QaDisposition.created_at, QaDisposition.id)
    )
    latest: dict[str, QaDisposition] = {}
    for row in rows:
        latest[row.fingerprint] = row
    return {fp: row for fp, row in latest.items() if row.action in _CLOSED_BY}


def _disposition_dict(row: QaDisposition) -> dict[str, Any]:
    return {
        "id": row.id,
        "action": row.action,
        "reason": row.reason,
        "actor_sub": row.actor_sub,
        "actor_role": row.actor_role,
        "self_review": bool(row.self_review),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/qa-rules")
def list_qa_rules(identity: IdentityContext = Depends(require_identity)) -> dict[str, Any]:
    """The published rule book: what each check means and what may be done about it."""
    from qyunslation.pipeline.qa import registry

    return {
        "rule_set_version": registry.rule_set_version(),
        "items": [
            {
                "code": rule.code,
                "rule_class": rule.rule_class,
                "title": rule.title,
                "why": rule.why,
                "how": rule.how,
                "locatable": rule.locatable,
                "batchable": rule.batchable,
            }
            for rule in registry.all_rules()
        ],
    }


@router.get("/translation-runs/{run_id}/qa-items")
def list_qa_items(
    run_id: str,
    include_history: bool = Query(default=False),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    stmt = select(QaItem).where(QaItem.run_id == run.id, QaItem.generation == run.generation)
    if not include_history:
        stmt = stmt.where(QaItem.is_current.is_(True))
    rows = list(session.scalars(stmt.order_by(QaItem.created_at)))
    grouped = _qa_dispositions_by_fingerprint(session, run)
    digest = _current_output_digest(session, run)
    viewer = (identity.user_sub, _cached_role(session, identity))
    prior = _prior_version_dispositions(session, run)
    return {
        "items": [
            _qa_item_payload(
                row,
                history=grouped.get(_item_fingerprint(row), []),
                digest=digest,
                viewer=viewer,
                run=run,
                prior=prior,
            )
            for row in rows
        ],
        "summary": run.qa_summary or {},
        "quality_state": run.quality_state,
        "check": _qa_check_info(session, run),
    }


class QaDispositionBody(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    reason: str = Field(default="", max_length=1000)
    expected_round_id: str | None = Field(default=None, max_length=36)


class QaDispositionBatchBody(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    reason: str = Field(default="", max_length=1000)
    item_ids: list[str] = Field(min_length=1, max_length=50)


def _disposition_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _apply_disposition(
    session: Session,
    run: TranslationRunRecord,
    identity: IdentityContext,
    item: QaItem | None,
    *,
    action: str,
    reason: str,
    expected_round_id: str | None = None,
) -> QaDisposition:
    """Record one disposition after every rule check. Raises HTTPException; writes only on success."""
    from qyunslation.pipeline.qa import registry

    if item is None or item.run_id != run.id or item.generation != run.generation:
        raise _disposition_error(404, "ITEM_NOT_FOUND", "没有找到这条质量问题")
    if run.status != "gated" or (run.quality_state or "draft") not in _QA_GATE_STATES:
        if run.status == "gated" and (run.quality_state or "draft") == "draft":
            raise _disposition_error(409, "QA_CHECK_RUNNING", "质量检查正在进行，完成后才能处置")
        raise _disposition_error(409, "NOT_AT_GATE", "任务当前不在质量闸门，不能处置质量问题")
    if not item.is_current:
        raise _disposition_error(409, "ITEM_SUPERSEDED", "这条问题属于旧一轮检查，请刷新后处理最新的问题")
    if expected_round_id is not None and expected_round_id != (item.round_id or ""):
        raise _disposition_error(409, "STALE_ROUND", "检查结果已更新，请刷新后再处置")
    info = registry.rule_for(item.code)
    rule_class = item.rule_class or info.rule_class
    classes = registry.ACTION_CLASSES.get(action)
    if classes is None:
        raise _disposition_error(422, "UNKNOWN_ACTION", "不支持的处置动作")
    if rule_class not in classes:
        raise _disposition_error(
            422, "ACTION_NOT_ALLOWED_FOR_CLASS", f"该类问题不允许此处置（{info.title}）；请按建议修复后重新检查"
        )
    role = _cached_role(session, identity)
    is_writer = run.actor_sub == identity.user_sub
    if action not in registry.allowed_actions(rule_class, role, is_writer=is_writer):
        raise _disposition_error(403, "DISPOSITION_FORBIDDEN", "当前账号没有权限执行此处置")
    clean_reason = (reason or "").strip()
    if len(clean_reason) < 10:
        raise _disposition_error(422, "REASON_REQUIRED", "请写明理由（至少 10 个字），它会被记入审计")

    fingerprint = _item_fingerprint(item)
    digest = _current_output_digest(session, run)
    history = _qa_dispositions_by_fingerprint(session, run).get(fingerprint, [])
    state = _effective_item_state(history, digest)
    last = state["last"]
    if last is not None and last.action == action and last.actor_sub == identity.user_sub:
        return last  # repeating the same decision is a no-op, not a second record
    if action == "confirm_false_positive":
        pending = state["pending_report"]
        if pending is None:
            raise _disposition_error(409, "NO_REPORT_TO_CONFIRM", "没有待确认的误报反馈")
        if pending.actor_sub == identity.user_sub:
            raise _disposition_error(409, "NEEDS_SECOND_PERSON", "误报需要由反馈人以外的人确认")
    elif action == "reject_false_positive":
        if state["pending_report"] is None:
            raise _disposition_error(409, "NO_REPORT_TO_REJECT", "没有待处理的误报反馈")
    elif action == "revoke_waiver":
        if state["closing"] is None or state["closing"].action != "grant_waiver":
            raise _disposition_error(409, "NOTHING_TO_REVOKE", "这条问题没有可撤销的例外")
    elif action == "grant_waiver" and state["closed"]:
        return state["closing"]

    row = QaDisposition(
        run_id=run.id,
        generation=run.generation,
        fingerprint=fingerprint,
        code=item.code,
        rule_class=rule_class,
        round_id=item.round_id,
        artifact_digest=digest,
        action=action,
        reason=clean_reason[:1000],
        evidence_json={"severity": item.severity, "title": info.title},
        actor_sub=identity.user_sub,
        actor_role=role,
        self_review=bool(is_writer and action != "report_false_positive"),
    )
    session.add(row)
    if not item.fingerprint:  # old finding: store the identity we just relied on
        item.fingerprint, item.rule_class = fingerprint, rule_class
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="qa.disposition",
        extra={
            "run_id": run.id,
            "generation": run.generation,
            "code": item.code,
            "rule_class": rule_class,
            "fingerprint": fingerprint,
            "disposition": action,
            "self_review": row.self_review,
        },
    )
    session.flush()
    return row


def _item_response(session: Session, run: TranslationRunRecord, item: QaItem, identity: IdentityContext) -> dict[str, Any]:
    grouped = _qa_dispositions_by_fingerprint(session, run)
    return _qa_item_payload(
        item,
        history=grouped.get(_item_fingerprint(item), []),
        digest=_current_output_digest(session, run),
        viewer=(identity.user_sub, _cached_role(session, identity)),
        run=run,
    )


@router.post("/translation-runs/{run_id}/qa-items/{item_id}/dispositions")
def post_qa_disposition(
    run_id: str,
    item_id: str,
    body: QaDispositionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    item = session.get(QaItem, item_id)
    _apply_disposition(
        session, run, identity, item,
        action=body.action, reason=body.reason, expected_round_id=body.expected_round_id,
    )
    _reconcile_with_dispositions(session, run)
    return _item_response(session, run, item, identity)


@router.post("/translation-runs/{run_id}/qa-dispositions/batch")
def post_qa_dispositions_batch(
    run_id: str,
    body: QaDispositionBatchBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Apply one decision to several findings of the *same* low-risk code; each is checked alone."""
    from qyunslation.pipeline.qa import registry

    run = _run_owned(session, run_id=run_id, identity=identity)
    items = {item_id: session.get(QaItem, item_id) for item_id in dict.fromkeys(body.item_ids)}
    found = [item for item in items.values() if item is not None and item.run_id == run.id]
    codes = {item.code for item in found}
    if len(codes) > 1:
        raise _disposition_error(422, "MIXED_CODES", "批量处置只能针对同一类问题")
    for code in codes:
        if not registry.rule_for(code).batchable:
            raise _disposition_error(422, "NOT_BATCHABLE", "这类问题必须逐项处理，不支持批量")
    results: list[dict[str, Any]] = []
    for item_id, item in items.items():
        try:
            _apply_disposition(session, run, identity, item, action=body.action, reason=body.reason)
            results.append({"item_id": item_id, "outcome": "succeeded"})
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR", "message": str(exc.detail)}
            results.append(
                {"item_id": item_id, "outcome": "failed", "code": detail.get("code"), "message": detail.get("message")}
            )
    _reconcile_with_dispositions(session, run)
    return {"results": results}


@router.get("/translation-runs/{run_id}/review-draft")
def get_review_draft(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    row = session.scalar(
        select(ReviewDraft).where(
            ReviewDraft.run_id == run.id,
            ReviewDraft.generation == run.generation,
            ReviewDraft.user_id == identity.user_sub,
        )
    )
    if row is None:
        return {
            "comment": "",
            "resolved_qa_ids": [],
            "payload": {},
            "updated_at": None,
        }
    return {
        "comment": row.comment or "",
        "resolved_qa_ids": list(row.resolved_qa_ids or []),
        "payload": dict(row.payload_json or {}),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/translation-runs/{run_id}/review-draft")
def put_review_draft(
    run_id: str,
    body: ReviewDraftBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    row = session.scalar(
        select(ReviewDraft).where(
            ReviewDraft.run_id == run.id,
            ReviewDraft.generation == run.generation,
            ReviewDraft.user_id == identity.user_sub,
        )
    )
    if row is None:
        row = ReviewDraft(
            run_id=run.id,
            generation=run.generation,
            user_id=identity.user_sub,
            comment=body.comment,
            resolved_qa_ids=list(body.resolved_qa_ids or []),
            payload_json=dict(body.payload or {}),
        )
        session.add(row)
    else:
        row.comment = body.comment
        row.resolved_qa_ids = list(body.resolved_qa_ids or [])
        row.payload_json = dict(body.payload or {})
        row.updated_at = datetime.now(timezone.utc)
    session.flush()
    return get_review_draft(run_id, identity=identity, session=session)


@router.post("/translation-runs/{run_id}/review-decision")
def post_review_decision(
    run_id: str,
    body: ReviewDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    role = _effective_role(session, identity)
    if role not in {"reviewer", "term_admin", "admin", "owner"}:
        raise HTTPException(status_code=403, detail="reviewer role required")
    decision = (body.decision or "").strip().casefold()
    if decision not in {"approve", "request_changes", "reject"}:
        raise HTTPException(status_code=400, detail="invalid decision")
    formal_gate = _formal_gate(session, run)
    if decision == "approve" and not formal_gate["passed"]:
        raise HTTPException(status_code=409, detail={"message": "formal gate blocked", **formal_gate})
    row = ReviewDecision(
        run_id=run.id,
        generation=run.generation,
        decision=decision,
        user_id=identity.user_sub,
        comment=body.comment,
        qa_snapshot=dict(run.qa_summary or {}),
        term_snapshot=dict(run.term_summary or {}),
        model_snapshot={
            "model_profile_id": run.model_profile_id,
            "document_classification": run.document_classification,
            "settings": dict(run.settings_snapshot or {}),
        },
    )
    session.add(row)
    draft = session.scalar(
        select(ReviewDraft).where(
            ReviewDraft.run_id == run.id,
            ReviewDraft.generation == run.generation,
            ReviewDraft.user_id == identity.user_sub,
        )
    )
    if draft is not None:
        session.delete(draft)
    if decision == "approve":
        run.quality_state = "approved"
        run.status = "succeeded"
        run.stage = "export"
        run.progress = 100
        run.completed_at = run.completed_at or datetime.now(timezone.utc)
        session.flush()
        _refresh_translation_run(session, run)
        try:
            from qyunslation.pipeline.event_store import persist_buffer
            from qyunslation.pipeline.events import StageEventBuffer

            buf = StageEventBuffer()
            buf.emit("review", "completed", message=f"已批准 · {identity.user_sub}")
            buf.emit("export", "completed", message="正式产物已解锁", progress=100.0)
            persist_buffer(session, run_id=run.id, generation=run.generation, buffer=buf)
        except Exception:
            pass
    elif decision == "request_changes":
        # Nothing re-executes here: the run is parked until someone creates a revision.
        run.quality_state = "changes_requested"
        run.stage = "review"
        run.status = "gated"
    else:
        run.quality_state = "draft"
        run.status = "failed"
        run.stage = "review"
        run.degradation_reason = "rejected by reviewer"
        run.completed_at = datetime.now(timezone.utc)
    run.updated_at = datetime.now(timezone.utc)
    return _translation_run_dict(session, run, identity=identity)


def _preview_target(path: Path, media: str, filename: str) -> tuple[Path, str, str]:
    """图片直传；DOCX/PPTX 转受保护 PDF，失败返回稳定错误码。"""
    from qyunslation.pipeline.office_preview import (
        IMAGE_MEDIA,
        OFFICE_SUFFIXES,
        OfficePreviewError,
        office_to_pdf,
    )

    suffix = path.suffix.casefold()
    if suffix in IMAGE_MEDIA:
        return path, IMAGE_MEDIA[suffix], filename
    if suffix in OFFICE_SUFFIXES and path.is_file():
        try:
            converted = office_to_pdf(path)
        except OfficePreviewError as exc:
            status = 501 if exc.code == "OFFICE_PREVIEW_UNAVAILABLE" else 502
            raise HTTPException(
                status_code=status, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        return converted, "application/pdf", f"{Path(filename).stem}.preview.pdf"
    return path, media, filename


def _translation_preview_rank(filename: str, file_type: str = "") -> int:
    """Prefer the mono translation when a run produced both PDF variants."""
    identity = f"{filename} {file_type}".casefold()
    if re.search(r"(?:^|[._-])mono(?:[._-]|$)", identity):
        return 0
    if re.search(r"(?:^|[._-])dual(?:[._-]|$)", identity):
        return 2
    return 1


@router.get("/translation-runs/{run_id}/preview/{side}")
def preview_translation_run(
    run_id: str,
    side: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
):
    """Authorized inline preview; does not expose storage paths."""
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    if side not in {"source", "translated"}:
        raise HTTPException(status_code=404, detail="preview side not found")
    if side == "source":
        preflight = session.get(PreflightRecord, run.preflight_id)
        if preflight is None:
            raise HTTPException(status_code=404, detail="source preview unavailable")
        path = _preflight_path(preflight)
        media = "application/pdf" if path.suffix.casefold() == ".pdf" else "application/octet-stream"
        filename = preflight.source_filename
        path, media, filename = _preview_target(path, media, filename)
    else:
        approved = getattr(run, "quality_state", None) in {"approved", "legacy_unverified"}
        allowed_kinds = ["translated_preview", "review_draft", "legacy"]
        if approved:
            allowed_kinds.append("formal")
        artifacts = list(
            session.scalars(
                select(TranslationArtifact)
                .where(
                    TranslationArtifact.run_id == run.id,
                    TranslationArtifact.tenant_id == run.tenant_id,
                    TranslationArtifact.kind.in_(allowed_kinds),
                )
                .order_by(TranslationArtifact.created_at.desc())
            )
        )
        # CLI runs may publish both `*.mono.pdf` and `*.dual.pdf`. The viewer
        # already places the source PDF in its own pane, so its translated pane
        # should show the standalone translation when that artifact exists.
        artifact = min(
            artifacts,
            key=lambda item: _translation_preview_rank(item.filename, item.file_type),
            default=None,
        )
        if artifact is None:
            # Fall back to runner outputs for v2 layout_complete without formal gate.
            try:
                from qyunslation.workbench.runner import get_pdf2zh_task_state

                state = get_pdf2zh_task_state(run.external_task_id or "")
            except Exception:
                state = None
            files = (state or {}).get("downloadable_files") or {}
            candidates = [
                (key, meta)
                for key, meta in files.items()
                if isinstance(meta, dict)
            ]
            _, first = min(
                candidates,
                key=lambda item: _translation_preview_rank(
                    str(item[1].get("filename") or Path(str(item[1].get("path") or "")).name),
                    str(item[0]),
                ),
                default=(None, None),
            )
            if not first:
                raise HTTPException(status_code=404, detail="translated preview unavailable")
            path = Path(str(first["path"]))
            media = mimetypes.guess_type(path.name)[0] or "application/pdf"
            filename = str(first.get("filename") or path.name)
        else:
            path = _artifact_path(artifact)
            media = artifact.media_type
            filename = artifact.filename
        path, media, filename = _preview_target(path, media, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="preview file missing")
    return FileResponse(
        path=path,
        media_type=media,
        filename=filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=60", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/translation-runs/{run_id}/artifacts/{artifact_id}")
def download_translation_artifact(
    run_id: str,
    artifact_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
):
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    artifact = session.scalar(
        select(TranslationArtifact).where(
            TranslationArtifact.id == artifact_id,
            TranslationArtifact.run_id == run.id,
            TranslationArtifact.tenant_id == run.tenant_id,
        )
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="translation artifact not found")
    quality_state = getattr(run, "quality_state", None) or "draft"
    if artifact.formal_export:
        allowed = (
            (run.status == "succeeded" and quality_state == "approved")
            or quality_state == "legacy_unverified"
            or artifact.kind == "legacy"
        )
        if not allowed:
            raise HTTPException(
                status_code=409,
                detail="formal export requires approved quality_state and succeeded status",
            )
    path = _artifact_path(artifact)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="translation artifact is no longer available")
    return FileResponse(
        path=path,
        media_type=artifact.media_type,
        filename=artifact.filename,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/translation-runs/{run_id}/cancel")
async def cancel_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _require_run_writer(session, identity, run)
    _refresh_translation_run(session, run)
    discarding = run.status == "gated"
    if run.status in _RUN_TERMINAL and not discarding:
        return _translation_run_dict(session, run, identity=identity)
    if run.external_task_id and not discarding:
        try:
            from qyunslation.workbench.runner import (
                cancel_pdf2zh_task,
                is_pdf2zh_task,
            )

            if is_pdf2zh_task(run.external_task_id):
                await cancel_pdf2zh_task(run.external_task_id)
            else:
                from qyunslation.server import get_translation_service

                get_translation_service().cancel_task(run.external_task_id)
        except Exception as exc:
            raise HTTPException(status_code=409, detail="translation runner could not cancel the task") from exc
    run.status = "cancelled"
    run.stage = "qa"
    run.progress = run.progress if run.progress is not None else None
    run.degradation_reason = (
        "discarded by user at the quality gate" if discarding else "translation cancelled by user"
    )
    run.completed_at = run.completed_at or datetime.now(timezone.utc)
    run.updated_at = datetime.now(timezone.utc)
    return _translation_run_dict(session, run, identity=identity)


def _ensure_preflight_usable(
    session: Session, preflight: PreflightRecord | None, *, actor_sub: str
) -> PreflightRecord:
    """A task that already uses a source file may keep using it after the 24h pre-check window.

    The window exists to clean up uploads nobody turned into a task. Retrying, resuming or
    revising is exactly "a task needs its source again", so the window is re-armed instead of
    forcing a new upload. Only a source that is really gone is an error, and it says so.
    """
    if preflight is None:
        raise _disposition_error(409, "SOURCE_UNAVAILABLE", "找不到该任务的原文件，请重新上传后翻译")
    if (preflight.status or "") != "ready":
        raise _disposition_error(409, "PREFLIGHT_NOT_READY", "原文件预检未通过，不能继续")
    try:
        present = _preflight_path(preflight).is_file()
    except HTTPException:
        present = False
    if not present:
        raise _disposition_error(409, "SOURCE_UNAVAILABLE", "原文件已被清理，无法继续，请重新上传后翻译")
    if _preflight_dict(preflight)["state"] == "expired":
        preflight.expires_at = datetime.now(timezone.utc) + timedelta(hours=PREFLIGHT_TTL_HOURS)
        record_audit(
            session,
            actor_sub=actor_sub,
            action="preflight.rearm",
            extra={"preflight_id": preflight.id, "reason": "task_still_uses_source"},
        )
        session.flush()
    return preflight


async def _spawn_next_generation(
    session: Session,
    run: TranslationRunRecord,
    identity: IdentityContext,
    *,
    key_prefix: str,
    snap: dict[str, Any],
    columns: dict[str, Any] | None = None,
    expect_digest: str | None = None,
) -> TranslationRunRecord:
    """Create (once) the next version of a run from its frozen configuration and start it."""
    preflight = session.get(PreflightRecord, run.preflight_id)
    _ensure_preflight_usable(session, preflight, actor_sub=identity.user_sub)
    next_generation = run.generation + 1
    existing = session.scalar(
        select(TranslationRunRecord).where(
            TranslationRunRecord.preflight_id == run.preflight_id,
            TranslationRunRecord.generation == next_generation,
        )
    )
    if existing is not None:
        if expect_digest and (existing.settings_snapshot or {}).get("config_digest") != expect_digest:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REVISION_EXISTS",
                    "message": "该任务已经有一个用不同参数生成的新版本",
                    "run_id": existing.id,
                },
            )
        return existing
    columns = columns or {}
    key = hashlib.sha256(f"{key_prefix}:{run.id}:{next_generation}".encode("utf-8")).hexdigest()
    snap = dict(snap)
    snap["revision_of"] = {"run_id": run.id, "generation": run.generation}
    snap["requested_by"] = identity.user_sub
    new = TranslationRunRecord(
        preflight_id=run.preflight_id,
        tenant_id=run.tenant_id,
        actor_sub=run.actor_sub,  # the task keeps its submitter; who asked is recorded below
        idempotency_key_hash=hashlib.sha256(key.encode("utf-8")).hexdigest(),
        generation=next_generation,
        direction=run.direction,
        profile=run.profile,
        display_name=columns.get("display_name", run.display_name),
        settings_snapshot=snap,
        status="queued",
        stage="validation",
        quality_state="draft",
        document_classification=columns.get("document_classification", run.document_classification),
        model_profile_id=columns.get("model_profile_id", run.model_profile_id),
        term_summary={"status": "snapshot_pending"},
        qa_summary={"blocker": 0, "warning": 0, "info": 0},
    )
    session.add(new)
    session.flush()
    _carry_frozen_ad_prompt(session, run, new)
    await _launch_translation_run(
        run=new,
        preflight=preflight,
        target_language=_run_target_language(new.direction),
        session=session,
    )
    return new


_REVISION_OVERRIDABLE = frozenset(
    {"model_profile_id", "term_model_profile_id", "document_classification", "bilingual", "display_name"}
)
_REVISION_AD_LOCKED = frozenset({"model_profile_id", "term_model_profile_id", "document_classification"})


def _apply_revision_overrides(
    session: Session, run: TranslationRunRecord, snap: dict[str, Any], overrides: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parameters changed at confirmation become a new, validated configuration for the new version.

    Only settings that do not change the source-derived inputs can be overridden here; anything
    else (languages, document type, domain, which feed the frozen AD prompt) needs a new task
    from the original file, and the answer says so.
    """
    from qyunslation.pipeline import resolve_pipeline_mode
    from qyunslation.pipeline.model_profiles import default_term_profile_id, validate_selection
    from qyunslation.pipeline.run_snapshot import build_run_model_snapshot

    unknown = sorted(set(overrides) - _REVISION_OVERRIDABLE)
    if unknown:
        raise _disposition_error(422, "OVERRIDE_NOT_SUPPORTED", f"这些参数需要从原文件新建任务，不能在修订版里修改：{', '.join(unknown)}")
    domain = str(snap.get("domain_profile") or "general").casefold()
    if domain == "ad" and _REVISION_AD_LOCKED & set(overrides):
        raise _disposition_error(422, "OVERRIDE_NOT_SUPPORTED_FOR_AD", "AD 任务的模型和资料等级与已冻结的提示词绑定，请从原文件新建任务")
    snap = dict(snap)
    classification = overrides.get("document_classification") or run.document_classification or "internal"
    model = overrides.get("model_profile_id") or run.model_profile_id
    if overrides.get("term_model_profile_id"):
        term = overrides["term_model_profile_id"]
    elif {"document_classification", "model_profile_id"} & set(overrides):
        term = default_term_profile_id(classification)  # the old term model may not be allowed any more
    else:
        term = snap.get("term_model_profile_id") or default_term_profile_id(classification)
    try:
        classification, model, term = validate_selection(
            classification=classification, model_profile_id=model, term_profile_id=term
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    preflight = session.get(PreflightRecord, run.preflight_id)
    pdf = bool(preflight and preflight.source_format.casefold() == "pdf")
    bilingual = bool(overrides["bilingual"]) if "bilingual" in overrides else bool(snap.get("bilingual", True))
    mode = build_run_model_snapshot(
        classification=classification,
        translator_id=model,
        term_id=term,
        termbase_version=(snap.get("model_snapshot") or {}).get("termbase_version"),
        pipeline=snap.get("pipeline") or resolve_pipeline_mode(None),
    )
    snap.update(mode)
    snap.update(
        {
            "document_classification": classification,
            "model_profile_id": model,
            "term_model_profile_id": term,
            "bilingual": bilingual,
            "bilingual_effective": bilingual and pdf,
            "revision_overrides": sorted(overrides),
        }
    )
    snap["config_digest"] = _run_config_digest(
        preflight_id=run.preflight_id,
        direction=run.direction,
        profile=run.profile,
        domain_profile=domain,
        bilingual=bilingual,
        classification=classification,
        model_profile_id=model,
        term_model_profile_id=term,
    )
    snap["config_digest_v"] = 2
    columns: dict[str, Any] = {"document_classification": classification, "model_profile_id": model}
    if "display_name" in overrides:
        columns["display_name"] = (str(overrides["display_name"] or "").strip() or None)
    return snap, columns


def _approved_affiliation_overrides(session: Session, run: TranslationRunRecord) -> dict[str, str]:
    segments = list(
        session.scalars(
            select(ReviewSegment).where(
                ReviewSegment.translation_run_id == run.id,
                ReviewSegment.generation == run.generation,
                ReviewSegment.role == "affiliation",
                ReviewSegment.status == "approved",
            )
        ).all()
    )
    return {
        segment.source_text: segment.revised_text
        for segment in segments
        if segment.revised_text
        and segment.revised_text.strip()
        and segment.revised_text.strip() != (segment.machine_text or "").strip()
    }


def _carry_frozen_ad_prompt(session: Session, source: TranslationRunRecord, target: TranslationRunRecord) -> None:
    """New generations of an AD run must reuse the frozen prompt text.

    The frozen prompt lives in the per-run directory; without carrying the
    identical text (same digest as the copied prompt_snapshot) the launch
    blocks with "AD prompt digest mismatch".  Earlier generations are searched
    too, so a generation that itself failed to launch does not strand the chain.
    """
    if str((target.settings_snapshot or {}).get("domain_profile") or "general").casefold() != "ad":
        return
    expected = str(dict((target.settings_snapshot or {}).get("prompt_snapshot") or {}).get("digest") or "")
    try:
        from qyunslation.pipeline.ad_prompt_store import load_frozen_prompt, write_frozen_prompt
        from qyunslation.workbench.runner import get_pdf2zh_runner

        runner = get_pdf2zh_runner()
        candidates = [source] + list(
            session.scalars(
                select(TranslationRunRecord)
                .where(
                    TranslationRunRecord.preflight_id == target.preflight_id,
                    TranslationRunRecord.id != target.id,
                )
                .order_by(TranslationRunRecord.generation.desc())
            )
        )
        loaded = None
        for candidate in candidates:
            found = load_frozen_prompt(
                runner._run_dir(tenant_id=candidate.tenant_id, run_id=candidate.id, generation=candidate.generation)
            )
            if found is not None and (not expected or str(found[1].get("digest") or "") == expected):
                loaded = found
                break
        if loaded is None:
            raise RuntimeError("no earlier generation holds a frozen prompt with the expected digest")
        write_frozen_prompt(
            runner._run_dir(tenant_id=target.tenant_id, run_id=target.id, generation=target.generation),
            text=loaded[0],
            snapshot=loaded[1],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "AD_PROMPT_UNAVAILABLE", "message": f"failed to carry frozen prompt: {exc}"},
        ) from exc


@router.post("/translation-runs/{run_id}/retry", status_code=201)
async def retry_translation_run(
    run_id: str,
    body: RetryTranslationBody | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    if run.status not in _RUN_TERMINAL:
        raise HTTPException(status_code=409, detail="only terminal translation runs can be retried")
    preflight = session.get(PreflightRecord, run.preflight_id)
    _ensure_preflight_usable(session, preflight, actor_sub=identity.user_sub)
    snap = dict(run.settings_snapshot or {})
    requested_pipeline = ((body.pipeline if body else None) or "").strip().casefold()
    if requested_pipeline == "v2":
        snap["pipeline"] = "v2"
        snap["pipeline_requested"] = "v2"
        snap["retry_of"] = {"run_id": run.id, "generation": run.generation}
    retry = await _spawn_next_generation(session, run, identity, key_prefix="retry", snap=snap)
    return _translation_run_dict(session, retry, identity=identity)


class RevisionBody(BaseModel):
    pipeline: str | None = Field(default=None, max_length=32)
    apply_review_corrections: bool = False
    # PLAN-078c: parameters changed at confirmation (model, class, output mode, name).
    overrides: dict[str, Any] | None = None


@router.post("/translation-runs/{run_id}/revisions", status_code=201)
async def create_translation_revision(
    run_id: str,
    body: RevisionBody | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Fix-and-recheck: a new version from the same frozen configuration.

    The old version is frozen (superseded) and keeps its findings; the new version's first
    check reports what changed against it. Calling this again returns the same new version.
    """
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    if run.status not in _RUN_TERMINAL:
        raise HTTPException(status_code=409, detail="only runs that have finished executing can be revised")
    snap = dict(run.settings_snapshot or {})
    requested_pipeline = ((body.pipeline if body else None) or "").strip().casefold()
    if requested_pipeline == "v2":
        snap["pipeline"] = "v2"
        snap["pipeline_requested"] = "v2"
    if body is not None and body.apply_review_corrections:
        if _effective_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}:
            raise HTTPException(status_code=403, detail="reviewer role required")
        overrides = _approved_affiliation_overrides(session, run)
        if not overrides:
            raise HTTPException(status_code=409, detail="no edited affiliation translations to apply")
        snap["review_overrides"] = overrides
        snap["correction_of"] = {"run_id": run.id, "generation": run.generation}
    columns: dict[str, Any] = {}
    expect_digest = None
    if body is not None and body.overrides:
        snap, columns = _apply_revision_overrides(session, run, snap, body.overrides)
        expect_digest = snap["config_digest"]
    revision = await _spawn_next_generation(
        session, run, identity, key_prefix="retry", snap=snap, columns=columns, expect_digest=expect_digest
    )
    return _translation_run_dict(session, revision, identity=identity)


@router.post("/translation-runs/{run_id}/resume")
async def resume_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    if run.status not in _RUN_RESUMABLE:
        raise HTTPException(status_code=409, detail="only interrupted runs can be resumed")
    preflight = session.get(PreflightRecord, run.preflight_id)
    _ensure_preflight_usable(session, preflight, actor_sub=identity.user_sub)
    _clear_persisted_executor_outputs(run)
    # Resuming produces new output; the verdict for the previous output no longer applies
    # and the run must be checked again when its executor finishes.
    session.query(QaItem).filter(
        QaItem.run_id == run.id, QaItem.generation == run.generation
    ).update({QaItem.is_current: False}, synchronize_session=False)
    run.quality_state = "draft"
    run.qa_summary = {"blocker": 0, "unavailable": 0, "warning": 0, "info": 0}
    run.status = "queued"
    run.stage = "validation"
    run.progress = None
    run.degradation_reason = None
    run.completed_at = None
    run.external_task_id = None
    session.flush()
    await _launch_translation_run(
        run=run,
        preflight=preflight,
        target_language=_run_target_language(run.direction),
        session=session,
        resume=True,
    )
    return _translation_run_dict(session, run, identity=identity)


def _requalify_translation_run(
    session: Session,
    run: TranslationRunRecord,
    *,
    runner_state: dict[str, Any] | None = None,
) -> None:
    """PLAN-073b：用修复后的规则/术语重新检查，不重新翻译。

    PLAN-078a: it is the same pass as the first check (term extraction, degraded-service
    handling, rule version, events), run as a new round. Registering is idempotent: a
    second click while a round is live changes nothing.
    """
    from qyunslation.pipeline.qa import rounds

    if rounds.active_round(session, run.id, run.generation) is None:
        run.quality_state = "draft"
        run.stage = "qa"
    _schedule_qa_round(session, run, trigger="requalify")


@router.post("/translation-runs/{run_id}/requalify")
async def requalify_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    if run.status == "gated" and (run.quality_state or "draft") == "draft":
        # A check is already running (double click, second tab): answer with its state.
        return _translation_run_dict(session, run, identity=identity)
    if run.status != "gated" or (run.quality_state or "draft") not in {
        "qa_blocked",
        "qa_unavailable",
        "qa_degraded",
        "review_ready",
    }:
        raise HTTPException(status_code=409, detail="run is not at the quality gate")
    _requalify_translation_run(session, run)
    session.flush()
    return _translation_run_dict(session, run, identity=identity)


@router.get("/translation-runs/{run_id}/term-candidates")
def list_run_term_candidates(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=40, ge=1, le=100),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    rows = list(session.scalars(
        select(DocumentTermCandidate)
        .where(DocumentTermCandidate.translation_run_id == run.id)
        .options(
            selectinload(DocumentTermCandidate.occurrences),
            selectinload(DocumentTermCandidate.decisions),
        )
        .order_by(DocumentTermCandidate.created_at.desc())
    ).unique().all())
    from qyunslation.persist.candidate_repo import candidate_to_dict
    from qyunslation.workbench.term_extract import term_suggester_info

    start = (page - 1) * page_size
    selected = rows[start : start + page_size]
    return {
        "items": [candidate_to_dict(row) for row in selected],
        "page": page,
        "page_size": page_size,
        "total": len(rows),
        "unresolved": sum(row.status not in _FINAL_TERM_STATUSES for row in rows),
        "suggester": term_suggester_info(run),
        "rules": {
            "version": (run.term_summary or {}).get("rule_version"),
            "included_regions": ["标题", "摘要", "正文", "章节标题", "图表", "脚注"],
            "excluded_regions": ["作者", "研究单位", "参考文献", "地址/邮箱", "页眉页脚", "注册编号"],
            "method": [
                "词库、形态和缩写规则确定性提取",
                "结构化模型补充疾病与机制短语",
                "候选必须逐字存在于源文",
                "词库命中、通用词、统计词、碎片、乱码和历史拒绝词不进入新候选",
                "按规范化词形去重并保留全部出现位置；每页默认 40 条",
            ],
        },
    }


def _decide_run_candidate(
    session: Session,
    *,
    run: TranslationRunRecord,
    candidate: DocumentTermCandidate,
    body: RunTermDecisionBody,
    identity: IdentityContext,
) -> dict[str, Any]:
    from qyunslation.persist.candidate_repo import CandidateConflict, decide_candidate

    if candidate.translation_run_id != run.id or candidate.tenant_id != run.tenant_id:
        raise HTTPException(status_code=404, detail="term candidate not found")
    action = body.action.strip().casefold()
    role = _effective_role(session, identity)
    high_risk = candidate.risk.strip().casefold() in {"high", "critical"}
    owner_review = run.actor_sub == identity.user_sub
    if (
        high_risk
        and action in {"approve", "do_not_translate", "merge"}
        and role not in {"term_admin", "admin", "owner"}
        and not owner_review
    ):
        raise HTTPException(status_code=403, detail="term_admin role required for high-risk term")
    if action == "submit_for_admin" and not high_risk:
        raise HTTPException(status_code=400, detail="only high-risk candidates require administrator review")
    try:
        result = decide_candidate(
            session,
            candidate=candidate,
            actor_sub=identity.user_sub,
            action=action,
            expected_version=body.expected_version,
            target_term=body.target_term,
            note=body.note,
            scope="org",
        )
    except CandidateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action=f"translation_run.term.{action}",
        source_sha256=candidate.source_sha256,
        extra={"run_id": run.id, "candidate_id": candidate.id},
    )
    return result


@router.post("/translation-runs/{run_id}/term-candidates/{candidate_id}/decision")
def decide_run_term_candidate(
    run_id: str,
    candidate_id: str,
    body: RunTermDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    if not _can_review_run(session, identity, run):
        raise HTTPException(status_code=403, detail="reviewer role required")
    candidate = session.get(DocumentTermCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="term candidate not found")
    return _decide_run_candidate(
        session, run=run, candidate=candidate, body=body, identity=identity
    )


@router.post("/translation-runs/{run_id}/term-candidates/batch-decision")
def batch_decide_run_term_candidates(
    run_id: str,
    body: RunTermBatchDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    if not _can_review_run(session, identity, run):
        raise HTTPException(status_code=403, detail="reviewer role required")
    decided: list[dict[str, Any]] = []
    for item in body.decisions:
        candidate = session.get(DocumentTermCandidate, item.candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="term candidate not found")
        action = item.action.strip().casefold()
        if action == "approve" and candidate.risk.strip().casefold() in {"high", "critical"}:
            raise HTTPException(status_code=400, detail="high-risk terms require individual review")
        decided.append(
            _decide_run_candidate(
                session, run=run, candidate=candidate, body=item, identity=identity
            )
        )
    return {"decided": decided, "count": len(decided), "formal_gate": _formal_gate(session, run)}


@router.post("/translation-runs/{run_id}/term-candidates/enrich-suggestions")
def enrich_run_term_candidate_suggestions(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Use termbase + DeepSeek to backfill suggested_target for pending candidates."""
    run = _run_owned(session, run_id=run_id, identity=identity)
    if not _can_review_run(session, identity, run):
        raise HTTPException(status_code=403, detail="reviewer role required")
    from qyunslation.workbench.term_extract import enrich_run_term_suggestions

    updated = enrich_run_term_suggestions(session, run=run)
    session.commit()
    listing = list_run_term_candidates(
        run_id,
        page=1,
        page_size=40,
        identity=identity,
        session=session,
    )
    listing["suggestions_enriched"] = updated
    return listing


@router.get("/translation-runs/{run_id}/affiliation-segments")
def list_run_affiliation_segments(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    rows = list(
        session.scalars(
            select(ReviewSegment)
            .where(
                ReviewSegment.translation_run_id == run.id,
                ReviewSegment.generation == run.generation,
                ReviewSegment.role == "affiliation",
            )
            .options(selectinload(ReviewSegment.notes))
            .order_by(ReviewSegment.page_no, ReviewSegment.created_at)
        ).all()
    )
    from qyunslation.persist.review_repo import segment_to_dict

    return {
        "items": [segment_to_dict(row) for row in rows],
        "unconfirmed": sum(row.status != "approved" for row in rows),
    }


@router.patch("/translation-runs/{run_id}/affiliation-segments/{segment_id}")
def decide_run_affiliation_segment(
    run_id: str,
    segment_id: str,
    body: AffiliationDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    if _effective_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        raise HTTPException(status_code=403, detail="reviewer role required")
    segment = session.get(ReviewSegment, segment_id)
    if (
        segment is None
        or segment.translation_run_id != run.id
        or segment.generation != run.generation
        or segment.role != "affiliation"
    ):
        raise HTTPException(status_code=404, detail="affiliation segment not found")
    if segment.version != body.expected_version:
        raise HTTPException(status_code=409, detail="affiliation segment version conflict; refresh required")
    from qyunslation.persist.review_repo import ReviewError, decide_segment

    job = session.get(Job, segment.job_id)
    try:
        result = decide_segment(
            session,
            segment=segment,
            tenant_id=run.tenant_id,
            actor_sub=identity.user_sub,
            action="approve",
            revised_text=body.revised_text,
            project_id=job.project_id if job else None,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="translation_run.affiliation.approve",
        source_sha256=segment.source_sha256,
        extra={"run_id": run.id, "segment_id": segment.id},
    )
    return {**result, "formal_gate": _formal_gate(session, run)}


@router.post("/translation-runs/{run_id}/apply-corrections", status_code=201)
async def apply_run_corrections(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    if _effective_role(session, identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        raise HTTPException(status_code=403, detail="reviewer role required")
    newer = session.scalar(
        select(TranslationRunRecord.id).where(
            TranslationRunRecord.preflight_id == run.preflight_id,
            TranslationRunRecord.generation > run.generation,
        ).limit(1)
    )
    if newer:
        raise HTTPException(status_code=409, detail="this artifact has already been superseded")
    overrides = _approved_affiliation_overrides(session, run)
    if not overrides:
        raise HTTPException(status_code=409, detail="no edited affiliation translations to apply")
    snap = {
        **dict(run.settings_snapshot or {}),
        "review_overrides": overrides,
        "correction_of": {"run_id": run.id, "generation": run.generation},
    }
    retry = await _spawn_next_generation(session, run, identity, key_prefix="correction", snap=snap)
    return _translation_run_dict(session, retry, identity=identity)


class PreferencesBody(BaseModel):
    preferences: dict[str, Any] = Field(default_factory=dict)


def _safe_preferences(raw: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(PREF_DEFAULTS)
    for key, value in (raw or {}).items():
        if key in PREF_ALLOWED_KEYS:
            merged[key] = value
    if merged["direction"] not in {"English → 简体中文", "简体中文 → English"}:
        merged["direction"] = PREF_DEFAULTS["direction"]
    if merged["profile"] not in {"临床研究文档", "监管申报材料", "通用医药文档"}:
        merged["profile"] = PREF_DEFAULTS["profile"]
    if merged["density"] not in {"comfortable", "compact"}:
        merged["density"] = PREF_DEFAULTS["density"]
    for key in ("bilingual", "reduceMotion", "largeText"):
        if not isinstance(merged[key], bool):
            merged[key] = bool(merged[key])
    merged["workbench"] = _safe_workbench_preferences(raw)
    return merged


@router.get("/preferences")
def get_preferences(
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    row = session.query(WebPreference).filter_by(tenant_id=tenant.id, user_sub=identity.user_sub).first()
    raw = dict((row.preferences if row else {}) or {})
    locked: list[str] = []
    for key, policy in _tenant_policies(session, tenant.id).items():
        if policy.locked:
            raw[key] = _policy_value(policy)
            locked.append(key)
        elif key not in raw:
            raw[key] = _policy_value(policy)
    return {
        "preferences": _safe_preferences(raw),
        "source": "personal",
        "locked": sorted(locked),
    }


@router.put("/preferences")
def put_preferences(
    body: PreferencesBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    clean = _safe_preferences(body.preferences)
    for key, policy in _tenant_policies(session, tenant.id).items():
        if not policy.locked:
            continue
        locked_value = _policy_value(policy)
        if key in (body.preferences or {}) and body.preferences[key] != locked_value:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PREFERENCE_LOCKED",
                    "key": key,
                    "reason": policy.reason or "由系统策略锁定",
                },
            )
        clean[key] = locked_value
    row = session.query(WebPreference).filter_by(tenant_id=tenant.id, user_sub=identity.user_sub).first()
    if row is None:
        row = WebPreference(tenant_id=tenant.id, user_sub=identity.user_sub, preferences=clean)
        session.add(row)
    else:
        row.preferences = clean
    session.flush()
    record_audit(session, actor_sub=identity.user_sub, action="web.preference.update", extra={"keys": sorted(clean)})
    return {"preferences": clean, "source": "personal"}


@router.get("/projects")
def list_projects(
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    rows = repo.list_projects(session, tenant_id=tenant.id)
    return [
        {
            "id": p.id,
            "tenant_id": p.tenant_id,
            "slug": p.slug,
            "name": p.name,
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]


@router.post("/projects", status_code=201)
def create_project(
    body: ProjectCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    project = repo.create_project(
        session, tenant_id=tenant.id, slug=body.slug, name=body.name
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="project.create",
        extra={"project_id": project.id, "slug": project.slug},
    )
    return {
        "id": project.id,
        "tenant_id": project.tenant_id,
        "slug": project.slug,
        "name": project.name,
        "created_at": project.created_at.isoformat(),
    }


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    project = repo.get_project(session, project_id=project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {
        "id": project.id,
        "tenant_id": project.tenant_id,
        "slug": project.slug,
        "name": project.name,
        "created_at": project.created_at.isoformat(),
    }


@router.get("/jobs")
def list_jobs(
    project_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    project = repo.get_project(session, project_id=project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    rows = repo.list_jobs(session, project_id=project.id)
    return [_job_dict(j) for j in rows]


@router.post("/jobs", status_code=201)
def create_job(
    body: JobCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    digest = body.source_sha256.strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        raise HTTPException(status_code=400, detail="source_sha256 must be 64 hex chars")
    tenant = _tenant_bundle(session, identity)
    project = repo.get_project(session, project_id=body.project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    provenance = None
    if body.attach_gateway_provenance:
        from qyunslation.gateway.config import ProfileNotWiredError, build_provenance

        try:
            provenance = build_provenance()
        except ProfileNotWiredError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = repo.create_job(
        session,
        project_id=project.id,
        source_sha256=digest,
        storage_key=body.storage_key,
        provenance=provenance,
    )
    # authorization 故意传入以验证审计剥离
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="job.create",
        source_sha256=digest,
        extra={"job_id": job.id, "project_id": project.id, "authorization": "REDACT_ME"},
    )
    return _job_dict(job)


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = repo.get_job(session, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    project = repo.get_project(session, project_id=job.project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_dict(job)


class ProvenanceBody(BaseModel):
    provenance: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default=None, max_length=32)
    # 调用方可传 api_key；服务端必须剥离
    api_key: str | None = None


@router.post("/jobs/{job_id}/provenance")
def set_job_provenance(
    job_id: str,
    body: ProvenanceBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = repo.get_job(session, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    project = repo.get_project(session, project_id=job.project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="job not found")
    merged = dict(body.provenance or {})
    # 故意可能带入的密钥字段
    if body.api_key:
        merged["api_key"] = body.api_key
    cleaned = sanitize_extra(merged) or {}
    for bad in ("api_key", "apikey", "authorization", "password", "secret", "token"):
        cleaned.pop(bad, None)
    if "endpoint" in cleaned:
        from qyunslation.structure.model_trace import strip_endpoint

        cleaned["endpoint"] = strip_endpoint(str(cleaned["endpoint"]))
    repo.attach_provenance(session, job=job, provenance=cleaned, status=body.status)
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="job.provenance",
        source_sha256=job.source_sha256,
        extra={"job_id": job.id, "api_key": "should-strip", "keys": sorted(cleaned.keys())},
    )
    return _job_dict(job)


class ConceptCreate(BaseModel):
    preferred_source: str = Field(min_length=1, max_length=512)
    preferred_target: str = Field(min_length=1, max_length=512)
    src_lng: str = Field(default="en", max_length=16)
    tgt_lng: str = Field(default="zh", max_length=16)
    domain: str = Field(default="", max_length=64)
    layer: str = Field(default="session", max_length=32)
    evidence: str | None = None
    do_not_translate: bool = False
    # 调用方即使传 curated 也强制 staging
    status: str | None = None
    forbidden: list[dict[str, str]] = Field(default_factory=list)
    project_id: str | None = Field(default=None, max_length=36)
    term_type: str = Field(default="general", max_length=64)


@router.get("/concepts")
def list_concepts_api(
    status: str | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import concept_to_dict, list_concepts

    rows = list_concepts(session, status=status, tenant_id=tenant.id)
    return [concept_to_dict(c) for c in rows]


@router.post("/concepts", status_code=201)
def create_concept_api(
    body: ConceptCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import concept_to_dict, create_staging_concept

    forbidden = [
        (str(item.get("lang") or ""), str(item.get("text") or ""))
        for item in body.forbidden
    ]
    if body.project_id and repo.get_project(
        session, project_id=body.project_id, tenant_id=tenant.id
    ) is None:
        raise HTTPException(status_code=404, detail="project not found")
    concept = create_staging_concept(
        session,
        domain=body.domain,
        layer=body.layer,
        preferred_source=body.preferred_source,
        preferred_target=body.preferred_target,
        src_lng=body.src_lng,
        tgt_lng=body.tgt_lng,
        evidence=body.evidence,
        do_not_translate=body.do_not_translate,
        forbidden=forbidden,
        tenant_id=tenant.id,
        project_id=body.project_id,
        term_type=body.term_type,
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="concept.create_staging",
        extra={
            "concept_id": concept.id,
            "requested_status": body.status,
            "api_key": "should-strip",
        },
    )
    return concept_to_dict(concept)


# --- PLAN-058 术语预解析 / 译后候选闭环 ---


class TermResolveRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=20000)
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)


class TermOccurrenceBody(BaseModel):
    page_no: int | None = Field(default=None, ge=1)
    block_id: str | None = Field(default=None, max_length=128)
    object_id: str | None = Field(default=None, max_length=128)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox: dict[str, Any] | None = None
    source_context: str | None = Field(default=None, max_length=20000)
    target_context: str | None = Field(default=None, max_length=20000)


class TermCandidateBody(BaseModel):
    source_term: str = Field(min_length=1, max_length=512)
    observed_target: str = Field(default="", max_length=512)
    suggested_target: str | None = Field(default=None, max_length=512)
    term_type: str = Field(default="general", max_length=64)
    risk: str = Field(default="normal", max_length=32)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    match_type: str = Field(default="candidate", max_length=32)
    source_context: str | None = Field(default=None, max_length=20000)
    target_context: str | None = Field(default=None, max_length=20000)
    occurrences: list[TermOccurrenceBody] = Field(default_factory=list, max_length=1000)


class TermExtractBody(BaseModel):
    candidates: list[TermCandidateBody] = Field(min_length=1, max_length=1000)
    termbase_version: str | None = Field(default=None, max_length=128)


class TermCandidateDecisionBody(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    expected_version: int = Field(ge=1)
    target_term: str | None = Field(default=None, max_length=512)
    concept_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=10000)
    scope: str = Field(default="project", max_length=32)
    aliases: list[str] = Field(default_factory=list, max_length=50)
    abbreviations: list[str] = Field(default_factory=list, max_length=50)


class TermBatchDecisionItem(TermCandidateDecisionBody):
    candidate_id: str = Field(min_length=1, max_length=36)


class TermBatchDecisionBody(BaseModel):
    decisions: list[TermBatchDecisionItem] = Field(min_length=1, max_length=200)


class TermPromoteBody(BaseModel):
    scope: str = Field(min_length=1, max_length=32)
    project_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=10000)


def _term_admin_membership(session: Session, *, tenant_id: str, user_sub: str):
    membership = repo.ensure_membership(session, tenant_id=tenant_id, user_sub=user_sub)
    return membership, membership.role in {"term_admin", "admin", "owner"}


@router.post("/terms/resolve")
def resolve_terms_api(
    body: TermResolveRequest,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    if body.project_id and repo.get_project(
        session, project_id=body.project_id, tenant_id=tenant.id
    ) is None:
        raise HTTPException(status_code=404, detail="project not found")
    from qyunslation.glossary.termbase import (
        match_to_dict,
        resolve_runtime_terms,
        runtime_termbase_version,
    )
    from qyunslation.glossary.term_policy import compile_term_policy

    matches = resolve_runtime_terms(
        session,
        tenant_id=tenant.id,
        project_id=body.project_id,
        text=body.source_text,
        src_lang=body.src_lang,
        tgt_lang=body.tgt_lang,
    )
    termbase_version = runtime_termbase_version(
        session, tenant_id=tenant.id, project_id=body.project_id
    )
    policy = compile_term_policy(matches, termbase_version=termbase_version)
    return {
        "matches": [match_to_dict(match) for match in matches],
        "policy": policy,
        "termbase_version": termbase_version,
        # 058c 首版只有本地确定性命中；语义候选接入后由实际路径置 true。
        "semantic_used": any(match.match_type == "semantic" for match in matches),
    }


@router.get("/terms/search")
def search_terms_api(
    source_text: str = Query(min_length=1, max_length=20000),
    project_id: str | None = Query(default=None, max_length=36),
    src_lang: str = Query(default="en", max_length=16),
    tgt_lang: str = Query(default="zh", max_length=16),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    exact = resolve_terms_api(
        TermResolveRequest(
            source_text=source_text,
            project_id=project_id,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
        ),
        identity,
        session,
    )
    from qyunslation.persist.term_embedding_repo import semantic_search_concept_terms

    suggestions = semantic_search_concept_terms(
        session,
        tenant_id=_tenant_bundle(session, identity).id,
        project_id=project_id,
        query=source_text,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        limit=5,
        threshold=0.88,
    )
    exact["semantic_suggestions"] = suggestions
    exact["semantic_used"] = bool(suggestions)
    return exact


@router.post("/jobs/{job_id}/terms/extract", status_code=201)
def extract_job_terms_api(
    job_id: str,
    body: TermExtractBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import candidate_to_dict, enqueue_candidate

    created = []
    for item in body.candidates:
        candidate = enqueue_candidate(
            session,
            job=job,
            tenant_id=tenant.id,
            project_id=job.project_id,
            source_term=item.source_term,
            observed_target=item.observed_target,
            suggested_target=item.suggested_target,
            term_type=item.term_type,
            risk=item.risk,
            confidence=item.confidence,
            match_type=item.match_type,
            source_context=item.source_context,
            target_context=item.target_context,
            termbase_version=body.termbase_version,
            occurrences=[occurrence.model_dump() for occurrence in item.occurrences],
        )
        created.append(candidate_to_dict(candidate))
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="term.candidate.extract",
        source_sha256=job.source_sha256,
        extra={"job_id": job.id, "count": len(created), "api_key": "should-strip"},
    )
    return {"created": created, "count": len(created)}


@router.get("/jobs/{job_id}/terms")
def list_job_terms_api(
    job_id: str,
    status: str | None = Query(default=None, max_length=32),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import candidate_to_dict, list_candidates

    rows = list_candidates(
        session,
        tenant_id=tenant.id,
        job_id=job.id,
        project_id=job.project_id,
        status=status,
    )
    return [candidate_to_dict(row) for row in rows]


@router.post("/jobs/{job_id}/terms/{candidate_id}/decide")
def decide_job_term_api(
    job_id: str,
    candidate_id: str,
    body: TermCandidateDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import (
        CandidateConflict,
        decide_candidate,
        get_candidate,
    )

    candidate = get_candidate(
        session, candidate_id=candidate_id, tenant_id=tenant.id, job_id=job.id
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="term candidate not found")
    scope = body.scope.strip().casefold()
    membership, is_term_admin = _term_admin_membership(
        session, tenant_id=tenant.id, user_sub=identity.user_sub
    )
    if scope != "project":
        if not is_term_admin:
            raise HTTPException(status_code=403, detail="term_admin role required")
    action = body.action.strip().casefold()
    high_risk = candidate.risk.strip().casefold() in {"high", "critical"}
    if action == "submit_for_admin":
        if not high_risk:
            raise HTTPException(status_code=400, detail="only high-risk candidates require administrator review")
    elif (high_risk or candidate.status == "pending_admin") and not is_term_admin:
        raise HTTPException(status_code=403, detail="term_admin role required for high-risk term")
    try:
        result = decide_candidate(
            session,
            candidate=candidate,
            actor_sub=identity.user_sub,
            action=body.action,
            expected_version=body.expected_version,
            target_term=body.target_term,
            concept_id=body.concept_id,
            note=body.note,
            scope=scope,
            aliases=body.aliases,
            abbreviations=body.abbreviations,
        )
    except CandidateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action=f"term.candidate.{body.action.strip().lower()}",
        source_sha256=job.source_sha256,
        extra={
            "job_id": job.id,
            "candidate_id": candidate.id,
            "concept_id": result.get("concept_id"),
            "api_key": "should-strip",
        },
    )
    return result


@router.post("/jobs/{job_id}/terms/batch-decide")
def batch_decide_job_terms_api(
    job_id: str,
    body: TermBatchDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import (
        CandidateConflict,
        decide_candidate,
        get_candidate,
    )

    results = []
    for item in body.decisions:
        candidate = get_candidate(
            session, candidate_id=item.candidate_id, tenant_id=tenant.id, job_id=job.id
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="term candidate not found")
        scope = item.scope.strip().casefold()
        _membership, is_term_admin = _term_admin_membership(
            session, tenant_id=tenant.id, user_sub=identity.user_sub
        )
        if scope != "project":
            if not is_term_admin:
                raise HTTPException(status_code=403, detail="term_admin role required")
        # 未知、语义或多义候选必须逐条确认，避免批量操作绕过风险控制。
        if item.action.strip().casefold() == "approve" and (
            candidate.match_type not in {"exact", "alias"}
            or candidate.risk.strip().casefold() in {"high", "critical"}
            or candidate.status != "pending"
        ):
            raise HTTPException(
                status_code=400,
                detail=f"candidate {candidate.id} is not eligible for batch approval",
            )
        try:
            results.append(
                decide_candidate(
                    session,
                    candidate=candidate,
                    actor_sub=identity.user_sub,
                    action=item.action,
                    expected_version=item.expected_version,
                    target_term=item.target_term,
                    concept_id=item.concept_id,
                    note=item.note,
                    scope=scope,
                    aliases=item.aliases,
                    abbreviations=item.abbreviations,
                )
            )
        except CandidateConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"decided": results, "count": len(results)}


@router.get("/jobs/{job_id}/term-review-summary")
def term_review_summary_api(
    job_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import list_candidates

    rows = list_candidates(
        session,
        tenant_id=tenant.id,
        job_id=job.id,
        project_id=job.project_id,
        limit=1000,
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    unresolved_high_risk = [
        row
        for row in rows
        if row.risk.strip().casefold() in {"high", "critical"}
        and row.status != "approved"
    ]
    return {
        "job_id": job.id,
        "total": len(rows),
        "pending": counts.get("pending", 0),
        "pending_admin": counts.get("pending_admin", 0),
        "applied": counts.get("applied", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "high_risk_unresolved": len(unresolved_high_risk),
        "formal_gate": {
            "passed": not unresolved_high_risk,
            "blocking_candidate_ids": [row.id for row in unresolved_high_risk],
        },
    }


@router.post("/concepts/{concept_id}/promote")
def promote_concept_api(
    concept_id: str,
    body: TermPromoteBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    membership = repo.ensure_membership(
        session, tenant_id=tenant.id, user_sub=identity.user_sub
    )
    if membership.role not in {"term_admin", "admin", "owner"}:
        raise HTTPException(status_code=403, detail="term_admin role required")
    from qyunslation.persist.concept_repo import concept_to_dict, get_concept

    concept = get_concept(session, concept_id)
    if concept is None or concept.tenant_id not in {None, tenant.id}:
        raise HTTPException(status_code=404, detail="concept not found")
    scope = body.scope.strip().casefold()
    if scope not in {"org", "form", "clinical", "project"}:
        raise HTTPException(status_code=400, detail="invalid promotion scope")
    if body.project_id and repo.get_project(
        session, project_id=body.project_id, tenant_id=tenant.id
    ) is None:
        raise HTTPException(status_code=404, detail="project not found")
    if scope == "project" and not body.project_id:
        raise HTTPException(status_code=400, detail="project_id is required for project scope")
    concept.status = "curated"
    concept.layer = scope
    concept.tenant_id = tenant.id
    concept.project_id = body.project_id if scope == "project" else None
    concept.evidence = (
        f"{concept.evidence or ''};promoted_by:{identity.user_sub};note:{body.note or ''}"
    )
    concept.version += 1
    session.flush()
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="concept.promote",
        extra={"concept_id": concept.id, "scope": scope, "api_key": "should-strip"},
    )
    return concept_to_dict(concept)

class TmUnitCreate(BaseModel):
    source_text: str = Field(min_length=1, max_length=20000)
    target_text: str = Field(min_length=1, max_length=20000)
    approved: bool | None = None  # true → 400；正式库只走审校 decide
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)


class TmLookupRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=20000)
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)
    fuzzy_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    fuzzy_limit: int = Field(default=5, ge=0, le=20)
    semantic_limit: int = Field(default=5, ge=0, le=20)


class TmImportBody(BaseModel):
    tmx: str = Field(min_length=1, max_length=8 * 1024 * 1024)
    project_id: str | None = Field(default=None, max_length=36)


@router.post("/tm/units", status_code=201)
def create_tm_unit_api(
    body: TmUnitCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import stage_import_unit, tm_unit_to_dict

    if body.approved is True:
        raise HTTPException(
            status_code=400,
            detail="formal TM only via review decide; POST /tm/units writes staging",
        )
    if body.project_id:
        project = repo.get_project(
            session, project_id=body.project_id, tenant_id=tenant.id
        )
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
    unit = stage_import_unit(
        session,
        tenant_id=tenant.id,
        source_text=body.source_text,
        target_text=body.target_text,
        project_id=body.project_id,
        src_lang=body.src_lang,
        tgt_lang=body.tgt_lang,
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="tm.unit.stage",
        extra={
            "unit_id": unit.id,
            "approved": False,
            "api_key": "should-strip",
        },
    )
    return tm_unit_to_dict(unit)


@router.post("/tm/lookup")
def tm_lookup_api(
    body: TmLookupRequest,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import lookup

    return lookup(
        session,
        tenant_id=tenant.id,
        source_text=body.source_text,
        src_lang=body.src_lang,
        tgt_lang=body.tgt_lang,
        project_id=body.project_id,
        fuzzy_threshold=body.fuzzy_threshold,
        fuzzy_limit=body.fuzzy_limit,
        semantic_limit=body.semantic_limit,
    )


@router.get("/tm/export.tmx")
def tm_export_tmx_api(
    src_lang: str = "en",
    tgt_lang: str = "zh",
    project_id: str | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> Response:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import list_approved_units
    from qyunslation.tm.tmx import build_tmx

    units = list_approved_units(
        session,
        tenant_id=tenant.id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        project_id=project_id,
    )
    xml = build_tmx(units, src_lang=src_lang, tgt_lang=tgt_lang)
    return Response(content=xml, media_type="application/xml")


@router.post("/tm/import.tmx")
def tm_import_tmx_api(
    body: TmImportBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import stage_import_unit, tm_unit_to_dict
    from qyunslation.tm.tmx import parse_tmx

    try:
        parsed = parse_tmx(body.tmx)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid TMX: {exc}") from exc

    created = []
    for item in parsed:
        unit = stage_import_unit(
            session,
            tenant_id=tenant.id,
            source_text=item.source_text,
            target_text=item.target_text,
            project_id=body.project_id,
            src_lang=item.src_lang or "en",
            tgt_lang=item.tgt_lang or "zh",
        )
        created.append(tm_unit_to_dict(unit))
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="tm.tmx.import",
        extra={"count": len(created), "api_key": "should-strip"},
    )
    return {"imported": len(created), "units": created, "note": "imported as approved=false"}


class QaRunBody(BaseModel):
    source_text: str = Field(min_length=1)
    target_text: str = ""
    role: str = "body"
    domain: str = ""
    forbidden: list[str] = Field(default_factory=list)
    table_qc_codes: list[str] = Field(default_factory=list)
    page_qc_codes: list[str] = Field(default_factory=list)
    enable_repair: bool = False
    enable_review: bool = False
    job_id: str | None = Field(default=None, max_length=36)
    # 测试用：传入则跳过真实 provider，用该字符串作为 repair 结果
    mock_repaired_text: str | None = None


@router.post("/qa/run")
def qa_run_api(
    body: QaRunBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = None
    if body.job_id:
        from qyunslation.persist.review_repo import job_owned_by_tenant

        job = job_owned_by_tenant(session, job_id=body.job_id, tenant_id=tenant.id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.gateway.pipeline import run_segment_pipeline

    provider = None
    if body.mock_repaired_text is not None:

        class _Mock:
            def translate(self, source: str, *, system: str | None = None) -> str:
                return body.target_text or source

            def review(self, source: str, target: str, *, findings: list[str] | None = None) -> str:
                return "PASS"

            def repair(self, source: str, target: str, *, findings: list[str] | None = None) -> str:
                return body.mock_repaired_text or target

        provider = _Mock()
    elif body.enable_repair or body.enable_review:
        try:
            from qyunslation.gateway.provider import get_provider

            provider = get_provider()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"provider unavailable: {exc}") from exc

    out = run_segment_pipeline(
        body.source_text,
        target=body.target_text,
        role=body.role,
        domain=body.domain,
        forbidden=body.forbidden or None,
        table_qc_codes=body.table_qc_codes or None,
        page_qc_codes=body.page_qc_codes or None,
        provider=provider,
        enable_review=body.enable_review,
        enable_repair=body.enable_repair,
    )
    if job is not None and out.get("qa", {}).get("blocked"):
        repo.attach_provenance(
            session,
            job=job,
            provenance=job.provenance or {"qa_blocked": True},
            status="qa_blocked",
        )
        out["job_status"] = "qa_blocked"
        out["job_id"] = job.id
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="qa.run",
        extra={
            "blocked": out.get("qa", {}).get("blocked"),
            "repaired": out.get("repaired"),
            "api_key": "should-strip",
        },
    )
    return out


class ReviewEnqueueItem(BaseModel):
    # 上限对齐 ORM 列宽，避免超长值到 PG 才报 500
    source_text: str = Field(min_length=1, max_length=20000)
    machine_text: str = Field(default="", max_length=20000)
    block_id: str | None = Field(default=None, max_length=128)
    policy: str = Field(default="TRANSLATE", max_length=32)
    role: str = Field(default="body", max_length=64)


class ReviewEnqueueBody(BaseModel):
    job_id: str = Field(min_length=1, max_length=36)
    segments: list[ReviewEnqueueItem] = Field(min_length=1, max_length=500)


class ReviewNoteBody(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class ReviewDecideBody(BaseModel):
    action: str = Field(min_length=1, max_length=16)  # approve | reject
    revised_text: str | None = Field(default=None, max_length=20000)
    promote_term: bool = False
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)


@router.post("/review/enqueue")
def review_enqueue_api(
    body: ReviewEnqueueBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import (
        enqueue_segments,
        job_owned_by_tenant,
        segment_to_dict,
    )

    job = job_owned_by_tenant(session, job_id=body.job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    items = [s.model_dump() for s in body.segments]
    created, skipped = enqueue_segments(session, job=job, items=items)
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="review.enqueue",
        source_sha256=job.source_sha256,
        extra={
            "job_id": job.id,
            "created": len(created),
            "skipped": len(skipped),
            "api_key": "should-strip",
        },
    )
    return {
        "created": [segment_to_dict(s) for s in created],
        "skipped": skipped,
        "count": len(created),
    }


@router.get("/review/queue")
def review_queue_api(
    job_id: str | None = None,
    status: str | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import list_queue, segment_to_dict

    rows = list_queue(session, tenant_id=tenant.id, job_id=job_id, status=status)
    return [segment_to_dict(s) for s in rows]


@router.post("/review/segments/{segment_id}/note", status_code=201)
def review_note_api(
    segment_id: str,
    body: ReviewNoteBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import add_note, get_segment_for_tenant

    seg = get_segment_for_tenant(session, segment_id=segment_id, tenant_id=tenant.id)
    if seg is None:
        raise HTTPException(status_code=404, detail="segment not found")
    note = add_note(
        session, segment=seg, author_sub=identity.user_sub, body=body.body
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="review.segment.note",
        source_sha256=seg.source_sha256,
        extra={"segment_id": seg.id, "api_key": "should-strip"},
    )
    return {
        "id": note.id,
        "segment_id": seg.id,
        "author_sub": note.author_sub,
        "body": note.body,
        "created_at": note.created_at.isoformat(),
    }


@router.post("/review/segments/{segment_id}/decide")
def review_decide_api(
    segment_id: str,
    body: ReviewDecideBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import (
        ReviewError,
        decide_segment,
        get_segment_for_tenant,
        job_owned_by_tenant,
    )

    seg = get_segment_for_tenant(session, segment_id=segment_id, tenant_id=tenant.id)
    if seg is None:
        raise HTTPException(status_code=404, detail="segment not found")
    job = job_owned_by_tenant(session, job_id=seg.job_id, tenant_id=tenant.id)
    project_id = job.project_id if job else None
    try:
        result = decide_segment(
            session,
            segment=seg,
            tenant_id=tenant.id,
            actor_sub=identity.user_sub,
            action=body.action,
            revised_text=body.revised_text,
            promote_term=body.promote_term,
            project_id=project_id,
            src_lang=body.src_lang,
            tgt_lang=body.tgt_lang,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    action = body.action.strip().lower()
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action=f"review.segment.{action}",
        source_sha256=seg.source_sha256,
        extra={
            "segment_id": seg.id,
            "tm_unit_id": result.get("tm_unit_id"),
            "concept_id": result.get("concept_id"),
            "api_key": "should-strip",
        },
    )
    return result


@router.get("/review/diff")
def review_diff_api(
    source_sha256: str | None = None,
    segment_id: str | None = None,
    version_a: int | None = None,
    version_b: int | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import ReviewError, diff_revisions

    if not source_sha256 and not segment_id:
        raise HTTPException(status_code=400, detail="source_sha256 or segment_id required")
    try:
        return diff_revisions(
            session,
            tenant_id=tenant.id,
            source_sha256=source_sha256.lower() if source_sha256 else None,
            segment_id=segment_id,
            version_a=version_a,
            version_b=version_b,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/review/suggestions")
def review_suggestions_api(
    source_text: str = Query(min_length=1, max_length=20000),
    target_text: str | None = Query(default=None, max_length=20000),
    project_id: str | None = Query(default=None, max_length=36),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import list_forbidden_texts
    from qyunslation.persist.review_repo import suggestions

    if not (source_text or "").strip():
        raise HTTPException(status_code=400, detail="source_text required")
    forbidden = list_forbidden_texts(session, curated_only=True)
    return suggestions(
        session,
        tenant_id=tenant.id,
        source_text=source_text,
        target_text=target_text,
        project_id=project_id,
        forbidden=forbidden,
    )
