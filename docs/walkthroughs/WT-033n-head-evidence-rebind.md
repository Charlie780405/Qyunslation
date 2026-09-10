# WT-033n 当前 HEAD 终态证据重绑

> 计划：[PLAN-033n](../plans/PLAN-033-pdf-fidelity/PLAN-033n-head-evidence-rebind.md)
> 分支：`feat/PLAN-033n-head-evidence-rebind`
> HEAD：`76c75cf`
> 日期：2026-09-10
> 结论：**033 可诚实关闭。** `inspect_final` `fail=[]`；033n/033l/033 总门 PASS。

## 产物

目录：`/tmp/plan033m-76c75cf/`（`HEAD` 文件 = `76c75cf`）

| 文件 | 用途 |
| --- | --- |
| `*.mono.imgtr.tbltr.pdf` / `*.dual.imgtr.tbltr.pdf` | 终态 PDF |
| `033n-inspect.json` | `inspect_final` 快照 |
| `table-zh-cache.json` | 单元格译文缓存 |
| `run.log` / `post.log` | BabelDOC + 后处理日志 |

样本：`/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf`（不入库）

模型：`qwen3.6:35b-a3b` @ `http://100.67.66.123:11434/v1`

## 门禁

| 门禁 | 结果 |
| --- | --- |
| `rerun-plan033-head-evidence.sh` | BabelDOC exit=0；后处理 exit=0（修复 office.env 含空格值的安全加载） |
| `verify-plan-033n.sh` | PASS |
| `verify-plan-033l.sh` | PASS |
| `verify-plan-033.sh` | PASS（含 033n + structure suite） |

## 遗留与下阶段输入

- **033 关闭**：当前 HEAD 证据已绑定，不再「文档已关、总门 BLOCKED」。
- **030 未关**：下一门 [PLAN-030j](../plans/PLAN-030-semantic-layout-translation/PLAN-030j-layout-debt.md)（D1–D5，待批后编码），其后 030i。
- **034**：暂停。
- 弱项仍降级：`cap_body_gap`、续页金样、Figure 像素残影探针（见 WT-033m）。

保护：未改、未提交 `glossaries/auto-proper-nouns.csv`。
