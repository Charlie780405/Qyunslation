#!/usr/bin/env python3
"""图片嵌字翻译模块：RapidOCR 检测识别 → qwen3.6:27b 翻译 → opencv 擦除 → PIL 嵌字

阶段 1 验证通过（12 块文字精确检测/翻译/嵌字，非文字区域 97.5% 一致）。
阶段 2 由 DocuTranslate 内嵌图整合调用。

技术栈（全复用已有能力 + 最小增量）：
  - 检测+识别: RapidOCR（DBNet onnx + CRNN，本地 CPU，不装 paddle 框架）
  - 翻译:      qwen3.6:27b（泰州 Ollama，请求级 num_ctx 提速）
  - 擦除:      opencv inpaint（精确 mask，保护图形）
  - 嵌字:      PIL + NotoSansSC（字号自适应 + 颜色匹配）
"""
import base64
import json
import re
import time
import urllib.request

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR
from PIL import Image, ImageDraw, ImageFont

OLLAMA = "http://100.67.66.123:11434"
FONT = "/home/dev/.fonts/NotoSansSC.ttf"
MODEL = "qwen3.6:27b"

# RapidOCR 引擎（det_limit_side_len 放大避免小字丢失）
_engine = RapidOCR(det_limit_side_len=2400)


def ocr_image(img_path):
    """RapidOCR 检测+识别 → [(x1,y1,x2,y2,text,score), ...]（按从上到下排序）"""
    result, _ = _engine(img_path)
    boxes = []
    if result:
        for box, text, score in result:
            x = [p[0] for p in box]
            y = [p[1] for p in box]
            boxes.append((int(min(x)), int(min(y)), int(max(x)), int(max(y)), text.strip(), float(score)))
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


def translate_texts(texts, model=MODEL, num_ctx=4096):
    """批量翻译文本 → {序号: 译文}，纯译文不加注释"""
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    prompt = (f"Translate each numbered line to Chinese. Output ONLY the translation, "
              f"keep the same numbering, no explanations, no parentheses notes:\n{numbered}")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": num_ctx},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        content = json.loads(r.read().decode())["message"]["content"]
    trans = {}
    for line in content.split("\n"):
        m = re.match(r"(\d+)[.、)\s]+(.+)", line.strip())
        if m:
            trans[int(m.group(1))] = m.group(2).strip()
    return trans


def translate_image(img_path, out_path, to_lang="中文"):
    """完整图片嵌字翻译：读图 → OCR → 翻译 → 擦除 → 嵌字 → 存图"""
    img_cv = cv2.imread(img_path)
    orig = img_cv.copy()
    boxes = ocr_image(img_path)
    if not boxes:
        return 0

    # 翻译
    texts = [b[4] for b in boxes]
    trans = translate_texts(texts)

    # 擦除前取原文字色（深色像素均值）
    colors = []
    for b in boxes:
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        gray = cv2.cvtColor(orig[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        vals = gray.flatten()
        vals = vals[vals < 120]
        color_val = int(vals.mean()) if len(vals) > 0 else 17
        colors.append((color_val, color_val, color_val))

    # 擦除（精确 mask，收缩 1px 保护相邻图形）
    for b in boxes:
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        mask = np.zeros(img_cv.shape[:2], np.uint8)
        cv2.rectangle(mask, (x1 + 1, y1 + 1), (x2 - 1, y2 - 1), 255, -1)
        img_cv = cv2.inpaint(img_cv, mask, 3, cv2.INPAINT_TELEA)

    # 嵌字
    result = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(result)
    for i, b in enumerate(boxes):
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        zh = trans.get(i + 1, "")
        if not zh:
            continue
        size = max(12, min(int((y2 - y1) * 0.9), 40))
        font = ImageFont.truetype(FONT, size)
        d.text((x1, y1 - int(size * 0.1)), zh, fill=colors[i], font=font)

    result.save(out_path)
    return len(boxes)


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dense_design.png"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/dense_design_zh.png"
    t0 = time.time()
    n = translate_image(src, dst)
    print(f"翻译 {n} 个文字块 → {dst} ({time.time()-t0:.1f}s)")
