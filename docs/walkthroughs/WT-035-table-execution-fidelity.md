# WT-035：表格执行侧数字保护与跨页续表

日期：2026-09-10  
纲领：[PLAN-035](../plans/PLAN-035-table-execution-fidelity/PLAN-035-table-execution-fidelity.md)

## 交付摘要

- `table_cell_policy.py`：单元格 `PRESERVE` / `PROTECT_TOKENS` / `TRANSLATE` SSOT
- `table_translate.py`：纯数值不进 LLM；译后 `TABLE_DIGIT_DRIFT` 硬失败
- `scan_pdf.py`：`continued_table_anchors` 接线；`semantic_occurrence_index` 多页续表
- `pdf_table_translate.py`：按 occurrence 排序；`digits_preserved` 回写
- 合成夹具 `continued-table.pdf`（`generate_synthetic.py` + `catalog.v1.json`）
- `scripts/verify-release.sh` 发布总门（串 030i / 035 / 030-table / 033l）

## 验收

```bash
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python bash scripts/verify-plan-035.sh
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python bash scripts/verify-release.sh
```

预期：`verify-plan-035.sh` → `SUMMARY: PASS fail=0`；`verify-release.sh` → `SUMMARY: PASS`（033l 无本机样本时为 `BLOCKED`，不 block 035 单门）

## 部署

**记录（2026-09-10）**

| 项 | 值 |
| --- | --- |
| merge | `6162f3e`（main，含 catalog 热修） |
| 前置 | `4300938` PLAN-035 功能 merge |
| 服务 | `pdf2zh.service`、`qyunslation-office.service` → active |
| PYTHONPATH | `/home/dev/qyunslation`（与开发树同步） |

部署后复验：

```bash
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python bash scripts/verify-release.sh
```

**结果（2026-09-10）**：030i / 035 / 030-table **PASS**；033l **BLOCKED**（本机缺 final mono/dual PDF，符合 `verify-release.sh` 设计）。样本机应设 `QYUNSLATION_RELEASE_STRICT_SAMPLE=1` 使 033l 也 hard-fail。

扫描器升至 **1.7.0**：旧 manifest 缓存失效，用户需对同一 PDF **重新预扫** 才能看到跨页续表 occurrence 与 cell policy。

## 回滚

- `git revert` PLAN-035 merge commit
- `systemctl --user restart pdf2zh.service qyunslation-office.service`
- `verify-plan-030-table.sh` + `verify-plan-030i.sh` 仍为结构回归门

## 遗留

- ljae439 无跨页续表样本：V6 降级为 INFO
- DOCX/PPTX 表格 policy 对齐：后续引用同一 SSOT
- WT-030-table「跨页续表 out of scope」文案待指向 PLAN-035

## 下一步建议

| 优先级 | 项 | 说明 |
| --- | --- | --- |
| P0 | 真实续表金样 | 从知识库/生产找 `Table N Continued` PDF，补 `tests/fixtures/structure/reference/`，把 035 continuation 从合成件升级为硬金样 |
| P1 | `table_cell_policy` 跨格式 | 让 `scan_docx`、`md_tables`、`doc_image_policy` 引用同一 SSOT，消除三处 numeric 规则漂移 |
| P1 | UI 可观测 | manifest/执行失败展示 `TABLE_DIGIT_DRIFT`、`digits_preserved`、`TABLE_CONTINUATION_UNLINKED` |
| P2 | ~~PLAN-036 立项~~ | 已开 [PLAN-036](../plans/PLAN-036-table-policy-unification/PLAN-036-table-policy-unification.md)（policy 统一 + 续表金样） |
| P3 | 纯图片表 / PPT OCR | 036 后再立项，勿空开 PLAN-034 |
| P2 | 发布纪律 | CI/部署前固定跑 `verify-release.sh`；样本机设 `QYUNSLATION_RELEASE_STRICT_SAMPLE=1` 使 033l 也 hard-fail |
