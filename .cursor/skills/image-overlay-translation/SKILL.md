---
name: image-overlay-translation
description: >-
  图片嵌字翻译：RapidOCR 检测、think:false 分批翻译、Otsu 配色、纯色遮盖、字体粗细对齐、QC 关卡。
  触发：图片翻译、嵌字、流程图翻译、译文丢字、OCR 没检出、文字看不见、遮盖、图层、
  image_translate、RapidOCR、ImageOverlayWorkflow、对比度、蓝框白字、涂抹痕迹、黑框、对齐。
---

# 图片嵌字翻译（SK-Q002）

qyunslation 自治 Skill。管 `extensions/image_translate.py` 与预览 viewer，不改 HPD 服务本身。

## 铁律

1. **流程图必须 RapidOCR**——HPD 把整图标成 `<BLOCK>image`。HPD 仅作扫描件回退。
2. **关思考用 API 参数**——`think: false`；`/no_think` 对 qwen3.6 无效。
3. **禁止先全擦后条件画**——缺译不擦不画；未译框像素擦后必须回贴。
4. **取色禁止单侧灰度阈值**——Otsu 分层中位数；对比度 `< 60` 强制黑/白。
5. **颜色判据一律按通道算**——禁止 BGR 拍平求 std。
6. **纯色用「通道内点 std + 贴近中位数占比」**——边框内缩采样抗蹭线。
7. **纯色块矩形填充**——`inpaint` 全图只一次。
8. **擦除按 OCR 框；排版锚原文墨迹**——可用区只做换行宽度与溢出余量，禁止当排版框居中。
9. **对齐从行间一致性推断**——比各行 `x1/cx/x2` 标准差；实心色块强制 center；禁质心对框中心三分桶。
10. **锚点用主行墨迹**——最宽 y 投影行，避开括号线把整体 ink bbox 拉歪。
11. **实心/居中仅钳图像边界**——禁止被不对称可用区左右/上下推偏。
12. **行高用 `font.getmetrics()`**——禁 `getbbox` 墨迹高判能否放下。
13. **层级按「背景色桶 + 白底 y 行带」**——组内统一字号；组间 `k × orig_em`。
14. **全屏克隆禁止嵌套 `.qy-viewer-inner`**——全屏兜底 `calc(100vh-72px)`。
15. **收工前 QC**——C1–C6 + C7a/C7b + C8（成品 vs 计划绘制锚点）；`ALIGN_TOL_PX` 默认 12。
16. **判据落 verify**——`scripts/verify-plan-025.sh`。

## 施工顺序

```
RapidOCR → translate_texts → _analyze_box_style/_ink_geometry
→ _available_box → 擦除/一次 inpaint → 回贴
→ _assign_tier_sizes → 墨迹锚点嵌字 → _qc_report
```

## 排障

| 现象 | 看 |
| --- | --- |
| 译文整体右移/下沉 | 是否用可用区当排版框；C8 `plan_dx/plan_dy` |
| 同级字号不一 | `_assign_tiers` / C7a |
| 蓝框涂抹 / 16 周黑框 | solid 通道 std + frac |
| 周数竖向偏 | 是否用整体 ink 含括号线；改主行 |
| 全屏裁底部 | 嵌套 `.qy-viewer-inner` |
| journalctl 无嵌字日志 | sidecar `basicConfig` |

详表见 [reference.md](reference.md)；踩坑见 [pitfalls.md](pitfalls.md)。
