# 踩坑（SK-Q002）

单一 SSOT；带来源。与 PLAN 正文不重复。

1. **HPD 把流程图标成整块 `image`** → 内部零 OCR，60 标签只出 2 脚注（PLAN-021）。正解：图片链路 RapidOCR，HPD 回退。
2. **`/no_think` 前缀无效** → qwen3.6 仍输出 thinking，`num_predict=2000` 耗尽后 `content=""`（PLAN-021）。正解：`think: false` API 参数。
3. **先全擦后 `trans.get` 条件画** → `trans` 空时净删字（PLAN-021）。正解：缺译不擦不画。
4. **`vals = vals[vals < 120]` 单侧取色** → 蓝底白字框对比度塌到 1，译文「看不见」（PLAN-022）。正解：Otsu 分层中位数 + 对比度兑底。
5. **纯色框用 TELEA inpaint** → 边缘涂抹成花纹（PLAN-022）。正解：纯色时 `cv2.rectangle` 填充。
6. **`QYUNSLATION_FONT` 指向 Thin TTF** → 嵌字偏细（PLAN-022）。正解：Regular.otf + Bold.otf，粗细从面积比推断。
7. **无条件左对齐** → 流程图标签偏左（PLAN-022）。曾用质心三分桶，密排图几乎全判 center 失效（PLAN-025 改行间一致性；实心强制 center）。
8. **viewer `querySelectorAll('img, .prose')`** → `.prose > img` 双命中，全屏叠两张（PLAN-022）。正解：整容器 `cloneNode` + canvas 位图重绘。
9. **返回 `len(boxes)` 当绘制数** → 日志虚报（PLAN-021）。正解：返回实际 `drawn`。
10. **docx/custom_api 未传 `to_lang`** → 永远简体中文（PLAN-019/021）。正解：透传。
11. **BGR 拍平求 std 判纯色** → 蓝底 `(154,95,33)` 通道间差把 std 抬到 ~50，全部误判非纯色走 inpaint，框内涂抹痕迹（PLAN-023）。正解：对内点 `np.std(..., axis=0).max()` 按通道。
12. **纯 std 阈值不抗边缘蹭线** → 右上「16周」OCR 框蹭到青色括号线，solid 翻车，inpaint 扩散成黑/青梯形（PLAN-023）。正解：边框内缩 2px 采样 + 通道内点 std + 贴近中位数占比 `>= 0.80`。
13. **循环内逐框 `cv2.inpaint` 整图** → 涂抹层层叠加放大痕迹（PLAN-023）。正解：非纯色累加 mask，全图只 inpaint 一次；非纯色优先邻域取色擦字。
14. **用 `getbbox` 墨迹高判能否放下** → 真实行高更大，「16 weeks」第二行掉出框外；底部英文缩成两行小字像丢失（PLAN-023）。正解：`font.getmetrics()` ascent+descent；排版用 `_available_box` 扩到碰邻居为止。
15. **框重叠 + 缺译不擦** → 邻框擦除矩形盖掉未译框原文，像素回不来（PLAN-023）。正解：擦前备份 `redraw=False` ROI，擦后回贴。
16. **无 QC / 无 basicConfig** → 「擦了没画」静默出货，journalctl 看不到嵌字日志（PLAN-023）。正解：`_qc_report` 六项 + sidecar `basicConfig`。
17. **全屏克隆嵌套 `.qy-viewer-inner`** → 中间层高度 auto，`max-height:100%` 退化，图片按宽铺满后底部被裁（访视轴/分层消失）（PLAN-024）。正解：搬子节点不嵌套；父级 `height:100%`；全屏 `max-height: calc(100vh - 72px)`。
18. **逐框独立二分字号** → 同蓝框两行、同组脚注大小不一（PLAN-024）。正解：背景色桶 + 白底 y 行带分档；组内统一；组间 `k × orig_em`。
19. **用墨迹高度分档** → `IGA` 拉丁 43 vs 汉字脚注 54 被当成两级（PLAN-024）。正解：反推渲染字号；组 orig_em 取 75 分位。
20. **把可用区当排版框居中** → 可用区向右/下不对称扩展后，译文相对原文统一右移 120–1125px、下沉 16–20px（PLAN-025）。正解：排版锚 `_ink_geometry` 主行墨迹；可用区只做换行宽。
21. **C8 在 avail∪ocr 上测墨迹** → 邻框文字把 dst cy 系统性拉偏 ~27px（PLAN-025）。正解：在 `draw_bbox` 小窗测成品 vs 计划锚点。
22. **主行按「最宽行」选** → 「16周」OCR 框蹭到贯穿全宽的青色括号线（`h=2 w=139`），最宽行选中那条线，锚点 cy 落 117 而非 151，整块比同排高约 30px（PLAN-025b）。正解：`_main_row` 先剔除线状行（宽高比 ≥ 8 且高 < 最高行 40%）。
23. **白底也算 solid 就强制居中** → 脚注 bullet「·IGA 3…」「·既往是否…」原文左边同为 201，译文长短不同后各自居中，两条错开百余像素（PLAN-025b）。正解：只有非白底实心块强制 center；白底走推断 + 跨框左对齐组。
24. **左对齐组只看左边一致** → W/V 刻度标签上下相邻且左边也一致，被误并成左对齐组（PLAN-025b）。正解：要求组内右端参差 ≥ 3×tol，等宽条目不成组。
25. **用 `font.getbbox()` 定位水平** → 它返回布局盒（x0 恒 0、x2 为步进宽），「·」或前导空格的左边距吃不到，整行右移 13px（PLAN-025b）。正解：`font.getmask(text).getbbox()` 取真实墨迹范围。
26. **纯色整 OCR 框 `rectangle` 填充** → 「16周」框顶蹭到青色括号线（`y=116-117`），整框白填把线抹成缺口；同图 #9/#18 框边色带也被邻框越界抹掉（PLAN-026）。正解：`_fill_band` 只填非线状文字行带；擦后回贴文字带外原图像素；贯穿线 `_line_guard_mask`；C10 守门。
27. **白底一律顶对齐** → 原文墨迹高 51、译文渲染高 30 时顶对齐使视觉中心统一上移 `(51-30)/2≈10.5px`，「16W」看起来偏上（PLAN-026）。正解：竖向三段式——能放下就居中于 `ink_cy`，放不下才顶对齐向下生长。

