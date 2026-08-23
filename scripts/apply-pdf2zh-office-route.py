#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-005e：pdf2zh GUI 内路由 Word/图片到 Qyunslation sidecar (:8010)。"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
)

MARKER = "_qy_office_sidecar"
OFFICE_HELPER = '''
# --- PLAN-005e: Word/图片 → Qyunslation sidecar (:8010) ---
_QY_OFFICE_SIDECAR_EXT = {".doc", ".docx", ".png", ".jpg", ".jpeg", ".webp"}
_QY_OFFICE_SIDECAR_URL = "http://127.0.0.1:8010"


def _qy_is_office_sidecar_file(path: Path) -> bool:
    return path.suffix.lower() in _QY_OFFICE_SIDECAR_EXT


async def _qy_run_office_sidecar_task(
    file_path: Path,
    output_dir: Path,
    progress,
    task_prefix: str = "",
):
    """Route Word/image to sidecar; returns (mono_path, dual, glossary, token_usage)."""
    import json

    suffix = file_path.suffix.lower()
    workflow_type = "image_overlay" if suffix in {".png", ".jpg", ".jpeg", ".webp"} else "docx"
    payload = {"workflow_type": workflow_type, "to_lang": "简体中文"}

    progress(0.05, desc=f"{task_prefix}提交文档/图片翻译…")

    def _submit() -> str:
        with open(file_path, "rb") as fh:
            resp = requests.post(
                f"{_QY_OFFICE_SIDECAR_URL}/service/translate/file",
                files={"file": (file_path.name, fh)},
                data={"payload": json.dumps(payload)},
                timeout=120,
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("task_started"):
            raise gr.Error(data.get("message", "文档翻译服务启动失败"))
        return data["task_id"]

    task_id = await asyncio.to_thread(_submit)

    while True:
        await asyncio.sleep(2)

        def _poll():
            resp = requests.get(
                f"{_QY_OFFICE_SIDECAR_URL}/service/status/{task_id}",
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()

        status = await asyncio.to_thread(_poll)
        pct = status.get("progress_percent") or 0
        msg = status.get("status_message") or "处理中…"
        progress(0.1 + 0.85 * pct / 100.0, desc=f"{task_prefix}{msg}")

        if status.get("error_flag"):
            raise gr.Error(status.get("status_message", "文档/图片翻译失败"))

        if status.get("download_ready"):
            downloads = status.get("downloads") or {}
            dl_key = None
            for key in ("docx", "image", "file"):
                if key in downloads:
                    dl_key = key
                    break
            if dl_key is None and downloads:
                dl_key = next(iter(downloads))
            if dl_key is None:
                raise gr.Error("翻译完成但无可用下载")

            dl_url = downloads[dl_key]
            if not dl_url.startswith("http"):
                dl_url = f"{_QY_OFFICE_SIDECAR_URL}{dl_url}"

            def _download():
                resp = requests.get(dl_url, timeout=600)
                resp.raise_for_status()
                return resp.content

            content = await asyncio.to_thread(_download)
            out_suffix = file_path.suffix
            if dl_key == "docx":
                out_suffix = ".docx"
            out_name = f"{file_path.stem}.zh{out_suffix}"
            out_path = output_dir / out_name
            out_path.write_bytes(content)
            progress(1.0, desc=f"{task_prefix}完成")
            return out_path, None, None, None

        if not status.get("is_processing") and not status.get("download_ready"):
            raise gr.Error(status.get("status_message", "文档/图片翻译异常结束"))

'''

FILE_TYPES_OLD = 'file_types=[".pdf", ".PDF"],'
FILE_TYPES_NEW = (
    'file_types=[".pdf", ".PDF", ".doc", ".docx", ".png", ".jpg", ".jpeg"],'
)

LOOP_ANCHOR = '''            # Build translation settings
            translate_settings = _build_translate_settings(
                settings.clone(),
                file_path,
                output_dir,
                SaveMode.follow_settings,
                ui_inputs,
            )

            # Create task
            task = asyncio.create_task(
                _run_translation_task(
                    translate_settings,
                    file_path,
                    state,
                    progress,
                    task_prefix=task_prefix,
                )
            )'''

LOOP_PATCH = '''            if _qy_is_office_sidecar_file(file_path):
                task = asyncio.create_task(
                    _qy_run_office_sidecar_task(
                        file_path,
                        output_dir,
                        progress,
                        task_prefix=task_prefix,
                    )
                )
            else:
                # Build translation settings
                translate_settings = _build_translate_settings(
                    settings.clone(),
                    file_path,
                    output_dir,
                    SaveMode.follow_settings,
                    ui_inputs,
                )

                # Create task
                task = asyncio.create_task(
                    _run_translation_task(
                        translate_settings,
                        file_path,
                        state,
                        progress,
                        task_prefix=task_prefix,
                    )
                )'''


def apply(text: str) -> tuple[str, bool]:
    changed = False

    if MARKER not in text:
        anchor = "async def translate_files("
        if anchor not in text:
            print("ERROR: translate_files anchor not found", file=sys.stderr)
            return text, False
        text = text.replace(anchor, OFFICE_HELPER + "\n" + anchor, 1)
        changed = True

    if FILE_TYPES_OLD in text:
        text = text.replace(FILE_TYPES_OLD, FILE_TYPES_NEW, 1)
        changed = True
    elif FILE_TYPES_NEW in text:
        pass
    else:
        print("WARN: file_types anchor not found", file=sys.stderr)

    if LOOP_ANCHOR in text:
        text = text.replace(LOOP_ANCHOR, LOOP_PATCH, 1)
        changed = True
    elif "_qy_is_office_sidecar_file(file_path)" in text:
        pass
    else:
        print("ERROR: translate loop anchor not found", file=sys.stderr)
        return text, False

    return text, changed


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated, changed = apply(original)
    if not changed and MARKER in original:
        print("already patched:", GUI)
        return 0
    if updated == original:
        print("no changes applied", file=sys.stderr)
        return 1
    GUI.write_text(updated, encoding="utf-8")
    print("patched:", GUI)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
