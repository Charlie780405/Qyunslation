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

## 定位手法（PLAN-023/024/025）

- 逐框打印 `边框bg / 当前bg / solid / 通道std / frac`
- 对照跨通道拍平 std vs 按通道 max std
- 框重叠矩阵（IoU / cover_a / cover_b）
- 原图与译图同区域裁剪对比（顶栏 16周、蓝框、底部分层）
- 逐框打印 `ink / est_size / tier / assigned`（PLAN-024）
- 逐框打印 `ink_cx/cy vs avail_cx/cy` 与 `plan_dx/plan_dy / render dx/dy`（PLAN-025）
- qc.json `align[]`：`anchor_src` / `anchor_plan` / `anchor_dst`
