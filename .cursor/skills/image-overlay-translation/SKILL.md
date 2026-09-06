---
name: image-overlay-translation
description: >-
  图片嵌字翻译：RapidOCR 检测、think:false 分批翻译、Otsu 配色、纯色遮盖、字号层级、墨迹锚点对齐、QC 关卡。
  触发：图片翻译、嵌字、流程图翻译、译文丢字、OCR 没检出、文字看不见、遮盖、图层、
  image_translate、RapidOCR、ImageOverlayWorkflow、对比度、蓝框白字、涂抹痕迹、黑框、对齐、错位。
---

# 图片嵌字翻译（SK-Q002）

qyunslation 自治 Skill。管 `extensions/image_translate.py` 与预览 viewer，不改 HPD 服务本身。

## 施工顺序

```
RapidOCR → translate_texts → _analyze_box_style（含 _ink_geometry/_infer_align）
→ _available_box → 擦除 / 一次 inpaint → 回贴未译框
→ _assign_left_groups → _assign_tier_sizes → 墨迹锚点嵌字 → _qc_report
```

## 铁律

### A. OCR 与翻译

1. **流程图必须 RapidOCR**——HPD 把整图标成 `<BLOCK>image`；HPD 仅作扫描件回退。
2. **关思考用 API 参数**——`think: false`；`/no_think` 对 qwen3.6 无效。
3. **`to_lang` 必须透传**——docx/custom_api 漏传会永远输出简体中文。

### B. 取色与擦除

4. **取色禁止单侧灰度阈值**——Otsu 分层中位数；对比度 `< 60` 强制黑/白。
5. **颜色判据一律按通道算**——禁止 BGR 拍平求 std。
6. **纯色判据 = 通道内点 std + 贴近中位数占比**——边框内缩 2px 采样抗蹭线。
7. **纯色块矩形填充**——非纯色累加 mask，`inpaint` 全图只做一次。
8. **禁止先全擦后条件画**——缺译不擦不画；未译框像素擦前备份、擦后回贴。

### C. 字号

9. **行高用 `font.getmetrics()`**——禁 `getbbox` 墨迹高判能否放下。
10. **层级按「背景色桶 + 白底 y 行带」**——禁按墨迹高度分档（字形差异会误判）。
11. **组内字号统一、组间保持原图比例**——`k = min(fit/orig_em)`，`orig_em` 取组内 75 分位；outlier 单独降级告警，不得拖垮 k。
12. **粗细组内多数决**——同级条目不得有的 Bold 有的 Regular。

### D. 对齐（排版基准）

13. **排版锚原文墨迹，可用区只做换行宽与溢出余量**——禁止拿 `_available_box` 当排版框居中。
14. **锚点取主行**——`_main_row` 排除线状行（宽高比 ≥ 8 且高度 < 最高行 40%），否则会锚到括号线/色带上。
15. **对齐从行间一致性推断**——比各行 `x1/cx/x2` 标准差；只有**非白底**实心块才强制 center。
16. **跨框左对齐组**——纵向邻接 + 左墨迹边一致 + 右端明显参差 → 整组锚同一 `x1`；等宽条目不成组。
17. **水平定位用 `getmask().getbbox()`**——`font.getbbox()` x0 恒为 0，拿不到左边距，「·」或前导空格会整体右移。
18. **强锚只钳图像边界**——居中 / 实心彩色块 / 左对齐组成员不得被不对称可用区推偏。

### E. 交付

19. **全屏克隆禁止嵌套 `.qy-viewer-inner`**——全屏兜底 `max-height: calc(100vh - 72px)`。
20. **收工前 QC**——C1–C6 + C7a/C7b + C8/C9；`QYUNSLATION_IMAGE_QC_STRICT=1` 为门禁。
21. **判据落 verify**——`scripts/verify-plan-025.sh`。

## QC 检查项

| 码 | 查什么 |
| --- | --- |
| C1/C2 | 覆盖率、绘制块数 |
| C3/C4 | 墨迹实测（擦了没画）、对比度 |
| C5/C6 | 溢出、可读性（WARN） |
| C7a/C7b | 组内字号一致、组间比例偏差 |
| C8 | 成品墨迹 vs 计划绘制锚点，`ALIGN_TOL_PX` 默认 12 |
| C9 | 左对齐组成品 `x1` 参差 |

## 排障

| 现象 | 看 |
| --- | --- |
| 译文整体右移/下沉 | 是否拿可用区当排版框；C8 `plan_dx/plan_dy` |
| 单个标签比同排高一截 | `_main_row` 是否锚到线状行 |
| bullet 列表参差 | `_assign_left_groups` / C9 |
| 带「·」或前导空格的行偏右 | 是否用 `getbbox` 代替 `getmask` 定位 |
| 同级字号不一 | `_assign_tiers` / C7a |
| 蓝框涂抹 / 黑框 | solid 通道 std + frac |
| 全屏裁底部 | 嵌套 `.qy-viewer-inner` |
| journalctl 无嵌字日志 | sidecar `basicConfig` |

详表见 [reference.md](reference.md)；踩坑见 [pitfalls.md](pitfalls.md)。
