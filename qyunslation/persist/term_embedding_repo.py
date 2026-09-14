# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：ConceptTerm embedding 回填与语义候选检索。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from sqlalchemy import bindparam, select
from sqlalchemy.orm import Session, selectinload

from qyunslation.glossary.governance import normalize_lang
from qyunslation.persist.models import Concept, ConceptTerm, ConceptTermEmbedding, PgVector

logger = logging.getLogger(__name__)
EMBEDDING_MODEL = "bge-m3"
DEFAULT_DIM = 1024
EMBED_BATCH = 32


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _text_hash(term: ConceptTerm) -> str:
    return sha256(f"{term.lang}\0{term.text}".encode("utf-8")).hexdigest()


def _visible_concept_filter(stmt, *, tenant_id: str, project_id: str | None):
    return (
        stmt.where(Concept.status == "curated")
        .where((Concept.tenant_id.is_(None)) | (Concept.tenant_id == tenant_id))
        .where((Concept.project_id.is_(None)) | (Concept.project_id == project_id))
    )


def _embed(texts: list[str]) -> tuple[list[list[float]], str]:
    from qyunslation.embed import client as embed_client

    vectors = embed_client.embed_texts(texts)
    model = embed_client._model()
    return vectors, model


def backfill_concept_term_embeddings(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None = None,
    dim: int = DEFAULT_DIM,
    model: str | None = None,
    batch_size: int = EMBED_BATCH,
    embedder: Callable[[list[str]], tuple[list[list[float]], str]] | None = None,
) -> dict[str, Any]:
    """Create or refresh vectors for visible curated terms.

    Embedding is a sidecar: a provider outage reports ``errors`` and leaves
    deterministic term lookup fully usable.  Existing rows are never replaced
    with an invalid or partial response.
    """
    stmt = _visible_concept_filter(
        select(ConceptTerm)
        .join(Concept, ConceptTerm.concept_id == Concept.id)
        .options(selectinload(ConceptTerm.concept).selectinload(Concept.terms)),
        tenant_id=tenant_id,
        project_id=project_id,
    )
    terms = list(session.scalars(stmt).unique().all())
    if not terms:
        return {"considered": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}

    existing = {
        row.term_id: row
        for row in session.scalars(
            select(ConceptTermEmbedding).where(
                ConceptTermEmbedding.term_id.in_([term.id for term in terms])
            )
        )
    }
    desired_model = model or EMBEDDING_MODEL
    pending = []
    skipped = 0
    for term in terms:
        row = existing.get(term.id)
        if (
            row is not None
            and row.text_hash == _text_hash(term)
            and row.model == desired_model
            and row.dim == dim
        ):
            skipped += 1
        else:
            pending.append(term)

    create_count = 0
    update_count = 0
    failed_count = 0
    errors: list[str] = []
    embed_fn = embedder or _embed
    actual_batch_size = max(1, min(batch_size, EMBED_BATCH))
    for start in range(0, len(pending), actual_batch_size):
        batch = pending[start : start + actual_batch_size]
        try:
            vectors, returned_model = embed_fn([term.text for term in batch])
            if len(vectors) != len(batch):
                raise ValueError("embedding response length mismatch")
            effective_model = model or returned_model or desired_model
            if effective_model != desired_model and model:
                raise ValueError(f"embedding model {effective_model!r} != requested {model!r}")
            for term, vector in zip(batch, vectors):
                if len(vector) != dim:
                    raise ValueError(
                        f"embedding dimension {len(vector)} != requested {dim}"
                    )
                row = existing.get(term.id)
                if row is None:
                    row = ConceptTermEmbedding(
                        term_id=term.id,
                        dim=dim,
                        model=effective_model,
                        text_hash=_text_hash(term),
                        vector=[float(value) for value in vector],
                        created_at=_utcnow(),
                    )
                    session.add(row)
                    existing[term.id] = row
                    create_count += 1
                else:
                    row.dim = dim
                    row.model = effective_model
                    row.text_hash = _text_hash(term)
                    row.vector = [float(value) for value in vector]
                    row.created_at = _utcnow()
                    update_count += 1
            session.flush()
        except Exception as exc:  # noqa: BLE001 - sidecar must not block exact path
            message = f"batch {start}:{start + len(batch)}: {type(exc).__name__}: {exc}"
            errors.append(message)
            failed_count += len(batch)
            logger.warning("concept term embedding failed: %s", message)

    return {
        "considered": len(terms),
        "created": create_count,
        "updated": update_count,
        "skipped": skipped,
        "failed": failed_count,
        "errors": errors,
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = sum(float(a) * float(a) for a in left) ** 0.5
    right_norm = sum(float(b) * float(b) for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _preferred_target(concept: Concept, *, src_lang: str, tgt_lang: str) -> str | None:
    targets = [
        term.text.strip()
        for term in concept.terms
        if normalize_lang(term.lang) == normalize_lang(tgt_lang)
        and term.role == "preferred"
    ]
    if targets:
        return targets[0]
    if concept.do_not_translate:
        sources = [
            term.text.strip()
            for term in concept.terms
            if normalize_lang(term.lang) == normalize_lang(src_lang)
            and term.role == "preferred"
        ]
        return sources[0] if sources else None
    return None


def semantic_search_concept_terms(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None,
    query: str,
    src_lang: str = "en",
    tgt_lang: str = "zh",
    limit: int = 5,
    threshold: float = 0.0,
    dim: int = DEFAULT_DIM,
    embedder: Callable[[list[str]], tuple[list[list[float]], str]] | None = None,
) -> list[dict[str, Any]]:
    """Return semantic suggestions; never promote a suggestion to a hard hit."""
    if not (query or "").strip():
        return []
    src_lang = normalize_lang(src_lang) or "en"
    tgt_lang = normalize_lang(tgt_lang) or "zh"
    try:
        vectors, model = (embedder or _embed)([query.strip()])
        query_vector = vectors[0]
        if len(query_vector) != dim:
            raise ValueError(f"query embedding dimension {len(query_vector)} != {dim}")
    except Exception as exc:  # noqa: BLE001 - deterministic fallback is required
        logger.warning("concept term semantic search degraded: %s", exc)
        return []

    stmt = _visible_concept_filter(
        select(ConceptTermEmbedding, ConceptTerm)
        .join(ConceptTerm, ConceptTermEmbedding.term_id == ConceptTerm.id)
        .join(Concept, ConceptTerm.concept_id == Concept.id)
        .where(ConceptTerm.lang == src_lang)
        .where(ConceptTermEmbedding.dim == dim)
        .where(ConceptTermEmbedding.model == model)
        .options(selectinload(ConceptTerm.concept).selectinload(Concept.terms)),
        tenant_id=tenant_id,
        project_id=project_id,
    )
    is_postgres_vector = (
        session.bind is not None
        and session.bind.dialect.name == "postgresql"
        and PgVector is not None
    )
    if is_postgres_vector:
        # Let PostgreSQL use the HNSW cosine index created by 058a0001.  The
        # SQLite/test path below intentionally keeps a small Python fallback.
        query_param = bindparam("term_query_vector", type_=PgVector(dim))
        distance = ConceptTermEmbedding.vector.op("<=>")(query_param)
        rows = session.execute(
            stmt.add_columns(distance.label("distance"))
            .order_by(distance)
            .limit(max(1, min(int(limit), 100)) * 4),
            {"term_query_vector": query_vector},
        ).all()
    else:
        rows = session.execute(stmt).all()
    hits = []
    for row in rows:
        embedding, source_term = row[:2]
        if is_postgres_vector:
            # cosine distance is in [0, 2] for normalized vectors; clamp the
            # derived score so the API never exposes an impossible confidence.
            score = max(0.0, min(1.0, 1.0 - float(row[2])))
        else:
            score = _cosine_similarity(query_vector, list(embedding.vector or []))
        if score < threshold:
            continue
        concept = source_term.concept
        target = _preferred_target(concept, src_lang=src_lang, tgt_lang=tgt_lang)
        if not target:
            continue
        hits.append(
            {
                "concept_id": concept.id,
                "source_term": source_term.text,
                "target_term": target,
                "project_id": concept.project_id,
                "scope": concept.layer,
                "term_type": concept.term_type,
                "score": score,
                "match_type": "semantic",
                "hard_constraint": False,
            }
        )
    hits.sort(key=lambda item: (item["score"], item["scope"]), reverse=True)
    return hits[: max(1, min(int(limit), 100))]
