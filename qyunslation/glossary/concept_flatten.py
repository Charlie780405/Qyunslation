# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d：Concept → 扁平 {source: target} 视图。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from qyunslation.glossary.governance import (
    GlossaryEntry,
    LAYER_PRIORITY,
    merge_by_priority,
)
from qyunslation.persist.concept_repo import curated_concepts, layer_sort_key
from qyunslation.persist.models import Concept


def concept_to_entries(concept: Concept) -> list[GlossaryEntry]:
    """把一个 Concept 的 preferred 词对展开为单条 GlossaryEntry（不自动反向）。"""
    preferred = [t for t in concept.terms if t.role == "preferred"]
    by_lang: dict[str, str] = {}
    for t in preferred:
        lang = (t.lang or "").casefold()
        if lang and t.text.strip():
            by_lang[lang] = t.text.strip()
    if concept.do_not_translate:
        text = next(iter(by_lang.values()), "")
        if not text:
            return []
        lang = next(iter(by_lang.keys()), "en")
        return [
            GlossaryEntry(
                source=text,
                target=text,
                src_lng=lang,
                tgt_lng=lang,
                layer=concept.layer,
                domain=concept.domain,
                status="curated",
                notes=concept.evidence or "",
            )
        ]
    # 优先 en→zh；否则取任意两语对（保持导入时 src/tgt 语义：第一语源、第二语目标）
    en = by_lang.get("en")
    zh = by_lang.get("zh")
    if en and zh:
        # import 时 source=en 或 source=zh 都写入了两侧 preferred；用 import 指纹无法恢复方向。
        # 约定：若 evidence/notes 不含方向，则默认 en→zh；zh→en 行在 CSV 中是独立 concept。
        # 为区分：看 terms 写入顺序不可靠。改用「仅输出一对」：若两语齐全，输出 en→zh。
        # CSV 中 zh→en 行导入后同样有 en+zh preferred → 也会变成 en→zh，丢失 zh→en。
        # 因此导入时必须在 Concept 上保留方向：用 evidence 存 "dir=src>tgt" 或加字段。
        # 最小修复：import_key 已含 src_lng|tgt_lng，flatten 时解析 import_key。
        src_lng, tgt_lng = "en", "zh"
        if concept.import_key:
            parts = concept.import_key.split("|")
            if len(parts) >= 4:
                src_lng, tgt_lng = parts[2], parts[3]
        source = by_lang.get(src_lng) or en
        target = by_lang.get(tgt_lng) or zh
        return [
            GlossaryEntry(
                source=source,
                target=target,
                src_lng=src_lng,
                tgt_lng=tgt_lng,
                layer=concept.layer,
                domain=concept.domain,
                status="curated",
                notes=concept.evidence or "",
            )
        ]
    langs = list(by_lang.items())
    if len(langs) >= 2:
        (l0, t0), (l1, t1) = langs[0], langs[1]
        return [
            GlossaryEntry(
                source=t0,
                target=t1,
                src_lng=l0,
                tgt_lng=l1,
                layer=concept.layer,
                domain=concept.domain,
                status="curated",
                notes=concept.evidence or "",
            )
        ]
    return []


def flatten_curated_entries(session: Session) -> list[GlossaryEntry]:
    concepts = curated_concepts(session)
    concepts_sorted = sorted(concepts, key=lambda c: -layer_sort_key(c.layer))
    entries: list[GlossaryEntry] = []
    for c in concepts_sorted:
        entries.extend(concept_to_entries(c))
    return entries


def flatten_curated_dict(session: Session) -> dict[str, str]:
    return merge_by_priority(flatten_curated_entries(session))


def try_db_curated_entries() -> list[GlossaryEntry] | None:
    """若引擎可用且有 curated 则返回 entries；空库或不可用返回 None。"""
    try:
        from qyunslation.persist.db import SessionLocal, get_engine

        if get_engine() is None or SessionLocal is None:
            return None
        session = SessionLocal()
        try:
            entries = flatten_curated_entries(session)
            return entries if entries else None
        finally:
            session.close()
    except Exception:
        return None


def try_db_curated_dict() -> dict[str, str] | None:
    entries = try_db_curated_entries()
    if entries is None:
        return None
    return merge_by_priority(entries)


def export_tbx_stub(concepts: Iterable[Concept]) -> str:
    """极简 TBX 导出（curated）；非完整 TBX 2.0。"""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<martif type="TBX" xml:lang="en">',
        "<text><body>",
    ]
    for c in concepts:
        if c.status != "curated":
            continue
        lines.append(f'<termEntry id="{c.id}">')
        for t in c.terms:
            if t.role != "preferred":
                continue
            lines.append(
                f'<langSet xml:lang="{t.lang}"><tig><term>{_xml_escape(t.text)}</term></tig></langSet>'
            )
        lines.append("</termEntry>")
    lines.append("</body></text></martif>")
    return "\n".join(lines)


def _xml_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_tbx(path: Path | str, session: Session) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(export_tbx_stub(curated_concepts(session)), encoding="utf-8")
    return dest
