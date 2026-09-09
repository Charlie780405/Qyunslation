---
name: image-overlay-translation
description: >-
  图片嵌字翻译：RapidOCR 检测、think:false 分批翻译、Otsu 配色、纯色遮盖、字号层级、墨迹锚点对齐、QC 关卡。
  文档内嵌图：DOCX DrawingML 实例解耦、PDF 共享 XObject 隔离、矢量安全覆盖、上传预扫描代际防线。
  触发：图片翻译、嵌字、流程图翻译、译文丢字、OCR 没检出、文字看不见、遮盖、图层、
  image_translate、RapidOCR、ImageOverlayWorkflow、对比度、蓝框白字、涂抹痕迹、黑框、对齐、错位、
  文档内嵌图、docx 图片、pdf 插图、imgtr。
---

# 图片嵌字翻译（SK-Q002）

qyunslation 自治 Skill。管 `extensions/image_translate.py` 与预览 viewer，不改 HPD 服务本身。
本 Skill 是**可迁移规范**：任何新图都按通用原则与自检清单走，禁止只对单张样例打补丁。

## 施工顺序

```
RapidOCR → translate_texts → _analyze_box_style（含 _ink_geometry/_infer_align）
→ _available_box → _fill_band 擦除 + _line_guard_mask → 文字带外回贴 → 一次 inpaint
→ 回贴未译框 → _assign_left_groups → _assign_tier_sizes → 墨迹锚点嵌字 → _qc_report
```

## 通用原则（先于铁律）

1. **OCR 框不是文字范围**——框会蹭到邻近图元；擦除、对齐、字号一切基于框的操作，先收敛到墨迹几何。
2. **破坏性操作先建保护掩膜**——填充/inpaint 前必须回答「框内哪些像素不属于本框的文字」。
3. **度量前先确认口径**——布局盒 / 墨迹盒 / 行盒不可混用（见 reference 对照表）。
4. **版式变换必须可证明不越界**——能放下就保中心，放不下才单向生长。

## 铁律

### A. OCR 与翻译

1. **流程图必须 RapidOCR**——HPD 把整图标成 `<BLOCK>image`；HPD 仅作扫描件回退。
2. **关思考用 API 参数**——`think: false`；`/no_think` 对 qwen3.6 无效。
3. **`to_lang` 必须透传**——docx/custom_api 漏传会永远输出简体中文。

### B. 取色与擦除（原则 1、2）

4. **取色禁止单侧灰度阈值**——Otsu 分层中位数；对比度 `< 60` 强制黑/白。
5. **颜色判据一律按通道算**——禁止 BGR 拍平求 std。
6. **纯色判据 = 通道内点 std + 贴近中位数占比**——边框内缩 2px 采样抗蹭线。
7. **纯色只填文字带 `_fill_band`**——禁止整 OCR 框 `rectangle`；线状行落在带外。贯穿线用 `_line_guard_mask`；擦后回贴文字带外原图，挡住邻框越界。
8. **非纯色累加 mask，`inpaint` 全图一次**——并扣掉 guard。缺译不擦不画；未译框擦前备份、擦后回贴。

### C. 字号（原则 3）

9. **行高用 `font.getmetrics()`**——禁 `getbbox` 墨迹高判能否放下。
10. **层级按「背景色桶 + 白底 y 行带」**——禁按墨迹高度分档。
11. **组内字号统一、组间保持原图比例**——`k = min(fit/orig_em)`，`orig_em` 取 75 分位；outlier 不得拖垮 k。
12. **粗细组内多数决**。

### D. 对齐（原则 1、3、4）

13. **排版锚原文墨迹，可用区只做换行宽与溢出余量**。
14. **锚点取主行**——`_main_row` 排除线状行（宽高比 ≥ 8 且高度 < 最高行 40%）。
15. **对齐从行间一致性推断**——只有**非白底**实心块才强制 center。
16. **跨框左对齐组**——纵向邻接 + 左墨迹边一致 + 右端参差 → 整组锚同一 `x1`。
17. **水平定位用 `getmask().getbbox()`**——`getbbox` x0 恒 0。
18. **竖向三段式**——实心彩色居中；其余能放下（渲染高 ≤ 原文墨迹高）居中；放不下顶对齐向下生长。`anchors.vertical_mode` 供 C8 读取。
19. **强锚只钳图像边界**——居中 / 实心彩色 / 左对齐组 / 竖向居中。

### E. 交付

20. **全屏克隆禁止嵌套 `.qy-viewer-inner`**——兜底 `max-height: calc(100vh - 72px)`。
21. **收工前 QC**——C1–C6 + C7a/b + C8/C9/C10；`QYUNSLATION_IMAGE_QC_STRICT=1` 门禁。
22. **判据落 verify**——`scripts/verify-plan-026.sh`（回归 025）。

## QC 检查项

| 码 | 查什么 |
| --- | --- |
| C1/C2 | 覆盖率、绘制块数 |
| C3/C4 | 墨迹实测（优先 `draw_bbox` 小窗）、对比度 |
| C5/C6 | 溢出、可读性（WARN） |
| C7a/C7b | 组内字号、组间比例 |
| C8 | 成品 vs 计划锚点（读 `vertical_mode`） |
| C9 | 左对齐组 `x1` 参差 |
| C10 | 文字带外图元损伤（原非背景→成背景） |

## 新图接入自检清单

换一张图先跑完再改代码：

