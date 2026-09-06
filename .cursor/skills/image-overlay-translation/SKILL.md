---
name: image-overlay-translation
description: >-
  图片嵌字翻译：RapidOCR 检测、think:false 分批翻译、Otsu 配色、纯色遮盖、字体粗细对齐、QC 关卡。
  触发：图片翻译、嵌字、流程图翻译、译文丢字、OCR 没检出、文字看不见、遮盖、图层、
  image_translate、RapidOCR、ImageOverlayWorkflow、对比度、蓝框白字、涂抹痕迹、黑框。
---

# 图片嵌字翻译（SK-Q002）

qyunslation 自治 Skill。管 `extensions/image_translate.py` 与预览 viewer，不改 HPD 服务本身。

## 铁律

1. **流程图必须 RapidOCR**——HPD 把整图标成 `<BLOCK>image`，内部零 OCR。HPD 仅作扫描件回退。
2. **关思考用 API 参数**——`think: false`；`/no_think` 前缀对 qwen3.6 无效。`num_predict` 耗尽时 `content` 空串。
3. **禁止先全擦后条件画**——缺译回退原文、不擦不画；未翻译框像素擦后必须回贴。
4. **取色禁止单侧灰度阈值**——必须 Otsu 分层取中位数；对比度 `< 60` 强制黑/白。
5. **颜色判据一律按通道算**——禁止把 BGR 拍平求 std（彩底通道差会虚报非纯色）。
6. **纯色判定用「通道 std + 贴近中位数占比」**——纯 std 会被括号线等边缘污染翻车。
7. **纯色块用矩形填充**——`cv2.rectangle(..., -1)`；`inpaint` 全图只做一次，禁止循环内重算。
8. **擦除按 OCR 框、排版按可用区域**——`_available_box` 向外扩到碰邻框/非背景为止。
9. **行高用 `font.getmetrics()`**——禁止用 `getbbox` 墨迹高判断能否放下（会溢出）。
10. **粗细与对齐从原图测**——面积比 ≥ 0.28 用 Bold；质心偏移判左/中/右。
11. **批量翻译分批 + 单条重试**——每批 25；编号解析失败不得静默丢弃。
12. **全屏预览整容器克隆**——禁止嵌套双命中叠图。
13. **收工前必须跑 QC 六项**——覆盖/绘制/墨迹实测/对比度/溢出/可读性；`QYUNSLATION_IMAGE_QC_STRICT=1` 为发布门禁。
14. **判据落 verify**——`scripts/verify-plan-023.sh`：OCR≥55、命中≥95%、solid≥55/60、QC 全绿。

## 施工顺序

```
RapidOCR → translate_texts(think:false, batch=25, retry)
→ _analyze_box_style(按通道) → _available_box
→ 纯色填充 / 一次 inpaint → 回贴未译框 → 嵌字 → _qc_report
```

## 排障

| 现象 | 看 |
| --- | --- |
| 译文几乎原样 | HPD 只出 2 框；应走 RapidOCR |
| 蓝/彩框内看不见字 | `_analyze_box_style` 对比度；禁 `vals<120` |
| 框内花纹涂抹 / 16 周黑框 | solid 误判走了 inpaint；查通道 std + frac |
| 底部英文像丢失 | 可用区域未扩 / 墨迹高溢出；查 QC C5/C6 |
| 字太细 / 偏左 | Bold 面积比、align 质心 |
| 全屏上下两份 | viewer 嵌套选择器 |
| journalctl 无嵌字日志 | sidecar 缺 `basicConfig` |

详表与诊断脚本见 [reference.md](reference.md)；踩坑 SSOT 见 [pitfalls.md](pitfalls.md)。
