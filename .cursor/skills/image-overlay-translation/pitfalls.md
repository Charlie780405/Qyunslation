# 踩坑（SK-Q002）

单一 SSOT；带来源。与 PLAN 正文不重复。

1. **HPD 把流程图标成整块 `image`** → 内部零 OCR，60 标签只出 2 脚注（PLAN-021）。正解：图片链路 RapidOCR，HPD 回退。
2. **`/no_think` 前缀无效** → qwen3.6 仍输出 thinking，`num_predict=2000` 耗尽后 `content=""`（PLAN-021）。正解：`think: false` API 参数。
3. **先全擦后 `trans.get` 条件画** → `trans` 空时净删字（PLAN-021）。正解：缺译不擦不画。
4. **`vals = vals[vals < 120]` 单侧取色** → 蓝底白字框对比度塌到 1，译文「看不见」（PLAN-022）。正解：Otsu 分层中位数 + 对比度兑底。
5. **纯色框用 TELEA inpaint** → 边缘涂抹成花纹（PLAN-022）。正解：边框 std `< 12` 时 `cv2.rectangle` 纯色填充。
6. **`QYUNSLATION_FONT` 指向 Thin TTF** → 嵌字偏细（PLAN-022）。正解：Regular.otf + Bold.otf，粗细从面积比推断。
7. **无条件左对齐** → 流程图标签偏左（PLAN-022）。正解：文字像素质心判 left/center/right。
8. **viewer `querySelectorAll('img, .prose')`** → `.prose > img` 双命中，全屏叠两张（PLAN-022）。正解：整容器 `cloneNode` + canvas 位图重绘。
9. **返回 `len(boxes)` 当绘制数** → 日志虚报（PLAN-021）。正解：返回实际 `drawn`。
10. **docx/custom_api 未传 `to_lang`** → 永远简体中文（PLAN-019/021）。正解：透传。