## 定位手法（PLAN-023/024/025/026）

- 逐框打印 `边框bg / 当前bg / solid / 通道std / frac`
- 对照跨通道拍平 std vs 按通道 max std
- 框重叠矩阵（IoU / cover_a / cover_b）
- 原图与译图同区域裁剪对比（顶栏 16周、蓝框、底部分层）
- 逐框打印 `ink / est_size / tier / assigned`（PLAN-024）
- 逐框打印 `ink_cx/cy vs avail_cx/cy` 与 `plan_dx/plan_dy / render dx/dy`（PLAN-025）
- qc.json `align[]`：`anchor_src` / `anchor_plan` / `anchor_dst` / `vertical_mode`
- 文字带外非背景像素计数 + 括号线行非白存活率（PLAN-026）
- qc.json `graphics_damage[]`（C10）
32. **`page.replace_image(xref)` 全局污染** → 页眉 Logo 与正文设计图共用 xref 时，一次替换全改（PLAN-027）。正解：多引用则逐实例 `insert_image` overlay，或先克隆资源。
33. **`package.iter_parts()` 当显示语义** → 取不到 EMU 尺寸/页眉身份，小 Logo 被翻或大图被漏（PLAN-027）。正解：DrawingML 枚举 `<wp:extent>` + occurrence 克隆。
34. **`cv2.imread` 丢 Alpha** → 透明 PNG 回嵌黑底（PLAN-027）。正解：`_load_image_bgr_alpha` / `_save_with_alpha`。
35. **Hermes `figure_clip` 退回整页** → 正文被压成位图（PLAN-027）。正解：面积>80% 或正文重叠>10% Fail-Closed，禁止整页回退。
36. **预扫描无代际锁** → 切换文件后旧 Tier-2 覆写 UI（PLAN-027）。正解：`_prescan_generation` + per-file hash。
37. **已是目标语种/纯数字仍送 LLM** → 幻觉或浪费（PLAN-027）。正解：`filter_translatable_texts`。
38. **HPD fallback 吃 `.imgtr.pdf`** → 已嵌字图被二次 OCR（PLAN-027）。正解：`_pre_imgtr_origin_path`。
39. **`rapidocr-onnxruntime` 声明但代码 `from rapidocr`** → 真正跑的是 docling 传递的 `rapidocr 3.x`；docling 一撤，OCR 静默退化（PLAN-027f）。正解：显式 `rapidocr>=3.6.0` + `onnxruntime`。
40. **RapidOCR 缺失仍本地 `probe_image`** → pdf2zh venv 无 rapidocr，同图 43→0 块，预扫描误报「无可译文字」（PLAN-027f）。正解：`has_local_ocr()` / sidecar；`ocr_engine` 字段暴露实际引擎。
41. **Gradio `.column` 默认 `flex-wrap:wrap`** → 长预览另起一列落到右邻栏，原文跑进「译文」（PLAN-027 热修）。正解：中右栏 `flex-wrap: nowrap`。
42. **源像素低于显示尺寸仍原样嵌字** → 回嵌拉伸发糊（PLAN-027g）。正解：`ensure_display_dpi` 升到 300 DPI；矢量默认 300/`MAX_PX=4000`。
43. **文字带外整段回贴原图** → OCR 框内带外的残画（`c`/`OL`）贴回，译文叠字（PLAN-027g）。正解：回贴避开文字 mask；擦后 `_clear_ocr_leftovers`。
44. **C3 在 avail∪ocr 大窗上用比例测墨迹** → 流程图短标签（如 `(n = 15)`）在高大白盒里比例低于 `QC_INK_MIN`，假空白记 `TRUNCATED`（PLAN-033k）。正解：优先 `draw_bbox` 小窗（与 C8 同口径）；无计划盒时改用绝对墨迹像素下限 `QC_INK_MIN_PX`。
45. **C6 用 OCR 框高且警告无 below** → 竖排阶段条全员假过小；`FONT_BELOW_TARGET` 写不进，450/600 DPI 重绘不触发（PLAN-033l）。正解：高盒用短边；按 C6 码映射。
46. **线保护把竖排字当贯穿竖线回贴** → `horiz_ink` 在无非文字候选时整词返回，擦完又贴回 Identification/Included，译文叠残影（PLAN-033）。正解：只保护扁的贯穿行；清残字后不再从原图回贴 guard；嵌字前按原文文字 mask 再擦残留。
47. **并排双语按中心点放行横跨框** → 图形摘要/摘要条 bbox 中心刚好 ≥ 0.5，整框 overlay 把左侧英文原文盖成中文（PLAN-033c / 2026-09-11）。正解：`_clip_rect_to_allowed` 裁到右半再 crop/insert；左侧 hash 不变。
48. **译后强制展开 Q2W/Q4W/IGA 0/1** → 「每2周一次（Q2W）」变成「每2周一次（每 2 周一次（Q2W））」，摘要行框撑爆，「目的」压进「背景」（PLAN-045a 热修）。正解：译后只校正伪译与短语；缩写不展开；literature `line_skip=1.25` + 框底裁切。
49. **矢量嵌字从译文页裁图** → BabelDOC 已改图内英文，OCR 吃糊字，双语左侧也被盖住；B/C 小字再乘 k 更小（2026-09-11 图形摘要）。正解：`origin=` 裁原稿；右侧 overlay；小字号档 `k=1` + `FIGURE_TIER_MIN_PX`。

29. **竖排轴标签被 OCR 切成近方形多框（PLAN-047f）** — `_is_rotated_axis_box` 的 `oh>=2*ow` 对单框不成立，旋转通道不触发，中文竖排重叠。正解：`_group_vertical_runs` 聚合后再旋转。
30. **PANEL 字母个体 k 导致 ABC 字号不一（PLAN-047f）** — 全图 panel 字母用 est 中位数统一落笔。
31. **左对齐组要求右缘参差（PLAN-047f）** — 图2 左列 B/C 两行等宽回落居中。正解：panel 内墨迹左缘成组即强制左对齐。
32. **擦除区译文覆盖不足仍擦（PLAN-047f）** — 背景脏。正解：覆盖率 ≥70% 才擦，否则不擦不画。
33. **sidecar 未加载导致 046d「已修」实未跑（PLAN-047）** — 见 SK-Q004。
