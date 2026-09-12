# PLAN-033c：原文不可变

> 状态：**已完成**（`verify-plan-033c.sh` PASS）
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 前置：033a
> 验收门：`bash scripts/verify-plan-033c.sh`

## 根因

`scripts/apply-pdf2zh-docimg.py` 在 BabelDOC 之前把 `file_path` 换成 `.imgtr.pdf`：

```
if _qy_new and _qy_Pimg(_qy_new).is_file():
    file_path = _qy_new
```

双语左侧因此带上嵌图译文。`_pre_imgtr_origin_path` 只给 HPD 回退用，BabelDOC 本体仍吃 imgtr。

## 做法（两刀，不可只砍第一刀）

1. **停止替换输入**：BabelDOC 始终吃原始 `file_path`。`_pre_imgtr_origin_path` 继续保留。
2. **译文后处理**：`do_translate_async_stream` 结束后，对**单语 PDF** 和**双语右侧页**跑 `translate_pdf_images`。禁止写回作为下次 BabelDOC 输入的那份文件。
3. **横跨框须裁切**：并排双语页上 `translatable_regions` 常给出盖住左右两栏的矢量框；只按中心点 `>= 0.5` 会把译文图盖到原文。`_clip_rect_to_allowed` 把 crop/overlay 裁到右半页。

只做第 1 刀会让图回到未译，算回归，禁止单独上线。

## 不改

- 扫描器、题注、表格提取器、030h D1–D5、预览 DPI。

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | 补丁源码不再出现 `file_path = _qy_new` | 通过 |
| V2 | 已安装 `gui.py` 的 `do_translate_async_stream` 实参仍是 `file_path`，且有 `_qy_imgtr_post` | 通过 |
| V3 | 合成双语页：`x_min_frac=0.5` 后左侧渲染 hash 与处理前一致，右侧改变 | 通过 |
| V4 | `_pre_imgtr_origin_path` 仍在（027 HPD 回退） | 通过 |
| V5 | `verify-plan-033a.sh` 仍绿 | 通过 |
