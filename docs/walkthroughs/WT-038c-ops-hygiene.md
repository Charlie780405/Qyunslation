# WT-038c：运维卫生

日期：2026-09-10  
纲领：[PLAN-038c](../plans/PLAN-038-gap-closure/PLAN-038c-ops-hygiene.md)

## 交付

| G-ID | 结果 |
| --- | --- |
| G-OPS-001 | `docutranslate.service` → `disabled`（再核实） |
| G-OPS-002 | `fix-archive-filenames.py --apply`：11 条；备份 `index.bak-20260910T120940Z.db`；再跑 dry-run「无需修正」 |
| G-OPS-003 | STRICT_SAMPLE 文档化；本机未强制 |
| G-OPS-004 | WT-035：scanner≥1.7.0 须重新预扫 |
| G-OPS-006 | 删除 `codex/recovery-030e-030f-20260908`（0 ahead / 90 behind main；本地 + origin） |

## 关闭缺口

G-OPS-001…004、G-OPS-006 全部 closed
