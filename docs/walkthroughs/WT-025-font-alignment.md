# WT-025 译文对齐锚定原图墨迹

## 做了什么

- [`qyunslation/extensions/image_translate.py`](../../qyunslation/extensions/image_translate.py)：`_ink_geometry` / `_infer_align`、主行墨迹锚点渲染、C8、`ALIGN_TOL_PX`
- SK-Q002：铁律改为墨迹锚点；pitfalls #20/#21；reference 对齐表
- [`scripts/verify-plan-025.sh`](../../scripts/verify-plan-025.sh)

## 验证

```bash
bash scripts/verify-plan-025.sh   # PASS=18 FAIL=0
```

期望：C8 全绿；期标题 `plan_dx/plan_dy≈0`；W12–W52 竖向方差 ≤2px。

## 部署

- HEAD：`51e3241`（merge PLAN-025）
- 已推：`qyunslation`、`mirror`（`origin`/docutranslate 403，与既往一致）
- 服务：`systemctl --user restart qyunslation-office.service pdf2zh.service`

## 追加修订（PLAN-025b）

用户反馈「16weeks 和 Prior treatment 没有完全对齐」，定位到三个独立成因：

1. **锚点选到线状行**。「16周」的 OCR 框蹭到贯穿全宽的青色括号线（墨迹行 `h=2 w=139`），
   `_main_row` 按「最宽行」把它选成锚点，整块比同排周数标签高约 30px。
   现按宽高比 ≥ 8 且高度 < 最高行 40% 剔除线状行，锚点从 `y=117` 回到真文字行 `y=126`。
2. **白底被当实心块强制居中**。脚注两条 bullet 原文左缘同为 `x=201`，译文长短不同后各自居中，
   彼此错开百余像素。现只有非白底实心块强制 center；白底走行间一致性推断，
   并新增 `_assign_left_groups`：纵向邻接 + 左墨迹边一致 + 右端明显参差 → 整组锚同一 `x1`。
   等宽刻度标签（W24/V10 之类）因右端不参差而不成组，避免误判。
3. **水平定位口径错**。`font.getbbox()` 返回布局盒（x0 恒 0），拿不到左边距，
   「·」开头的行整体右移 13px。改用 `font.getmask(text).getbbox()` 取真实墨迹范围。

新增 QC **C9**：左对齐组成品 `x1` 参差超 `ALIGN_TOL_PX` 即失败。

验收：`verify-plan-025.sh` PASS=28 FAIL=0，中→英与英→中 QC 全绿，最大渲染偏移 1px。

部署：main `e7f71e1`，重启 `qyunslation-office.service`，`https://translate.qyunsgen.com/` 返回 200。

## 已知边界

超长英文贴图像左缘时（如「分层因素」→ Stratification factors）会水平 clamp，`plan_dx` 可 > tol，C8 仍以计划锚点为准。
