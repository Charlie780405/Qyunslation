---
name: overlay QC gate
overview: 修掉图片嵌字的遮罩涂抹、换行溢出与长英文被压小三类瑕疵，并在保存前加一道六项 QC 关卡，最后把根因与铁律沉淀进 SK-Q002。
todos:
  - id: solid
    content: _analyze_box_style 改按通道 std + 贴近中位数占比双条件判纯色，solid 时 bg 取边框中位数，返回 border_bgr
    status: completed
  - id: erase
    content: 擦除改两趟：纯色 rectangle 填充，非纯色累加 mask 后全图一次性 inpaint；未翻译框原始 ROI 备份回贴
    status: completed
  - id: avail
    content: 新增 _available_box：从 OCR 框向外扩到碰邻框或非背景像素为止，擦除用原框、排版用可用区域
    status: completed
  - id: fit
    content: _fit_font_and_lines 行高改用 font.getmetrics()，max_size 上限提到 72，换行行数按可用高封顶；_font_bold 补 is_file 守卫
    status: completed
  - id: qc
    content: 新增 _qc_report 六项断言（覆盖/绘制/墨迹实测/对比度/溢出/可读性），落 qc.json，STRICT 模式抛错；sidecar 补 logging.basicConfig
    status: completed
  - id: skill
    content: SK-Q002 SKILL.md 补六条铁律，pitfalls.md 记录本次三现象与定位手法
    status: completed
  - id: verify
    content: verify-plan-023.sh 断言 + 参考图双向端到端 QC 全绿 + solid 命中率 55/60 以上，回归 017-022，浏览器实测三项
    status: completed
  - id: ship
    content: PLAN-023 与 WT-023，精确 commit、no-ff 合 main、推两个远程、重启两个服务，registry 登记 SK-Q002
    status: completed
isProject: false
---

# PLAN-023 图片嵌字遮罩修正与 QC 关卡

## 已定位的根因（均有实测证据）

**R1 纯色判据把彩色底全判成非纯色。** [image_translate.py:369](qyunslation/extensions/image_translate.py) 的 `float(np.std(border.astype(np.float32))) < SOLID_STD_MAX` 把 BGR 三通道拍平在一起求标准差。蓝底 `(154,95,33)` 光是通道之间的差距标准差就有约 50，远超阈值 12。诊断显示 #9/#10/#11/#13/#14/#16 这些框的 `边框bg` 与 `当前bg` 完全相等（底色绝对均匀），却全部 `solid=False` 走了 `cv2.inpaint`。只有白底能通过。这就是"用非背景色涂抹遮罩的痕迹"。

**R2 右上角"16周"的黑框是同一判据被括号线污染。** `#5 [3168,116,3308,186] solid=False`，而同排的 #6/#7/#8 都是 `solid=True`；#5 上边缘蹭到深青色括号线，几个像素就翻了结论，inpaint 把青色向内扩散成梯形色块。

**R3 inpaint 在循环里逐框对整张 4353x2132 图重算并覆盖 `img_cv`**，涂抹层层叠加，放大了 R1/R2 的痕迹。

**R4 换行判据用墨迹高，实际渲染会溢出。** `_fit_font_and_lines` 用 `_text_size`（即 `getbbox` 的 `bbox[3]-bbox[1]`，不含上下留白）算 `line_h`，判定 `total_h <= box_h` 通过，但真实行高更大。实测 #1/#2/#3/#4/#5/#6/#7/#8/#57 全部被拆成两行，"16 weeks" 的 `weeks` 明显掉到框外。

**R5 排版边界只用 OCR 框，长英文被压小。** OCR 框按中文紧凑宽度切，英文长约一倍。`分层因素：` 框宽仅 250px（右侧空了近 1000px），英文只能缩成两行小字——在缩略预览里就像消失了。另外 `max_size = max(12, min(int(box_h*0.9), 40))` 还有一个 40px 硬上限。

**R6 没有 QC 关卡，且日志根本看不到。** `translate_image` 只有 `logger.info`，sidecar 未配 `logging.basicConfig`，`journalctl` 里 grep 不到任何 `translate_image:` 行。

**R7 `_font_bold()` 缺 `is_file()` 守卫**，regular 在 [image_translate.py:551](qyunslation/extensions/image_translate.py) 有守卫，bold 没有；字体缺失时 `ImageFont.truetype` 直接抛错。

**R8 框重叠会抹掉未翻译框的原文。** 实测存在 4 对重叠（`#9 x #10` 互相覆盖 13%/23%，`#17 x #18` 各 23%）。擦除循环只按 `redraw` 擦，未翻译的框既不擦也不画，但它的原文像素可能落在邻框的擦除矩形内，被填掉后永远补不回来。

## 目标流程

```mermaid
flowchart TD
  ocr[RapidOCR 取框] --> tr[LLM 批量翻译]
  tr --> style["_analyze_box_style 按通道判色"]
  style --> avail["_available_box 向外扩到碰邻居为止"]
  avail --> erase["纯色 rectangle 填充<br/>非纯色累加 mask"]
  erase --> once["全图一次性 inpaint"]
  once --> restore["回贴未翻译框的原始像素"]
  restore --> draw["按可用区域排版绘制"]
  draw --> qc["_qc_report 六项断言"]
  qc --> save[保存]
```

