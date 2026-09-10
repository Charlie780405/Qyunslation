# PLAN-030j：栏式判定债 D1–D5

> 状态：**待批准**（纲领已写，未编码）
> 父计划：[PLAN-030](./PLAN-030-semantic-layout-translation.md)
> 前置：030h 已完成并登记五处债
> 阻塞：030i（UI/可观测/Checkpoint D）不得在本计划未清 D1–D5 前实施
> 验收门：`bash scripts/verify-plan-030j.sh`（待 030j 编码后创建）

## 目标

修复 [PLAN-030h](./PLAN-030h-cross-format-fidelity.md)「发现的债」，使 `LayoutMode.MULTI`、`POSTER_SECTION`、阅读顺序与 `content_profile` 契约与实现一致。摘除 030h 故意锁缺陷的测试。

## 债与实施顺序

| 阶段 | 编号 | 交付 | 关键文件 |
| --- | --- | --- | --- |
| 1 | D4 | A0 海报识别为 FREEFORM/POSTER，九分区不串成双栏正文 | `qyunslation/structure/layout.py` |
| 2 | D1/D2 | 三/四栏产出 MULTI；中栏不吞进左栏 | 同上 + `scan_pdf.py` 阅读顺序 |
| 3 | D3 | 少块双栏不短路 SINGLE | `layout.py` |
| 4 | D5 | `content_profile` 与容器解耦（可用户覆盖） | `scan_*.py`、`profiles.py` |

## Out of Scope

- 030i UI/manifest 下载（另立 030i）
- 030-table Camelot 选型（未过 Task 0）
- 033 学术 PDF 终态、BabelDOC 补丁制度化（随 030i Checkpoint D）

## 验证清单（编码后）

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/structure/test_layout_gold_samples.py` | 原 xfail/锁缺陷测试转 PASS |
| V2 | `verify-plan-030h.sh` | 仍 PASS（回归） |
| V3 | Nature/ljae439 双栏断言 | 不退化 |

## 批准门

用户确认本纲领后再开 `feat/PLAN-030j-layout-debt` 并改 `layout.py`。
