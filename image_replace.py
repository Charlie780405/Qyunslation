#!/usr/bin/env python3
"""内嵌图后处理：对翻译结果文档里的图片做嵌字翻译并替换回。

阶段 2 核心：DocuTranslate 翻译时图片原样保留（docx 在 word/media/，pdf/markdown 是 base64 内嵌），
本模块在翻译完成后提取这些图片 → image_translate 嵌字 → 替换回文档。

支持：
  - docx：解包 zip → 对 word/media/* 图片嵌字 → 替换 → 重打包
  - markdown：提取 ![](data:image/...;base64,...) → 嵌字 → 替换 base64
"""
import base64
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from image_translate import translate_image

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def translate_docx_images(input_docx, output_docx, skip_small=True):
    """解包 docx，对 word/media/ 里的图片嵌字，重打包。返回处理数量。"""
    tmp = tempfile.mkdtemp(prefix="docx_img_")
    try:
        with zipfile.ZipFile(input_docx) as z:
            z.extractall(tmp)
        media_dir = Path(tmp) / "word" / "media"
        count = 0
        if media_dir.exists():
            for img in sorted(media_dir.iterdir()):
                if img.suffix.lower() not in IMG_EXTS:
                    continue
                # 跳过大图图标/Logo（<8KB 通常是无文字图标）
                if skip_small and img.stat().st_size < 8192:
                    continue
                try:
                    n = translate_image(str(img), str(img))
                    count += 1
                    print(f"  [{img.name}] 嵌字 {n} 个文字块")
                except Exception as e:
                    print(f"  [{img.name}] 跳过: {e}")
        # 重打包
        with zipfile.ZipFile(output_docx, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(Path(tmp).rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(tmp))
        return count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def translate_markdown_images(md_text):
    """提取 markdown 里的 base64 图片 → 嵌字 → 替换回。返回 (新markdown, 处理数量)。"""
    pattern = re.compile(r"!\[[^\]]*\]\((data:image/(?:png|jpe?g|webp);base64,([A-Za-z0-9+/=]+))\)")
    count = 0
    tmpdir = tempfile.mkdtemp(prefix="md_img_")

    def repl(m):
        nonlocal count
        mime, b64 = m.group(1), m.group(2)
        ext = ".png" if "png" in mime else (".jpg" if "jpeg" in mime or "jpg" in mime else ".webp")
        img_path = Path(tmpdir) / f"img_{count}{ext}"
        try:
            img_path.write_bytes(base64.b64decode(b64))
            translate_image(str(img_path), str(img_path))
            new_b64 = base64.b64encode(img_path.read_bytes()).decode()
            count += 1
            return f"![Image](data:{mime.split(';')[0]};base64,{new_b64})"
        except Exception as e:
            print(f"  [markdown 图 {count}] 跳过: {e}")
            return m.group(0)

    new_md = pattern.sub(repl, md_text)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return new_md, count


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    if path.endswith(".docx"):
        out = sys.argv[2] if len(sys.argv) > 2 else path.replace(".docx", "_imgtrans.docx")
        n = translate_docx_images(path, out)
        print(f"docx 处理 {n} 张图片 → {out}")
    else:
        text = Path(path).read_text()
        new_text, n = translate_markdown_images(text)
        out = sys.argv[2] if len(sys.argv) > 2 else path.replace(".md", "_imgtrans.md")
        Path(out).write_text(new_text)
        print(f"markdown 处理 {n} 张图片 → {out}")