## 改动清单

### 1. `qyunslation/extensions/image_translate.py` — 颜色与遮罩

- `_analyze_box_style`：`solid` 改为两个条件同时成立——按通道 `np.std(border, axis=0).max() < SOLID_STD_MAX`，且边框像素贴近中位数的比例 `>= SOLID_FRAC_MIN`（新增环境变量，默认 0.80）。后者容忍括号线这类少量污染，直接修掉 R2。
- `solid` 时 `bg_bgr` 取边框中位数（抗文字污染），非 solid 才回退 Otsu 背景类中位数；返回值增加 `border_bgr` 供 QC 用。
- 擦除阶段改为两趟：纯色框逐个 `cv2.rectangle` 填 `bg_bgr`；非纯色框只往一张 `inpaint_mask` 上累加，循环结束后**只调一次** `cv2.inpaint`（修 R3）。
- 擦除前先备份所有 `redraw=False` 框的原始 ROI，擦完后回贴（修 R8）。

### 2. `image_translate.py` — 排版

- 新增 `_available_box(box, all_boxes, img, bg_bgr)`：从 OCR 框四向扩展，遇到其他 OCR 框的矩形、或与 `bg_bgr` 差异超阈值的连续行/列即停；横向上限为原框宽 3 倍、纵向 1.6 倍。**擦除仍用原 OCR 框，排版用可用区域**。
- `_fit_font_and_lines`：行高改用 `font.getmetrics()` 的 `ascent + descent`，不再用墨迹 bbox（修 R4）；`max_size` 上限由 40 提到 `min(int(avail_h * 0.9), 72)`；换行行数上限 `avail_h // line_h`；返回值带上 `size` 与 `line_h` 供 QC。
- `_font_bold()` 补 `is_file()` 守卫（修 R7）。

### 3. `image_translate.py` — QC 关卡

在 `result.save(out_path)` 之前调用新增的 `_qc_report(...)`，六项：

- C1 覆盖：`len(trans) == len(boxes)`，列出未翻译框号与原文
- C2 绘制：`drawn == sum(redraw)`
- C3 墨迹实测：把最终图与"只擦未写"的中间图逐框比对，框内变化像素占比需 `> 0.5%`，否则判为 BLANK（这是唯一能真正抓到"擦了没画"的检查）
- C4 对比度：每框 `contrast >= CONTRAST_MIN`
- C5 溢出：每行 `tw <= avail_w` 且 `total_h <= avail_h`
- C6 可读性：`size >= 0.6 * 原文墨迹高`，低于则 WARN（用于发现天生塞不下的图）

结果写 `logger.warning` 并落一份 `<out>.qc.json`；`QYUNSLATION_IMAGE_QC_STRICT=1` 时 C1/C2/C3/C4 任一失败直接抛错。同时在 office sidecar 入口补 `logging.basicConfig`，否则这些日志在 `journalctl` 里依然看不见。

### 4. Skill 沉淀 SK-Q002

`.cursor/skills/image-overlay-translation/SKILL.md` 新增铁律（保持 200 行内）：

- 颜色判据一律按通道算，禁止把 BGR 拍平求 std
- 纯色判定用"贴近中位数占比"，纯 std 会被边缘蹭线翻车
- `inpaint` 全图只做一次，禁止循环内重算
- 擦除按 OCR 框、排版按可用区域；未翻译框的像素必须回贴
- 行高用 `font.getmetrics()`，禁止用 `getbbox` 墨迹高判断能否放下
- 收工前必须跑 QC 六项，`QYUNSLATION_IMAGE_QC_STRICT=1` 为发布门禁

`pitfalls.md` 记录本次三个现象（彩色框涂抹痕迹 / 16周青色梯形 / 底部英文压成两行小字）与定位手法（逐框打印 `边框bg vs 当前bg vs solid`、跨通道 std 对照、框重叠矩阵、原图与译图同区域裁剪对比）。

### 5. 验收与交付

- 新增 `scripts/verify-plan-023.sh`：断言按通道 std、`SOLID_FRAC_MIN`、单次 inpaint、`getmetrics`、`_available_box`、`_qc_report`、`_font_bold` 守卫；对参考图 `方案设计图-20260728.jpg` 跑中译英与英译中双向端到端，要求 QC 六项全绿、`solid` 命中数从当前 8/60 提升到 55/60 以上；回归 017–022。
- 浏览器实测三项：右上角"16周"无色块、蓝框无涂抹痕迹、底部"Stratification factors:" 单行大字不溢出。
- `docs/plans/PLAN-023-overlay-qc/PLAN-023-overlay-qc.md` 与 `docs/walkthroughs/WT-023-overlay-qc.md`，精确 commit，`--no-ff` 合入 main，推 `mirror` 与 `qyunslation`，重启 `pdf2zh.service` 与 `qyunslation-office.service`。
- `registry.md` 补 SK-Q002 审计行，跑 `verify-skill-registry.sh` 与 `sync-cursor-skills.sh`。

## 风险

`_available_box` 向外扩展可能在密集排版的图上扩不动（退化为原框行为，安全），也可能在背景判定不准时扩过头压到邻居——由 C5 溢出检查与"遇到其他 OCR 框即停"两道约束兜底。扩展上限（横向 3 倍、纵向 1.6 倍）走环境变量，便于按图调。