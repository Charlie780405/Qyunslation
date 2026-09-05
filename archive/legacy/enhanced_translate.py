#!/usr/bin/env python3
"""增强翻译整合层：术语表注入 + DocuTranslate 翻译 + 图片嵌字（阶段 4 核心）。

把阶段 2（内嵌图嵌字）+ 阶段 3（术语表）串成完整流程：
  输入文档 → 术语表注入(custom_prompt) → DocuTranslate 翻译 → 下载结果 → 内嵌图嵌字 → 最终结果

用法：
  from enhanced_translate import enhanced_translate
  result_bytes = enhanced_translate(file_bytes, "test.docx", to_lang="中文")
"""
import io
import json
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from qyunslation.extensions.glossary_db import build_glossary_prompt, load_glossary
from qyunslation.extensions.image_replace import translate_docx_images

DOCUTRANSLATE_API = "http://127.0.0.1:8010"


def _submit_translate(file_bytes, filename, to_lang, custom_prompt=None):
    boundary = uuid.uuid4().hex
    payload = {"workflow_type": "auto", "to_lang": to_lang}
    if custom_prompt:
        payload["custom_prompt"] = custom_prompt
    pbytes = json.dumps(payload, ensure_ascii=False).encode()
    body = (b"--" + boundary.encode() + b"\r\n"
            b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n\r\n'
            + file_bytes + b"\r\n--" + boundary.encode() + b"\r\n"
            b'Content-Disposition: form-data; name="payload"\r\n\r\n'
            + pbytes + b"\r\n--" + boundary.encode() + b"--\r\n")
    req = urllib.request.Request(f"{DOCUTRANSLATE_API}/service/translate/file", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["task_id"]


def _poll_download(task_id, file_type="docx", max_wait=600):
    for _ in range(max_wait // 3):
        time.sleep(3)
        with urllib.request.urlopen(f"{DOCUTRANSLATE_API}/service/status/{task_id}", timeout=15) as r:
            st = json.load(r)
        if st.get("is_processing") is False:
            if not st.get("download_ready"):
                raise RuntimeError(f"翻译失败: {st.get('status_message', '')[:200]}")
            with urllib.request.urlopen(f"{DOCUTRANSLATE_API}/service/download/{task_id}/{file_type}", timeout=60) as r:
                return r.read()
    raise TimeoutError("翻译超时")


def enhanced_translate(file_bytes, filename, to_lang="中文", use_glossary=True, translate_images=True,
                       custom_glossary=None):
    """完整增强翻译：术语表注入 → 翻译 → 嵌字。返回 (结果bytes, 元信息dict)。"""
    meta = {"glossary_terms": 0, "images_translated": 0}

    # 1. 术语表注入
    glossary = custom_glossary if custom_glossary is not None else (load_glossary() if use_glossary else {})
    custom_prompt = build_glossary_prompt(glossary, to_lang) if glossary else None
    meta["glossary_terms"] = len(glossary)

    # 2. 翻译
    task_id = _submit_translate(file_bytes, filename, to_lang, custom_prompt)
    result = _poll_download(task_id)

    # 3. 内嵌图嵌字（仅 docx，pdf/markdown 走 image_replace 其他函数）
    if translate_images and filename.lower().endswith(".docx"):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(result)
            tmp_in = f.name
        tmp_out = tmp_in.replace(".docx", "_img.docx")
        meta["images_translated"] = translate_docx_images(tmp_in, tmp_out)
        result = Path(tmp_out).read_bytes()
        Path(tmp_in).unlink(missing_ok=True)
        Path(tmp_out).unlink(missing_ok=True)

    return result, meta


if __name__ == "__main__":
    import sys
    src = sys.argv[1]
    data = Path(src).read_bytes()
    result, meta = enhanced_translate(data, Path(src).name, to_lang="中文")
    out = sys.argv[2] if len(sys.argv) > 2 else src.replace(".docx", "_enhanced.docx")
    Path(out).write_bytes(result)
    print(f"增强翻译完成 → {out}，术语表 {meta['glossary_terms']} 条，嵌字 {meta['images_translated']} 张")
