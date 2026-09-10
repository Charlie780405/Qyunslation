# PLAN-033n：当前 HEAD 终态证据重绑

> 状态：**已完成**（HEAD `76c75cf`，`inspect_final fail=[]`）
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 分支：`feat/PLAN-033n-head-evidence-rebind`
> 验收门：`bash scripts/verify-plan-033n.sh`
> 前置：033m 已交付 HEAD 绑定契约；033m 证据仅对旧 HEAD `55ccbbb` 成立

## 目标

对**当前** `git rev-parse --short HEAD` 重跑 11 页样本全链路（BabelDOC → imgtr → tbltr），产物写入 `/tmp/plan033m-<HEAD>/`，使 `verify-plan-033l.sh` 与 `verify-plan-033.sh` 不再因缺产物而 BLOCKED。通过后 PLAN-033 可诚实标为关闭。

## 上一子计划缺口分析

| 缺口 | 来源 | 归并 |
| --- | --- | --- |
| 文档写「已关闭」但当前 HEAD 无绑定产物 | WT-033m + 总门 BLOCKED | **本计划** |
| 033m 证据绑 `55ccbbb`，`76c75cf` 仅 docs-only | git log | **本计划**重跑 |
| `cap_body_gap`、续页金样、Figure 像素残影 | WT-033m「未做/弱项」 | **不归并**（033 范围外或已降级 WARN） |

## Out of Scope

- 新翻译算法、Camelot、030h D1–D5
- 样本入库、改 `glossaries/auto-proper-nouns.csv`
- 开 PLAN-034 或 030j 编码（030j 仅写纲领）

## 实现边界

改：

- `scripts/rerun-plan033-head-evidence.sh`（HEAD 绑定重跑 SSOT）
- `scripts/verify-plan-033n.sh`
- 父纲领状态句、本 WT

不改：

- `plan033_final.py` 断言（除非重跑暴露真实回归）

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `bash scripts/rerun-plan033-head-evidence.sh` | exit=0；`/tmp/plan033m-<HEAD>/` 含 `*.mono.imgtr.tbltr.pdf` |
| V2 | `bash scripts/verify-plan-033l.sh` | PASS 或诚实 FAIL（非 BLOCKED 缺产物） |
| V3 | `bash scripts/verify-plan-033.sh` | PASS |
| V4 | `inspect_final` `fail=[]` | 通过则更新父纲领为「已关闭 @ 当前 HEAD」 |

## 回滚

删除 `/tmp/plan033m-<HEAD>/`；不影响生产服务。033 状态句回退为「033m 已部署，当前 HEAD 待重绑」。
