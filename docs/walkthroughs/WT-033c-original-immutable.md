# WT-033c 原文不可变（嵌图改译文后处理）

> 计划：[PLAN-033c](../plans/PLAN-033-pdf-fidelity/PLAN-033c-original-immutable.md)
> 日期：2026-09-09
> 验收门：`bash scripts/verify-plan-033c.sh` → `SUMMARY: PASS fail=0`

## 做了什么

原先 `apply-pdf2zh-docimg.py` 在 BabelDOC 之前把 `file_path` 换成 `.imgtr.pdf`，双语左侧因此带上嵌图译文。

两刀一起上：

1. 前置只记 `_pre_imgtr_origin_path`，不再 `file_path = _qy_new`。
2. `do_translate_async_stream` 之后对单语全文、并排双语右侧（`x_min_frac=0.5`）、交替页偶数页（`page_parity=even`）跑 `translate_pdf_images`。

`_pre_imgtr_origin_path` 仍留给 HPD 回退。只砍第一刀会让图回到未译，禁止单独上线。

## 验证

| # | 结果 |
| --- | --- |
| V1 补丁不再出现 `file_path = _qy_new` | 通过 |
| V2 已安装 GUI 有 `_qy_imgtr_post` / `x_min_frac`，stream 仍吃 `file_path` | 通过 |
| V3 合成双语页左侧渲染 hash 不变、右侧改变 | 通过 |
| V4 `_pre_imgtr_origin_path` 仍在 | 通过 |
| V5 `verify-plan-033a.sh` | 通过 |
| 相邻 `test_execution_parity` | 13 passed（`x_min_frac` 默认 None） |
| 重启 `pdf2zh.service` | `active`，22 条 ExecStartPre 均 status=0，无 ERROR；`:7860` 200 |

备份：`/home/dev/pdf2zh/gui.py.bak-plan033c-20260908T234059Z`。重启后后续补丁仍写过 `gui.py`，钩子还在：前置只记 `_pre_imgtr_origin_path`，`do_translate_async_stream` 仍吃 `file_path`，后置 `_qy_imgtr_post` + `x_min_frac`。

## 未做

033d / 033e 已接着做完。未把 Elsevier PDF 入库。已合 `main`（`f83c5ff`）并重启生产 `pdf2zh.service`。
