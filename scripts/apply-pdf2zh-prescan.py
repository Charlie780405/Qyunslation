#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-027b：上传两段预扫描 + 代际防线。

须在 dual-preview / layout-polish 之后执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

MARKER = "_qy_prescan"
CSS_MARKER = "/* _qy_prescan_css */"

HELPER = r'''
        # _qy_prescan
        def _qy_prescan_bump(st: dict) -> int:
            st = st if isinstance(st, dict) else {}
            gen = int(st.get("_prescan_generation") or 0) + 1
            st["_prescan_generation"] = gen
            return gen


        def _qy_prescan_tier1(files, state, lang_to=None):
            """同步 Tier-1：结构扫描，<300ms 目标。"""
            import sys as _sys
            from pathlib import Path as _P

            _sys.path.insert(0, "/home/dev/qyunslation/scripts")
            from doc_image_prescan import scan_file_tier1

            st = dict(state or {})
            gen = _qy_prescan_bump(st)
            st.setdefault("_prescan_meta", {"files": {}})
            if not files:
                st["_prescan_meta"] = {"files": {}, "current_generation": gen}
                return gr.update(value="", visible=False), st
            f0 = files[0]
            path = _P(f0.name if hasattr(f0, "name") else f0)
            if not path.is_file():
                return gr.update(value="无法读取上传文件", visible=True), st
            try:
                t1 = scan_file_tier1(path)
            except Exception as exc:
                logger.warning("prescan tier1 failed: %s", exc)
                st["_prescan_meta"]["current_generation"] = gen
                return gr.update(value=f"预扫描失败：{exc}", visible=True), st
            entry = t1.to_dict()
            entry["generation"] = gen
            entry["tier1_done"] = True
            entry["tier2_done"] = False
            entry["translatable_count"] = 0
            st["_prescan_meta"]["current_generation"] = gen
            st["_prescan_meta"]["files"][t1.file_hash] = entry
            st["_prescan_active_hash"] = t1.file_hash
            return gr.update(value=t1.summary_text, visible=True), st


        def _qy_prescan_tier2(files, state, lang_to=None):
            """异步 Tier-2：对候选图调 sidecar /image-probe；带代际守卫。"""
            import sys as _sys
            from pathlib import Path as _P

            _sys.path.insert(0, "/home/dev/qyunslation/scripts")
            from doc_image_prescan import format_tier2_summary, scan_file_tier1

            st = dict(state or {})
            gen = int(st.get("_prescan_generation") or 0)
            meta = st.get("_prescan_meta") or {}
            fh = st.get("_prescan_active_hash")
            entry = (meta.get("files") or {}).get(fh) if fh else None
            if not entry or int(entry.get("generation") or -1) != gen:
                return gr.update(), st
            if entry.get("file_type") in ("encrypted", "corrupt", "unsupported"):
                return gr.update(), st
            cands = entry.get("candidates") or []
            if not cands:
                text = (entry.get("summary_text") or "").replace("，正在检测文本…", "。")
                entry["tier2_done"] = True
                entry["summary_text"] = text
                return gr.update(value=text, visible=True), st

            # 探针优先走 sidecar：pdf2zh 与 qyunslation 是两个独立 venv，只有后者
            # 装了 rapidocr。本地 probe_image 在缺失时会静默回退到弱检测器，把
            # 满是中文的流程图误报成「无可译文字」，所以无 OCR 能力就交给 sidecar。
            translatable = 0
            errors = 0
            try:
                _sys.path.insert(0, "/home/dev/qyunslation")
                import os as _os
                import tempfile, zipfile
                from importlib.util import find_spec as _find_spec

                _local_ocr = _find_spec("rapidocr") is not None
                _sidecar = _os.environ.get(
                    "QYUNSLATION_OFFICE_URL", "http://127.0.0.1:8010"
                )

                def probe_image(img_path, **kw):
                    if _local_ocr:
                        from qyunslation.extensions.image_translate import (
                            probe_image as _local_probe,
                        )

                        return _local_probe(img_path, **kw)
                    import requests as _rq

                    _pf = kw.get("page_frac")
                    form = {
                        "to_lang": str(kw.get("to_lang") or "简体中文"),
                        "display_width_pt": float(kw.get("display_width_pt") or 0),
                        "display_height_pt": float(kw.get("display_height_pt") or 0),
                        "page_frac": -1.0 if _pf is None else float(_pf),
                        "is_header": bool(kw.get("is_header") or False),
                    }
                    blob = _P(img_path).read_bytes()
                    resp = _rq.post(
                        f"{_sidecar}/service/image-probe",
                        files={"file": (_P(img_path).name, blob, "image/png")},
                        data=form,
                        timeout=120,
                    )
                    resp.raise_for_status()
                    return resp.json()

                f0 = files[0] if files else None
                path = _P(f0.name if hasattr(f0, "name") else f0) if f0 else None
                if path and path.suffix.lower() == ".docx":
                    with zipfile.ZipFile(path) as z:
                        for c in cands[:10]:
                            if int(st.get("_prescan_generation") or 0) != gen:
                                return gr.update(), st
                            part = c.get("part_name")
                            if not part:
                                continue
                            try:
                                data = z.read(part)
                                suf = _P(part).suffix.lower() or ".png"
                                with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
                                    tmp.write(data)
                                    tmp_path = tmp.name
                                try:
                                    pr = probe_image(
                                        tmp_path,
                                        to_lang=str(lang_to or "简体中文"),
                                        display_width_pt=float(c.get("display_width_pt") or 0),
                                        display_height_pt=float(c.get("display_height_pt") or 0),
                                    )
                                finally:
                                    _P(tmp_path).unlink(missing_ok=True)
                                if pr.get("status") == "error":
                                    errors += 1
                                elif pr.get("should_translate"):
                                    translatable += 1
                            except Exception:
                                errors += 1
                elif path and path.suffix.lower() == ".pdf":
                    import pymupdf

                    doc = pymupdf.open(path)
                    try:
                        for c in cands[:10]:
                            if int(st.get("_prescan_generation") or 0) != gen:
                                return gr.update(), st
                            xref = c.get("xref")
                            if not xref:
                                continue
                            try:
                                pix = pymupdf.Pixmap(doc, int(xref))
                                if pix.n - pix.alpha > 3:
                                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                                    tmp.write(pix.tobytes("png"))
                                    tmp_path = tmp.name
                                try:
                                    pr = probe_image(
                                        tmp_path,
                                        to_lang=str(lang_to or "简体中文"),
                                        display_width_pt=float(c.get("display_width_pt") or 0),
                                        display_height_pt=float(c.get("display_height_pt") or 0),
                                        page_frac=c.get("page_frac"),
                                    )
                                finally:
                                    _P(tmp_path).unlink(missing_ok=True)
                                if pr.get("status") == "error":
                                    errors += 1
                                elif pr.get("should_translate"):
                                    translatable += 1
                            except Exception:
                                errors += 1
                    finally:
                        doc.close()
                elif path and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                    pr = probe_image(path, to_lang=str(lang_to or "简体中文"))
                    if pr.get("status") == "error":
                        errors += 1
                    elif pr.get("should_translate"):
                        translatable = 1
            except Exception as exc:
                logger.warning("prescan tier2 failed: %s", exc)
                if int(st.get("_prescan_generation") or 0) != gen:
                    return gr.update(), st
                return gr.update(value="插图文本检测失败，翻译时将重试", visible=True), st

            if int(st.get("_prescan_generation") or 0) != gen:
                return gr.update(), st

            text = format_tier2_summary(entry, translatable=translatable, errors=errors)
            entry["tier2_done"] = True
            entry["translatable_count"] = translatable
            entry["summary_text"] = text
            meta.setdefault("files", {})[fh] = entry
            st["_prescan_meta"] = meta
            return gr.update(value=text, visible=True), st


        def _qy_prescan_tier3(files, state):
            """PLAN-028b：Tier-3 矢量插图 + 表格结构扫描（线程池执行，带代际守卫）。"""
            import sys as _sys
            from pathlib import Path as _P

            _sys.path.insert(0, "/home/dev/qyunslation/scripts")
            from doc_image_prescan import format_tier3_summary, scan_pdf_tier3

            st = dict(state or {})
            gen = int(st.get("_prescan_generation") or 0)
            meta = st.get("_prescan_meta") or {}
            fh = st.get("_prescan_active_hash")
            entry = (meta.get("files") or {}).get(fh) if fh else None
            if not entry or int(entry.get("generation") or -1) != gen:
                return gr.update(), st
            if entry.get("file_type") not in ("pdf",):
                return gr.update(), st
            if entry.get("tier3_done"):
                return gr.update(value=entry.get("summary_text"), visible=True), st

            f0 = files[0] if files else None
            path = _P(f0.name if hasattr(f0, "name") else f0) if f0 else None
            if not path or not path.is_file():
                return gr.update(), st

            def _abort() -> bool:
                return int(st.get("_prescan_generation") or 0) != gen

            if _abort():
                return gr.update(), st

            try:
                t3 = scan_pdf_tier3(path, should_abort=_abort)
            except Exception as exc:
                logger.warning("prescan tier3 failed: %s", exc)
                return gr.update(), st

            if _abort():
                return gr.update(), st

            text = format_tier3_summary(
                entry,
                vector_count=t3.vector_count,
                table_count=t3.table_count,
                truncated=t3.truncated,
                pages_scanned=t3.pages_scanned,
                figure_caption_count=getattr(t3, "figure_caption_count", None),
                table_caption_count=getattr(t3, "table_caption_count", None),
                translatable_count=getattr(t3, "translatable_count", None),
                unnumbered_count=getattr(t3, "unnumbered_count", None),
            )
            entry["tier3_done"] = True
            entry["vector_count"] = t3.vector_count
            entry["table_count"] = t3.table_count
            entry["figure_caption_count"] = getattr(t3, "figure_caption_count", 0)
            entry["table_caption_count"] = getattr(t3, "table_caption_count", 0)
            entry["translatable_count"] = getattr(t3, "translatable_count", 0)
            entry["unnumbered_count"] = getattr(t3, "unnumbered_count", 0)
            entry["tier3_truncated"] = t3.truncated
            entry["summary_text"] = text
            meta.setdefault("files", {})[fh] = entry
            st["_prescan_meta"] = meta
            return gr.update(value=text, visible=True), st


        def _qy_prescan_clear(state):
            st = dict(state or {})
            _qy_prescan_bump(st)
            st["_prescan_meta"] = {"files": {}}
            st.pop("_prescan_active_hash", None)
            return gr.update(value="", visible=False), st
'''

