# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c/d/e/f/g：/api/v1（projects / jobs / concepts / tm / qa / review / health）。"""
from __future__ import annotations

import os
import re
import hashlib
import mimetypes
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from qyunslation.persist.models import (
    DocumentTermCandidate,
    PreflightRecord,
    QaItem,
    ReviewDecision,
    ReviewDraft,
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
    },
}
WORKBENCH_PREF_KEYS = frozenset(
    {"sourceLanguage", "targetLanguage", "profile", "bilingual", "classification"}
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
        },
    }


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
    if merged["profile"] not in {"临床研究文档", "监管申报材料", "通用医药文档"}:
        merged["profile"] = PREF_DEFAULTS["workbench"]["profile"]
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
        "document_classification": record.document_classification or metadata.get("document_classification") or "internal",
        "model_profile_id": record.model_profile_id or metadata.get("model_profile_id"),
        "reused": False,
        "expires_at": expires_at.isoformat(),
        "created_at": record.created_at.isoformat(),
    }


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
            return reused

    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary, target)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    issues: list[dict[str, str]] = []
    if suffix in {".png", ".jpg", ".jpeg"}:
        issues.append({"severity": "warning", "code": "IMAGE_DOCUMENT", "message": "图片文档将在翻译前执行 OCR。"})
    record = PreflightRecord(
        id=record_id,
        tenant_id=tenant.id,
        actor_sub=identity.user_sub,
        source_filename=filename,
        source_format=suffix.removeprefix(".").lower(),
        source_sha256=digest,
        size_bytes=size_bytes,
        status="ready",
        metadata_json={
            "mime": mime,
            "manifest_summary": {"pages": None, "objects": None, "scan_detected": suffix in {".png", ".jpg", ".jpeg"}},
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
    if _identity_role(identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        stmt = stmt.where(PreflightRecord.actor_sub == identity.user_sub)
    rows = list(session.scalars(stmt))
    items = [_preflight_dict(row) for row in rows if _preflight_dict(row)["state"] == "ready"]
    latest = items[0] if items else None
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
    if record.actor_sub != identity.user_sub and _identity_role(identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        raise HTTPException(status_code=404, detail="preflight not found")
    return _preflight_dict(record)


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
    path = _preflight_path(record)
    if path.is_file():
        path.unlink()
    session.delete(record)
    return Response(status_code=204)


class TranslationRunCreateBody(BaseModel):
    preflight_id: str = Field(min_length=1, max_length=36)
    direction: str | None = Field(default="English → 简体中文", max_length=64)
    source_language: str | None = Field(default=None, max_length=32)
    target_language: str | None = Field(default=None, max_length=32)
    profile: str = Field(default="临床研究文档", min_length=1, max_length=128)
    bilingual: bool = True
    display_name: str | None = Field(default=None, max_length=256)
    document_classification: str | None = Field(default=None, max_length=32)
    model_profile_id: str | None = Field(default=None, max_length=128)
    term_model_profile_id: str | None = Field(default=None, max_length=128)


class PreflightPatchBody(BaseModel):
    document_classification: str | None = Field(default=None, max_length=32)
    model_profile_id: str | None = Field(default=None, max_length=128)
    term_model_profile_id: str | None = Field(default=None, max_length=128)
    source_language: str | None = Field(default=None, max_length=32)
    target_language: str | None = Field(default=None, max_length=32)
    profile: str | None = Field(default=None, max_length=128)


class ReviewDecisionBody(BaseModel):
    decision: str = Field(min_length=1, max_length=32)
    comment: str | None = Field(default=None, max_length=2048)


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
    display_name: str | None = Field(default=None, max_length=256)
    archived: bool | None = None


_RUN_TERMINAL = frozenset(
    {"succeeded", "failed", "cancelled", "blocked", "degraded", "interrupted"}
)
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
    """PLAN-071e/h：用真实源/译文 PDF 产出 QA findings 与术语快照（失败也要留痕）。"""
    from qyunslation.pipeline.qa.engine import QaFinding
    from qyunslation.pipeline.qa.pdf_inspect import inspect_pdf_pair

    files = (runner_state or {}).get("downloadable_files") or {}
    mono: Path | None = None
    dual: Path | None = None
    for key, meta in files.items():
        if not isinstance(meta, dict) or not meta.get("path"):
            continue
        path = Path(str(meta["path"]))
        if not path.is_file() or path.suffix.casefold() != ".pdf":
            continue
        if "dual" in str(key).casefold() or "dual" in path.name.casefold():
            dual = dual or path
        else:
            mono = mono or path
    if mono is None and dual is None:
        return [], None, None
    preflight = session.get(PreflightRecord, run.preflight_id)
    if preflight is None:
        return [], None, None
    try:
        source_path = _preflight_path(preflight)
    except HTTPException:
        return [], None, None
    target = str(getattr(run, "direction", "") or "").split("→")[-1]
    facts: dict[str, Any] = {}
    findings, summary = inspect_pdf_pair(
        source_path=source_path,
        mono_path=mono,
        dual_path=dual,
        target_is_chinese=("中" in target or target.casefold().startswith("zh") or not target),
        facts_out=facts,
    )
    snapshot: dict[str, Any] | None = None
    if facts:
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
            findings.extend(check_terms_in_translation(snapshot, facts["translated"].text))
        except Exception:
            snapshot = None
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


def _maybe_run_auto_qa(
    session: Session,
    run: TranslationRunRecord,
    runner_state: dict[str, Any] | None = None,
) -> None:
    """PLAN-071e：layout 完成后跑确定性 QA，写入 qa_item 与 quality_state。"""
    if (run.quality_state or "draft") not in {"draft", "qa_blocked", "review_ready"}:
        return
    if run.stage not in {"layout", "qa"} and run.status not in {"translating", "rendering"}:
        # Still allow when layout_complete just set stage=layout.
        pass
    existing = session.scalar(
        select(QaItem.id).where(
            QaItem.run_id == run.id, QaItem.generation == run.generation
        ).limit(1)
    )
    if existing:
        return
    from qyunslation.pipeline.qa import (
        quality_state_from_findings,
        run_deterministic_qa,
        summarize,
    )

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
            )
        except Exception:
            pass
    findings = run_deterministic_qa(
        manifest={"objects": [{"id": "placeholder"}]} if run.manifest_version else {},
        term_summary=run.term_summary,
        settings_snapshot={**(run.settings_snapshot or {}), "generation": run.generation},
        translated_text_sample=None,
        logo_present=None,
    )
    findings.extend(inspected)
    for finding in findings:
        session.add(
            QaItem(
                run_id=run.id,
                generation=run.generation,
                category=finding.category,
                severity=finding.severity,
                code=finding.code,
                message=finding.message,
                object_id=finding.object_id,
                evidence_json=finding.evidence,
            )
        )
    run.qa_summary = summarize(findings)
    run.quality_state = quality_state_from_findings(findings)
    run.stage = "qa" if run.quality_state == "qa_blocked" else "review"
    try:
        from qyunslation.pipeline.event_store import persist_buffer
        from qyunslation.pipeline.events import StageEventBuffer

        buf = StageEventBuffer()
        blockers = int((run.qa_summary or {}).get("blocker") or 0)
        if run.quality_state == "qa_blocked":
            buf.emit("layout", "completed", message="版式完成")
            buf.emit("qa", "blocked", message=f"QA 拦截 {blockers} 项", progress=100.0)
        else:
            buf.emit("layout", "completed", message="版式完成")
            buf.emit("qa", "completed", message="确定性 QA 通过", progress=100.0)
            buf.emit("review", "running", message="等待人工审校")
        persist_buffer(session, run_id=run.id, generation=run.generation, buffer=buf)
    except Exception:
        pass


def _refresh_translation_run(session: Session, run: TranslationRunRecord) -> str | None:
    if run.status == "interrupted":
        return run.degradation_reason
    if run.status == "cancelled":
        return run.degradation_reason or "translation cancelled by user"
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
            run.status = "translating"
            run.stage = str(runner_state.get("stage") or "layout")
            run.progress = None
            _maybe_run_auto_qa(session, run, runner_state)
            if run.quality_state == "review_ready":
                run.stage = "review"
            elif run.quality_state == "qa_blocked":
                run.stage = "qa"
            run.updated_at = datetime.now(timezone.utc)
            return str(progress_message) if progress_message else None
        if status == "succeeded":
            from qyunslation.pipeline import run_pipeline_mode

            if run_pipeline_mode(run.settings_snapshot) == "v2":
                run.status = "translating"
                run.stage = "layout"
                run.progress = None
                run.updated_at = datetime.now(timezone.utc)
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
        from qyunslation.workbench.heartbeat import is_heartbeat_stale, mark_interrupted

        if run.status in {"queued", "scanning", "translating", "rendering"} and is_heartbeat_stale(
            run
        ):
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
            run.status = "translating"
            run.stage = "layout"
            run.progress = None
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


def _translation_run_dict(session: Session, run: TranslationRunRecord) -> dict[str, Any]:
    """Project the durable ledger plus current legacy-service state."""
    progress_message = _refresh_translation_run(session, run)
    preflight = session.get(PreflightRecord, run.preflight_id)
    settings = dict(run.settings_snapshot or {})
    source_language, target_language, _ = _normalize_language_pair(
        settings.get("source_language"), settings.get("target_language"), run.direction
    )
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
    return {
        "id": run.id,
        "project_id": None,
        "preflight_id": run.preflight_id,
        "generation": run.generation,
        "filename": preflight.source_filename if preflight else None,
        "format": preflight.source_format if preflight else None,
        "direction": run.direction,
        "source_language": source_language,
        "target_language": target_language,
        "profile": run.profile,
        "settings": settings,
        "display_name": run.display_name,
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
        "artifacts": [_artifact_dict(item, run.id) for item in artifacts],
        "degradation_reason": run.degradation_reason,
        "external_task_id": run.external_task_id,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _run_owned(session: Session, *, run_id: str, identity: IdentityContext) -> TranslationRunRecord:
    tenant = _tenant_bundle(session, identity)
    run = session.scalar(
        select(TranslationRunRecord).where(
            TranslationRunRecord.id == run_id,
            TranslationRunRecord.tenant_id == tenant.id,
        )
    )
    if run is None or (
        run.actor_sub != identity.user_sub
        and _identity_role(identity) not in {"reviewer", "term_admin", "admin", "owner"}
    ):
        raise HTTPException(status_code=404, detail="translation run not found")
    return run


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
                settings=run.settings_snapshot,
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
                settings=run.settings_snapshot,
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
        payload = AutoWorkflowParams(workflow_type="auto", to_lang=target_language)
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


@router.post("/translation-runs", status_code=201)
async def create_translation_run(
    body: TranslationRunCreateBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    source_language, target_language, direction = _normalize_language_pair(
        body.source_language, body.target_language, body.direction
    )
    tenant = _tenant_bundle(session, identity)
    preflight = session.get(PreflightRecord, body.preflight_id)
    if preflight is None or preflight.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="preflight not found")
    if preflight.actor_sub != identity.user_sub and _identity_role(identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        raise HTTPException(status_code=404, detail="preflight not found")
    state = _preflight_dict(preflight)
    if state["state"] != "ready":
        raise HTTPException(status_code=409, detail="preflight is not ready")
    key = (idempotency_key or f"preflight:{preflight.id}").strip()
    if not key or len(key) > 256:
        raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(TranslationRunRecord).where(
            TranslationRunRecord.tenant_id == tenant.id,
            TranslationRunRecord.idempotency_key_hash == key_hash,
        )
    )
    if existing is not None:
        return _translation_run_dict(session, existing)
    from qyunslation.pipeline.model_profiles import validate_selection

    classification = (
        body.document_classification
        or preflight.document_classification
        or "internal"
    )
    model_profile_id = body.model_profile_id or preflight.model_profile_id
    try:
        classification, model_profile_id, term_profile_id = validate_selection(
            classification=classification,
            model_profile_id=model_profile_id,
            term_profile_id=body.term_model_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
            "bilingual": body.bilingual,
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
    await _launch_translation_run(
        run=run, preflight=preflight, target_language=target_language, session=session
    )
    return _translation_run_dict(session, run)


@router.get("/translation-runs")
def list_translation_runs(
    status: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    page_size: int = Query(default=100, ge=1, le=100),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    stmt = select(TranslationRunRecord).where(TranslationRunRecord.tenant_id == tenant.id)
    if _identity_role(identity) not in {"reviewer", "term_admin", "admin", "owner"}:
        stmt = stmt.where(TranslationRunRecord.actor_sub == identity.user_sub)
    if not include_archived:
        stmt = stmt.where(TranslationRunRecord.archived_at.is_(None))
    if status:
        stmt = stmt.where(TranslationRunRecord.status == status)
    stmt = stmt.order_by(TranslationRunRecord.created_at.desc()).limit(page_size)
    rows = list(session.scalars(stmt))
    return {"items": [_translation_run_dict(session, row) for row in rows]}


@router.get("/translation-runs/{run_id}")
def get_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    return _translation_run_dict(session, _run_owned(session, run_id=run_id, identity=identity))


@router.patch("/translation-runs/{run_id}")
def patch_translation_run(
    run_id: str,
    body: TranslationRunPatchBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    changes: dict[str, Any] = {}
    if body.display_name is not None:
        clean_name = body.display_name.strip()
        run.display_name = clean_name or None
        changes["display_name"] = bool(clean_name)
    if body.archived is not None:
        if body.archived and run.status not in _RUN_TERMINAL:
            raise HTTPException(status_code=409, detail="only terminal translation runs can be archived")
        if body.archived:
            run.archived_at = datetime.now(timezone.utc)
            run.archived_by = identity.user_sub
        else:
            run.archived_at = None
            run.archived_by = None
        changes["archived"] = body.archived
    if changes:
        record_audit(
            session,
            actor_sub=identity.user_sub,
            action="translation_run.update",
            extra={"run_id": run.id, "changes": changes},
        )
    return _translation_run_dict(session, run)


@router.post("/translation-runs/{run_id}/restore")
def restore_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    run.archived_at = None
    run.archived_by = None
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="translation_run.restore",
        extra={"run_id": run.id},
    )
    return _translation_run_dict(session, run)


@router.delete("/translation-runs/{run_id}", status_code=204)
def delete_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> Response:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    if run.status not in _RUN_TERMINAL:
        raise HTTPException(status_code=409, detail="only terminal translation runs can be deleted")

    artifacts = list(
        session.scalars(
            select(TranslationArtifact).where(
                TranslationArtifact.run_id == run.id,
                TranslationArtifact.tenant_id == run.tenant_id,
            )
        )
    )
    for artifact in artifacts:
        path = _artifact_path(artifact)
        if path.is_file():
            path.unlink()
        session.delete(artifact)

    preflight = session.get(PreflightRecord, run.preflight_id)
    sibling = session.scalar(
        select(TranslationRunRecord.id)
        .where(
            TranslationRunRecord.preflight_id == run.preflight_id,
            TranslationRunRecord.id != run.id,
        )
        .limit(1)
    )
    if preflight is not None and sibling is None:
        path = _preflight_path(preflight)
        if path.is_file():
            path.unlink()
        session.delete(preflight)
    session.delete(run)
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="translation_run.delete",
        extra={"run_id": run_id},
    )
    return Response(status_code=204)


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
    if record.actor_sub != identity.user_sub and _identity_role(identity) not in {
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


@router.get("/translation-runs/{run_id}/qa-items")
def list_qa_items(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    rows = list(
        session.scalars(
            select(QaItem)
            .where(QaItem.run_id == run.id, QaItem.generation == run.generation)
            .order_by(QaItem.created_at)
        )
    )
    return {
        "items": [
            {
                "id": row.id,
                "category": row.category,
                "severity": row.severity,
                "code": row.code,
                "message": row.message,
                "object_id": row.object_id,
                "evidence": row.evidence_json,
                "resolved": row.resolved,
            }
            for row in rows
        ],
        "summary": run.qa_summary or {},
        "quality_state": run.quality_state,
    }


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
    role = _identity_role(identity)
    if role not in {"reviewer", "term_admin", "admin", "owner"}:
        raise HTTPException(status_code=403, detail="reviewer role required")
    decision = (body.decision or "").strip().casefold()
    if decision not in {"approve", "request_changes", "reject"}:
        raise HTTPException(status_code=400, detail="invalid decision")
    blockers = int((run.qa_summary or {}).get("blocker") or 0)
    if decision == "approve" and (run.quality_state == "qa_blocked" or blockers > 0):
        raise HTTPException(status_code=409, detail="cannot approve while QA blockers remain")
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
        run.quality_state = "draft"
        run.stage = "text"
        run.status = "translating"
    else:
        run.quality_state = "draft"
        run.status = "failed"
        run.stage = "review"
        run.degradation_reason = "rejected by reviewer"
        run.completed_at = datetime.now(timezone.utc)
    run.updated_at = datetime.now(timezone.utc)
    return _translation_run_dict(session, run)


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
        artifact = session.scalar(
            select(TranslationArtifact)
            .where(
                TranslationArtifact.run_id == run.id,
                TranslationArtifact.tenant_id == run.tenant_id,
                TranslationArtifact.kind.in_(allowed_kinds),
            )
            .order_by(TranslationArtifact.created_at.desc())
        )
        if artifact is None:
            # Fall back to runner outputs for v2 layout_complete without formal gate.
            try:
                from qyunslation.workbench.runner import get_pdf2zh_task_state

                state = get_pdf2zh_task_state(run.external_task_id or "")
            except Exception:
                state = None
            files = (state or {}).get("downloadable_files") or {}
            first = next(iter(files.values()), None)
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
    _refresh_translation_run(session, run)
    if run.status in _RUN_TERMINAL:
        return _translation_run_dict(session, run)
    if run.external_task_id:
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
    run.degradation_reason = "translation cancelled by user"
    run.completed_at = run.completed_at or datetime.now(timezone.utc)
    run.updated_at = datetime.now(timezone.utc)
    return _translation_run_dict(session, run)


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
    if preflight is None or _preflight_dict(preflight)["state"] != "ready":
        raise HTTPException(status_code=409, detail="preflight is not ready")
    next_generation = run.generation + 1
    existing = session.scalar(
        select(TranslationRunRecord).where(
            TranslationRunRecord.preflight_id == run.preflight_id,
            TranslationRunRecord.generation == next_generation,
        )
    )
    if existing is not None:
        return _translation_run_dict(session, existing)
    key = hashlib.sha256(f"retry:{run.id}:{next_generation}".encode("utf-8")).hexdigest()
    snap = dict(run.settings_snapshot or {})
    requested_pipeline = ((body.pipeline if body else None) or "").strip().casefold()
    if requested_pipeline == "v2":
        snap["pipeline"] = "v2"
        snap["pipeline_requested"] = "v2"
        snap["retry_of"] = {"run_id": run.id, "generation": run.generation}
    retry = TranslationRunRecord(
        preflight_id=run.preflight_id,
        tenant_id=run.tenant_id,
        actor_sub=identity.user_sub,
        idempotency_key_hash=hashlib.sha256(key.encode("utf-8")).hexdigest(),
        generation=next_generation,
        direction=run.direction,
        profile=run.profile,
        display_name=run.display_name,
        settings_snapshot=snap,
        status="queued",
        stage="validation",
        quality_state="draft",
        document_classification=run.document_classification,
        model_profile_id=run.model_profile_id,
        term_summary={"status": "snapshot_pending"},
        qa_summary={"blocker": 0, "warning": 0, "info": 0},
    )
    session.add(retry)
    session.flush()
    await _launch_translation_run(
        run=retry,
        preflight=preflight,
        target_language=_run_target_language(retry.direction),
        session=session,
    )
    return _translation_run_dict(session, retry)


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
    if preflight is None or _preflight_dict(preflight)["state"] != "ready":
        raise HTTPException(status_code=409, detail="preflight is not ready")
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
    return _translation_run_dict(session, run)


def _requalify_translation_run(
    session: Session,
    run: TranslationRunRecord,
    *,
    runner_state: dict[str, Any] | None = None,
) -> None:
    """PLAN-073b：用修复后的术语规则重跑确定性 QA，不重新翻译。"""
    from qyunslation.pipeline.qa import quality_state_from_findings, run_deterministic_qa, summarize

    session.query(QaItem).filter(
        QaItem.run_id == run.id,
        QaItem.generation == run.generation,
    ).delete(synchronize_session=False)
    if runner_state is None and run.external_task_id:
        try:
            from qyunslation.workbench.runner import get_pdf2zh_task_state

            runner_state = get_pdf2zh_task_state(run.external_task_id)
        except Exception:
            runner_state = None
    inspected, term_snapshot, _facts = _inspect_run_outputs(session, run, runner_state)
    if term_snapshot is not None:
        run.term_summary = term_snapshot
    findings = run_deterministic_qa(
        manifest={"objects": [{"id": "placeholder"}]} if run.manifest_version else {},
        term_summary=run.term_summary,
        settings_snapshot={**(run.settings_snapshot or {}), "generation": run.generation},
        translated_text_sample=None,
        logo_present=None,
    )
    findings.extend(inspected)
    for finding in findings:
        session.add(
            QaItem(
                run_id=run.id,
                generation=run.generation,
                category=finding.category,
                severity=finding.severity,
                code=finding.code,
                message=finding.message,
                object_id=finding.object_id,
                evidence_json=finding.evidence,
            )
        )
    run.qa_summary = summarize(findings)
    run.quality_state = quality_state_from_findings(findings)
    run.stage = "qa" if run.quality_state == "qa_blocked" else "review"
    run.updated_at = datetime.now(timezone.utc)


@router.post("/translation-runs/{run_id}/requalify")
async def requalify_translation_run(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    _refresh_translation_run(session, run)
    if run.status not in {"translating", "rendering", "review_ready"} and run.quality_state != "qa_blocked":
        raise HTTPException(status_code=409, detail="run is not ready for requalify")
    _requalify_translation_run(session, run)
    session.flush()
    return _translation_run_dict(session, run)


@router.get("/translation-runs/{run_id}/term-candidates")
def list_run_term_candidates(
    run_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _run_owned(session, run_id=run_id, identity=identity)
    rows = session.scalars(
        select(DocumentTermCandidate)
        .where(DocumentTermCandidate.translation_run_id == run.id)
        .order_by(DocumentTermCandidate.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "source_term": row.source_term,
                "suggested_target": row.suggested_target,
                "term_type": row.term_type,
                "risk": row.risk,
                "status": row.status,
                "source_context": row.source_context,
            }
            for row in rows
        ]
    }


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
