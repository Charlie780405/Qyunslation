---
name: image-overlay-translation
description: >-
  图片嵌字翻译：RapidOCR 检测、think:false 分批翻译、Otsu 配色、纯色遮盖、字体粗细对齐。
  触发：图片翻译、嵌字、流程图翻译、译文丢字、OCR 没检出、文字看不见、遮盖、图层、
  image_translate、RapidOCR、ImageOverlayWorkflow、对比度、蓝框白字。
---

# 图片嵌字翻译（SK-Q002）

qyunslation 自治 Skill。管 `extensions/image_translate.py` 与预览 viewer，不改 HPD 服务本身。

## 铁律

1. **流程图必须 RapidOCR**——HPD 把整图标成 `<BLOCK>image`，内部零 OCR（实测 60 标签只出 2 脚注）。HPD 仅作扫描件回退。
2. **关思考用 API 参数**——`think: false`；`/no_think` 前缀对 qwen3.6 无效（747 vs 66 token）。`num_predict` 耗尽时 `content` 是空串，静默返回空字典。
3. **禁止先全擦后条件画**——缺译回退原文、不擦不画。
4. **取色禁止单侧灰度阈值**——`vals < 120` 会把白字丢掉，蓝框对比度塌到 1。必须 Otsu 分层取中位数；对比度 `< 60` 强制黑/白。
5. **纯色块用矩形填充**——`cv2.rectangle(..., -1)`；TELEA inpaint 会涂抹花纹。边框 BGR 标准差 `< 12` 判纯色。
6. **粗细与对齐从原图测**——文字像素面积比 ≥ 0.28 用 Bold；质心偏移判左/中/右。字面：`NotoSansSC-Regular.otf` / `NotoSansSC-Bold.otf`。
7. **批量翻译分批 + 单条重试**——每批 25；编号解析失败不得静默丢弃。
8. **全屏预览整容器克隆**——禁止 `querySelectorAll('img, canvas, .prose')` 嵌套双命中叠图。
9. **判据落 verify**——`scripts/verify-plan-022.sh`：OCR≥55、命中≥95%、对比度≥60。

## 施工顺序

```
RapidOCR → translate_texts(think:false, batch=25, retry)
→ _analyze_box_style(Otsu) → 纯色填充/inpaint → Bold/Regular + 对齐嵌字
```

## 排障

| 现象 | 看 |
| --- | --- |
| 译文几乎原样 | HPD 只出 2 框；应走 RapidOCR |
| 蓝/彩框内看不见字 | `_analyze_box_style` 对比度；禁 `vals<120` |
| 框内花纹涂抹 | 应用纯色填充却走了 inpaint |
| 字太细 / 偏左 | Bold 面积比、align 质心 |
| 全屏上下两份 | viewer 嵌套选择器 |
| 永久转圈无结果 | `think` 烧光 / PLAN-020 stale-guard |

详表与诊断脚本见 [reference.md](reference.md)；踩坑 SSOT 见 [pitfalls.md](pitfalls.md)。