CSS = """
/* _qy_prescan_css */
.qy-prescan-bar {
  background: rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 6px;
  padding: 8px 12px !important;
  margin: 4px 0 8px 0 !important;
  font-size: 13px;
  line-height: 1.45;
  color: #444;
}
"""


def apply(text: str) -> str:
    # UI component
    if "qy_prescan_status" not in text:
        anchor = '''                            uploaded_files_view = gr.Markdown(
                                label=_("Uploaded files (this session)"),
                                value="",
                                visible=False,
                                elem_classes=["uploaded-files-list"],
                            )
'''
        if anchor not in text:
            raise RuntimeError("找不到 uploaded_files_view 锚点")
        insert = anchor + '''
                            # _qy_prescan
                            qy_prescan_status = gr.Markdown(
                                value="",
                                visible=False,
                                elem_classes=["qy-prescan-bar"],
                            )
'''
        text = text.replace(anchor, insert, 1)

    # Helpers — 先摘掉旧块再重插，脚本才能作为 SSOT 持续演进。
    # 空白一律规范化，否则每次重插都会多留空行，破坏幂等。
    state_anchor = "        state = gr.State("
    pos = text.find(state_anchor)
    if pos < 0:
        raise RuntimeError("找不到 state = gr.State 锚点")
    helper_start = "        # _qy_prescan\n        def _qy_prescan_bump("
    start = text.find(helper_start)
    if 0 <= start < pos:
        text = text[:start] + text[pos:]
        pos = text.find(state_anchor)
    text = text[:pos].rstrip("\n") + "\n\n" + HELPER.strip("\n") + "\n\n" + text[pos:]

    # CSS
    if CSS_MARKER not in text and "/* _qy_dual_preview_css */" in text:
        text = text.replace(
            "/* _qy_dual_preview_css */",
            "/* _qy_dual_preview_css */\n" + CSS,
            1,
        )

    # Wire upload chain
    if "_qy_prescan_tier1," not in text:
        old_then = '''        _qy_upload_evt.then(
            _qy_dual_payload,
            inputs=[result_file_selector, state],
            outputs=[preview_src, preview_src_html, preview, preview_html],
        )
'''
        new_then = '''        _qy_upload_evt.then(
            _qy_dual_payload,
            inputs=[result_file_selector, state],
            outputs=[preview_src, preview_src_html, preview, preview_html],
        )
        # _qy_prescan
        _qy_upload_evt.then(
            _qy_prescan_tier1,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state],
        ).then(
            _qy_prescan_tier2,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state],
        ).then(
            _qy_prescan_tier3,
            inputs=[file_input, state],
            outputs=[qy_prescan_status, state],
        )
'''
        if old_then not in text:
            raise RuntimeError("找不到 _qy_upload_evt.then dual_payload 锚点")
        text = text.replace(old_then, new_then, 1)
    elif "_qy_prescan_tier3," not in text and "_qy_prescan_tier2," in text:
        old_t2_end = """        ).then(
            _qy_prescan_tier2,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state],
        )
"""
        new_t2_t3 = """        ).then(
            _qy_prescan_tier2,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state],
        ).then(
            _qy_prescan_tier3,
            inputs=[file_input, state],
            outputs=[qy_prescan_status, state],
        )
"""
        if old_t2_end in text:
            text = text.replace(old_t2_end, new_t2_t3, 1)

    # Clear binding
    clear_marker = "# _qy_prescan_clear_bind"
    if clear_marker not in text:
        needle = "file_input.clear("
        idx = text.find(needle)
        if idx < 0:
            print("WARN: no file_input.clear to bind prescan clear", file=sys.stderr)
        else:
            insert_at = text.find("\n\n", idx)
            if insert_at > 0:
                bind = f'''
        {clear_marker}
        file_input.clear(
            _qy_prescan_clear,
            inputs=[state],
            outputs=[qy_prescan_status, state],
        )
'''
                text = text[:insert_at] + bind + text[insert_at:]

    return text


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            errs += 1

    need(MARKER in text, "marker missing")
    need("qy_prescan_status" in text, "status component missing")
    need("def _qy_prescan_tier1(" in text, "tier1 missing")
    need("def _qy_prescan_tier2(" in text, "tier2 missing")
    need("def _qy_prescan_tier3(" in text, "tier3 missing")
    need("_prescan_generation" in text, "generation guard missing")
    need("_qy_prescan_tier1," in text, "tier1 not wired")
    need("_qy_prescan_tier3," in text, "tier3 not wired")
    need("vector_count" in text, "vector_count missing")
    need("def _qy_prescan_clear(" in text, "clear helper missing")
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"FAIL: syntax {e}", file=sys.stderr)
        errs += 1
    return errs


def main() -> int:
    original = GUI.read_text(encoding="utf-8")
    try:
        updated = apply(original)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if updated != original:
        GUI.write_text(updated, encoding="utf-8")
        print("patched")
    else:
        print("already patched")
    return verify(GUI.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
