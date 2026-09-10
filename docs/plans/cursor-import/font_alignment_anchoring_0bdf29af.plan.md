---
name: font alignment anchoring
overview: 译文横竖位置改为锚定原图文字墨迹几何（而非 PLAN-023 扩展出的可用区），可用区退回只当溢出余量，并加 QC C8 对齐检查与 skill 铁律。
todos:
  - id: ink_geom
    content: 新增 _ink_geometry：基于 Otsu 文字掩膜返回整体 ink bbox 与按 y 投影切行的每行 x1/cx/x2
    status: completed
  - id: infer_align
    content: 新增 _infer_align：比较各行 x1/cx/x2 标准差取最小者定对齐，取代质心三分桶
    status: completed
  - id: anchor_x
    content: 横向锚点：left/center/right 分别对齐 ink_x1/ink_cx/ink_x2，不再用 ax1/ax2
    status: completed
  - id: anchor_y
    content: 竖向锚点：solid 框块 ink 垂直中心对 ink_cy，非 solid 首行 ink 顶对 ink_y1 向下生长
    status: completed
  - id: clamp
    content: 锚定后整块最小平移 clamp 进可用区，可用区退回只做换行宽度与溢出余量
    status: completed
  - id: qc_c8
    content: _qc_report 新增 C8：成品图重测锚点与原图比 dx/dy，超 ALIGN_TOL_PX 记 issue 并写 qc.json
    status: completed
  - id: skill
    content: SKILL.md 补排版基准与对齐推断铁律，pitfalls.md 记两条现象，reference.md 补 ALIGN_TOL_PX 与实测表
    status: completed
  - id: verify
    content: verify-plan-025.sh 断言 + 参考图中英互译端到端（全部框 |dx|,|dy| ≤ 8），回归 017-024
    status: completed
  - id: ship
    content: PLAN-025 与 WT-025、registry 审计行，精确 commit、no-ff 合 main、推两个远程、重启两个服务
    status: completed
isProject: false
---

# PLAN-025 译文对齐锚定原图墨迹

## 根因

渲染时把**可用区**当成了排版框，而可用区最宽可扩到原框 3 倍（`AVAIL_W_MULT = 3.0`），且 `st["align"]` 是在 OCR 框里算完拿到可用区上用的，基准前后不一致：

```1196:1206:/home/dev/qyunslation/qyunslation/extensions/image_translate.py
        y = ay1 + max(0, (box_h - total_h) // 2)
        fill = _bgr_to_rgb(st["fg_bgr"])
        min_contrast = min(min_contrast, float(st["contrast"]))
        for ln in lines:
            tw, _ = _text_size(font, ln)
            if st["align"] == "center":
                x = ax1 + max(0, (box_w - tw) // 2)
            elif st["align"] == "right":
                x = max(ax1, ax2 - tw)
            else:
                x = ax1
```

参考图实测 60 个框里 50 个偏移超 12px，两种规律：

- 竖向：几乎全部统一下沉 16–20px（可用区向下扩，居中后整体下移）
- 横向：12 个框右移 120–1125px（可用区向右吃进空白，`·既往是否接受过AD生物制剂治疗` 偏 1125px，`主要终点：EASI-75` 偏 460px，四个期标题各偏 182px）

另外 `_analyze_box_style` 的 align 三分桶（质心 vs 框中心，阈值 0.12）在参考图上 60 个框判出 58 个 center，等于没判。

锚定原图墨迹在两类框上都对：实测 `#20 安慰剂` 的原文墨迹中心与蓝色实心矩形中心差 (0, 0)，即原图设计本就是"文字在实心块内居中"，锚墨迹中心自然复现；期标题、脚注等自由文字锚墨迹也直接复位。

## 改法

### R1 原文墨迹几何 —— [qyunslation/extensions/image_translate.py](qyunslation/extensions/image_translate.py)

新增 `_ink_geometry(roi)`，基于已有 `_text_mask_u8` 的 Otsu 文字掩膜返回：整体 ink bbox、按 y 投影空行切出的每行 ink 的 `x1/cx/x2` 与首行 ink 顶、末行 ink 底。

### R2 对齐判定改为行间一致性

新增 `_infer_align(rows)` 取代质心三分桶：多行时比较各行 `x1`/`cx`/`x2` 三组的标准差，最小者即为原文对齐方式；单行时取 center（对单行而言"中心对齐到原墨迹中心"等价于原样复位，最稳）。`_analyze_box_style` 保留 `align` 键名以兼容 qc.json。

### R3 锚点渲染

把 `ax1/ay1` 排版基准换成墨迹锚点，`avails[i]` 退回只做换行宽度与溢出余量：

- 横向：`left → 行左边缘对齐 ink_x1`；`center → 行中心对齐 ink_cx`；`right → 行右边缘对齐 ink_x2`
- 竖向（按已确认的分情况策略）：`st["solid"] → 整块 ink 垂直中心对齐 ink_cy`；非 solid → 首行 ink 顶对齐 ink_y1，向下生长
- 块 ink 高按 `(n-1)*(lh+gap) + 末行墨迹高` 计算，不用 line box 高，避免 ascent/descent 空白引入偏移（现有 `d.text((x, y - top))` 已按 ink 顶定位，保持一致）
- 锚定后整块做**最小平移** clamp 进可用区，保证不出界、不压邻框

### R4 QC C8 对齐 —— `_qc_report`

对每个 `redraw` 框在成品图上重测墨迹锚点，与原图锚点比 `|dx|`、`|dy|`，超 `ALIGN_TOL_PX`（新增 ENV，默认 8）记 issue，写入 `.qc.json` 各框 `anchor_src/anchor_dst/dx/dy`；strict 模式下失败。

## 文档与验收

- [.cursor/skills/image-overlay-translation/SKILL.md](.cursor/skills/image-overlay-translation/SKILL.md) 补铁律：排版基准必须是原文墨迹几何，可用区只做溢出余量；对齐方式从行间一致性推断，不用质心对框中心
- [pitfalls.md](.cursor/skills/image-overlay-translation/pitfalls.md) 记两条：可用区当排版框导致的统一下沉与右移；质心三分桶在密排图上全判 center 失效
- [reference.md](.cursor/skills/image-overlay-translation/reference.md) 补 `ALIGN_TOL_PX` 与偏移实测表
- [scripts/verify-plan-025.sh](scripts/verify-plan-025.sh)：断言 `_ink_geometry`/`_infer_align`/`C8`/`ALIGN_TOL_PX` 存在；端到端参考图中英互译，断言全部框 `|dx| <= 8 且 |dy| <= 8`、W12–W52 一行 12 个框竖向锚点方差 ≤ 2px、QC 全绿；回归 PLAN-017 至 PLAN-024
- [docs/plans/PLAN-025-font-alignment/PLAN-025-font-alignment.md](docs/plans/PLAN-025-font-alignment/PLAN-025-font-alignment.md) 与 [docs/walkthroughs/WT-025-font-alignment.md](docs/walkthroughs/WT-025-font-alignment.md)，[registry.md](.cursor/skills/skill-registry/registry.md) 补审计行
- 精确 commit、no-ff 合 main、推两个远程、重启 `pdf2zh.service` 与 `qyunslation-office.service`