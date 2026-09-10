# PLAN-030j：栏式判定债 D1–D5

> 状态：**已完成**（030ja–030jd；D1–D5 已清，可开 030i）
> 父计划：[PLAN-030](./PLAN-030-semantic-layout-translation.md)
> 前置：030h 已完成并登记五处债
> 后续：[PLAN-030i](./PLAN-030i-delivery-closure.md)（纲领待批）
> 验收门：`bash scripts/verify-plan-030j.sh`
> 批准记录：用户于 2026-09-10 批准 PLAN-030j 并开 D4 编码

## 目标

修复 [PLAN-030h](./PLAN-030h-cross-format-fidelity.md)「发现的债」，使 `LayoutMode.MULTI`、`POSTER_SECTION`、阅读顺序与 `content_profile` 契约与实现一致。摘除 030h 故意锁缺陷的测试。

## 债与实施顺序

| 阶段 | 编号 | 交付 | 关键文件 |
| --- | --- | --- | --- |
| 1 | [D4](./PLAN-030ja-poster-freeform.md) | A0 海报识别为 FREEFORM，九分区不串成双栏正文 | `layout.py`（**已完成**） |
| 2 | [D1/D2](./PLAN-030jb-multi-column.md) | 三/四栏 MULTI；中栏 `middle` | `layout.py`（**已完成**） |
| 3 | [D3](./PLAN-030jc-few-block-double.md) | 少块双栏判 DOUBLE | `layout.py`（**已完成**） |
| 4 | [D5](./PLAN-030jd-profile-decouple.md) | 画像按语义推断 | `profiles.py`、`scan_pdf/docx`（**已完成**） |

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
