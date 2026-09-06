# SPDX-License-Identifier: MPL-2.0
"""自定义扩展 API：图片嵌字 + 探针 + 术语表管理。"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from qyunslation.extensions.glossary_db import load_glossary, merge_glossary, save_glossary
from qyunslation.extensions.image_translate import probe_image, translate_image

router = APIRouter(tags=["Custom Extensions"])


@router.post("/image-translate", summary="图片嵌字翻译（上传图→返回译后图）")
async def image_translate_endpoint(
    file: UploadFile = File(...),
    to_lang: str = Form("简体中文", description="目标语言"),
):
    """上传设计图，返回图内文字已翻译为目标语言的图片（版式不变）。"""
    suffix = Path(file.filename or "image.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        raise HTTPException(400, f"不支持的图片格式: {suffix}")
    tmp_in = None
    tmp_out = None
    n = 0
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(await file.read())
            tmp_in = f.name
        tmp_out = tmp_in.replace(suffix, f"_zh{suffix}")
        n = translate_image(tmp_in, tmp_out, to_lang=to_lang)
        data = Path(tmp_out).read_bytes()
    except Exception as e:
        raise HTTPException(500, f"图片嵌字失败: {e}") from e
    finally:
        if tmp_in:
            Path(tmp_in).unlink(missing_ok=True)
        if tmp_out:
            Path(tmp_out).unlink(missing_ok=True)
    return Response(content=data, media_type="image/png", headers={"X-Translated-Blocks": str(n)})


@router.post("/image-probe", summary="文档内嵌图片轻量探针（仅OCR不调LLM）")
async def image_probe_endpoint(
    file: UploadFile = File(...),
    to_lang: str = Form("简体中文", description="目标语言"),
    display_width_pt: float = Form(0.0),
    display_height_pt: float = Form(0.0),
    page_frac: float = Form(-1.0),
    is_header: bool = Form(False),
):
    """PLAN-027a：仅 OCR + 策略判定，供预扫描 Tier-2 使用。失败返回 status=error，不抛 500。"""
    suffix = Path(file.filename or "image.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return JSONResponse(
            {
                "status": "error",
                "should_translate": False,
                "reason": f"unsupported_format:{suffix}",
                "detected_blocks": 0,
                "translatable_blocks": 0,
                "detected_lang": "unknown",
                "text_samples": [],
            }
        )
    tmp_in = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(await file.read())
            tmp_in = f.name
        result = probe_image(
            tmp_in,
            to_lang=to_lang,
            display_width_pt=display_width_pt,
            display_height_pt=display_height_pt,
            page_frac=(None if page_frac < 0 else page_frac),
            is_header=is_header,
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse(
            {
                "status": "error",
                "should_translate": False,
                "reason": f"probe_failed:{e}",
                "detected_blocks": 0,
                "translatable_blocks": 0,
                "detected_lang": "unknown",
                "text_samples": [],
            }
        )
    finally:
        if tmp_in:
            Path(tmp_in).unlink(missing_ok=True)


@router.get("/glossary", summary="获取术语表")
async def get_glossary():
    g = load_glossary()
    return {"glossary": g, "count": len(g)}


class GlossaryItem(BaseModel):
    src: str
    dst: str


@router.post("/glossary", summary="添加/更新术语")
async def add_glossary(item: GlossaryItem):
    if not item.src.strip() or not item.dst.strip():
        raise HTTPException(400, "术语源/译文不能为空")
    merged = merge_glossary({item.src.strip(): item.dst.strip()})
    return {"ok": True, "count": len(merged)}


@router.delete("/glossary/{src}", summary="删除术语")
async def delete_glossary(src: str):
    g = load_glossary()
    if src in g:
        del g[src]
        save_glossary(g)
        return {"ok": True, "deleted": src}
    return {"ok": False, "error": "术语不存在"}
