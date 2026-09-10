---
name: erase guard anchor
overview: 修复实心填充抹掉相邻图元、以及白底标签整体上移 10.5px 两个问题，并把 SK-Q002 从「本图修补记录」重构为带通用原则与新图自检清单的可迁移规范。
todos:
  - id: fill-band
    content: 新增 _fill_band：实心填充范围收敛到非线状文字行带，不再整框填充
    status: completed
  - id: line-guard
    content: 新增 _line_guard_mask：形态学提取贯穿性线条，填充/inpaint 前备份后回贴
    status: completed
  - id: vertical-anchor
    content: 竖向锚定改三段式（实心彩色居中 / 能放下居中 / 放不下顶对齐），anchors 记录实际模式并让 C8 读取
    status: completed
  - id: qc10
    content: QC 新增 C10 图元损伤检查，纳入 QC_STRICT 硬失败
    status: completed
  - id: verify
    content: 写 verify-plan-026.sh：括号线存活率、周数标签中心偏移、双向 QC、回归 025
    status: completed
  - id: skill
    content: SK-Q002 重构：新增通用原则与新图接入自检清单，同步 pitfalls/reference/registry
    status: completed
  - id: ship
    content: 精确 commit、no-ff 合 main、推两个远程、重启服务、回填 WT-026
    status: completed
isProject: false
---

# PLAN-026 擦除保护与竖向锚定复位

## 实测依据

- 括号线原在 `y=113-117`（每行 156 非白像素）；「16周」OCR 框起于 `y=116`，矩形填充后 `y=116/117` 只剩 17/15 像素。
- 全图 60 个 solid 框中，**3 个**（#5、#18、#9）在「文字带之外」仍有图元会被矩形填充抹掉，受损区都紧贴框的上/下边缘。
- 周数标签 #5/#6/#7/#8 原文墨迹高 51、渲染高 30，顶对齐使视觉中心统一上移 **10.5px**。

## 一、擦除保护（两层，均通用）

改 [qyunslation/extensions/image_translate.py](qyunslation/extensions/image_translate.py) 擦除段（当前 `if st["solid"]: cv2.rectangle(img_cv, (x1,y1),(x2,y2), st["bg_bgr"], -1)`）。

**第 1 层：填充范围收敛到文字带。** 复用已有的 `_ink_geometry` + 线状行判据（`RULE_ROW_RATIO` / `RULE_ROW_H_FRAC`），取非线状行的 `y` 包络 ±pad 作为填充矩形的纵向范围，横向仍用全框。新增 `_fill_band(roi)` 返回该范围；无文字行时回退整框。这样 `y=116-118` 的线状行天然落在填充区外。

**第 2 层：长线图元保护掩膜。** 新增 `_line_guard_mask(roi, bg_bgr)`：对「非背景且非文字」的像素做形态学开运算（`1×K` 横核与 `K×1` 竖核，`K ≈ 0.6×` 框宽/高），存活像素即贯穿性线条/色带。填充前备份这些像素、填充后回贴。这层挡的是第 1 层挡不住的情形——竖线或箭头杆穿过文字带。

两层都对非纯色分支同样生效（`inpaint_mask` 需扣掉 guard 掩膜，避免 inpaint 把线抹花）。

## 二、竖向锚定规则复位

现在按 `solid_colored` 二分（实心彩色块居中、其余顶对齐），把白底标签全部抬高了。改为可证明不越界的三段式：

- 实心彩色块：恒居中于原文 `ink_cy`（不变）
- 其余且 `渲染块高 <= 原文墨迹块高`：居中于 `ink_cy`——落在原 footprint 内，不可能撞到上一行
- 其余且 `渲染块高 > 原文墨迹块高`：首行顶对齐 `ink_y1` 向下生长（保持既有防撞语义）

把实际采用的竖向模式写进 `anchors[i]`，C8 的 `vertical_center` 改读它，否则计划锚点与渲染口径会不一致。

## 三、QC 新增 C10（图元损伤）

在 `_qc_report` 增加：对每个重绘框，取 `OCR 框 − (文字带 ∪ draw_bbox)` 区域，统计「原图非背景（diff>40）但成品变成背景（diff<=15）」的像素数，超阈值即 C10 失败。纳入 `QC_STRICT` 硬失败集合（与 C8/C9 同级）。

## 四、验收 [scripts/verify-plan-026.sh](scripts/verify-plan-026.sh)

沿用 025 结构，新增断言：

- 括号线 `y=116-117, x=3160..3320` 成品非白像素 >= 原图的 90%
- #5/#6/#7/#8 的 `|原文 ink_cy − draw_bbox cy| <= 3`（回归前是 10.5）
- QC 无 C8/C9/C10；中→英、英→中双向全绿
- 回归 `verify-plan-025.sh`

## 五、Skill 全面梳理（SK-Q002）

用户要求「未来其它图片充分考虑类似情况」，所以 [SKILL.md](.cursor/skills/image-overlay-translation/SKILL.md) 从修补记录重构为可迁移规范，新增两节：

**通用原则**（置于具体铁律之前，每条具体铁律标注其归属）：

1. OCR 框不是文字范围——框会蹭到邻近图元；擦除、对齐、字号一切基于框的操作，先收敛到墨迹几何
2. 破坏性操作先建保护掩膜——填充/inpaint 前必须回答「框内哪些像素不属于本框的文字」
3. 度量前先确认口径——布局盒 / 墨迹盒 / 行盒不可混用（已有对照表上提到此节）
4. 版式变换必须可证明不越界——能放下就保中心，放不下才单向生长

**新图片接入自检清单**：OCR 引擎选择、框与图元的相交检查、纯色判据复核、层级分档抽样、锚点行抽样、QC 全码通过——每项给出可直接跑的一行度量代码。

同步更新 [pitfalls.md](.cursor/skills/image-overlay-translation/pitfalls.md)（新增矩形填充吃图元、顶对齐抬高两条）、[reference.md](.cursor/skills/image-overlay-translation/reference.md)（新 ENV、C10、竖向锚定三段式对照）、[registry.md](.cursor/skills/skill-registry/registry.md)。

## 六、交付

feat 分支 → 精确 commit → `--no-ff` 合 main → 推 qyunslation 与 mirror → 重启 `qyunslation-office.service` → 回填 [WT-026](docs/walkthroughs/WT-026-erase-guard.md)。