1. **OCR 引擎**：框数是否接近肉眼标签数？流程图必 RapidOCR。
2. **框与图元相交**：对每个 solid 框算 `_fill_band` 外非背景像素；>0 则必须靠带外回贴/guard，不能整框填。
3. **纯色判据**：抽查蓝底/白底 `solid` / `solid_colored` / `frac`。
4. **层级**：同色同排字号是否全等；组间 `k` 是否≈1。
5. **锚点行**：抽查蹭线框的 `_main_row` 是否避开线状行。
6. **竖向**：渲染块高 ≤ 原文时 `vertical_mode=center`；中心偏移 ≤3px。
7. **QC**：`issues` 无 C8/C9/C10；必要时开 `QC_STRICT=1`。

```python
from qyunslation.extensions.image_translate import ocr_image, _analyze_box_style, _fill_band
import cv2, numpy as np
img=cv2.imread(path)
for i,b in enumerate(ocr_image(path),1):
    roi=img[b[1]:b[3],b[0]:b[2]]; st=_analyze_box_style(roi)
    by1,by2=_fill_band(roi); bg=np.array(st["bg_bgr"],int)
    outside=np.ones(roi.shape[:2],bool); outside[by1:by2,:]=False
    n=int(((np.abs(roi.astype(int)-bg).max(2)>40)&outside).sum())
    if n>20: print(i,b[4][:24], "outside_gfx", n, "band", by1, by2)
```

## 文档内嵌图接入（PLAN-027）

单图流水线之上，DOCX/PDF 文档内插图走「实例优先」：

### 铁律（文档级）

23. **Occurrence-First**——以显示实例（DrawingML / 页面 xref+bbox）为主键，不以物理 part/xref 全局替换。
24. **共享资源先克隆**——同一 ImagePart / XObject 被多处引用时，只对目标实例克隆新资源并重定向；禁止直接改共享 blob/xref。
25. **Alpha / SMask 保真**——`_load_image_bgr_alpha` + `_save_with_alpha`；译文墨迹处强制不透明，其余恢复原 Alpha。
26. **几何用显示尺寸**——DOCX 读 `<wp:extent>`（EMU→pt）；PDF 用页面 bbox；禁止只看源像素。
27. **语种与数字门控**——`doc_image_policy.filter_translatable_texts`：纯数字/单位跳过；已是目标语种跳过。
28. **矢量覆盖 Fail-Closed**——`find_safe_vector_figures`：面积 >80% 页或与长正文重叠 >10% 或撞表格 → 放弃，**绝不退回整页**。
29. **预扫描代际锁**——`_prescan_generation` + per-file hash；过期 Tier-2 回调丢弃。
30. **HPD 回退用原稿**——PDF 插图前置后若报 Scanned PDF，HPD 必须吃 `_pre_imgtr_origin_path`。
31. **单图熔断**——超时/QC 失败保留原图；交付 `<stem>.imgtr.json`。
32. **依赖声明 = import 名**——`from rapidocr import RapidOCR` 必须对应 `rapidocr` 包（另显式声明 `onnxruntime`）；禁止靠 docling 传递依赖撑主链路。
33. **跨 venv 能力显式判定**——pdf2zh 进程无 RapidOCR 时，探针/嵌字必须走 sidecar；禁止本地静默弱回退。
34. **HPD 仅限扫描件整页**——流程图 / 设计图主路径必须 RapidOCR；HPD 把整图标成 `<BLOCK>image`。
35. **引擎降级必须可见**——`ocr_image_with_engine` 返回实际引擎名；`probe_image` / `/image-probe` 透传 `ocr_engine`；启动打印 `ocr_engine_status()`。
36. **回嵌目标 300 DPI**——按显示 pt 用 `ensure_display_dpi` 仅上采样；矢量 `VECTOR_CROP_DPI=300`、`VECTOR_MAX_PX≥4000`；不改 EMU/bbox。
37. **擦除后必须二次确认无原文残留**——扩框 + 加厚文字带；带外回贴避开文字 mask；`_clear_ocr_leftovers` 再扫一轮。

### 关键模块

| 模块 | 职责 |
| --- | --- |
| `doc_image_policy.py` | 几何/语种/数字判定（stdlib+PIL） |
| `docx_image_overlay.py` | DrawingML 枚举 + 克隆回填 |
| `pdf_figure_crop.py` / `pdf_image_translate.py` | 矢量安全聚类 + 位图/矢量双策略 |
| `doc_image_prescan.py` + `apply-pdf2zh-prescan.py` | Tier-1/2 预扫描 |
| `apply-pdf2zh-docimg.py` | PDF 前置嵌字补丁 |
| `/service/image-probe` | 纯 OCR 探针 |

验收：`scripts/verify-plan-027.sh`。

## 排障

| 现象 | 看 |
| --- | --- |
| 线上有白块/缺口 | `_fill_band` 是否整框填；C10；文字带外回贴 |
| 标签整体偏上 | 是否误用顶对齐；`vertical_mode` / 原文墨迹高 |
| 译文整体右移/下沉 | 可用区当排版框；C8 `plan_dx/plan_dy` |
| 单个标签比同排高 | `_main_row` 锚到线状行 |
| bullet 参差 | `_assign_left_groups` / C9 |
| 「·」行偏右 | `getbbox` vs `getmask` |
| 同级字号不一 | `_assign_tiers` / C7a |
| 蓝框涂抹 | solid 通道 std + frac |
| 全屏裁底 | 嵌套 `.qy-viewer-inner` |

详表见 [reference.md](reference.md)；踩坑见 [pitfalls.md](pitfalls.md)。
