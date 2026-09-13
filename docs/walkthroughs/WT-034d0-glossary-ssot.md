# WT-034d0：术语 SSOT 与 prompt 桥接

对应 [PLAN-034d0](../plans/PLAN-034-pharma-rd-mvp/PLAN-034d0-glossary-ssot-bridge.md)。分支：`feat/PLAN-034-pharma-rd-mvp`。

## 执行摘要

扁平术语三分裂已收敛：`glossary_db` 预置改走四层 `build_merged_dict`；UI 增量导出 `glossaries/staging/ui-increment.csv`（layer=session）并入 merge；`start_translation` 挂 SSOT `glossary_dict`，**不**写全表 `custom_prompt`；chunk 命中过滤 + 中文强指令在 `Glossary.append_system_prompt`；键统一 `_normalize_key`。

## 历史对照（实现前 → 后）

| 锚点 | 实现前 | 实现后 |
| --- | --- | --- |
| `load_glossary` vs `build_merged_dict` | ≈209 vs ≈370（缺 org/form/project） | 空 json 时条数一致 |
| 全表 `build_glossary_prompt` | ≈9429 字符 | 运行时按 chunk 命中；无命中返回空 |

## 变更明细

| 文件 | 摘要 |
| --- | --- |
| `qyunslation/extensions/glossary_db.py` | 四层预置；`filter_glossary_hits`；`export_ui_increment_csv` |
| `qyunslation/glossary/glossary.py` | `_normalize_key`；中文命中注入 |
| `qyunslation/glossary/ssot.py` | `apply_ssot_to_payload` / `merge_ssot_glossary` |
| `qyunslation/server/core.py` | `start_translation` 调用 SSOT |
| `scripts/glossary_merge_runtime.py` | 纳入 ui-increment session |
| `agents/markdown_agent.py` / `segments_agent.py` | `update_glossary_dict` → `Glossary.update` |
| `tests/glossary/test_plan034d0_ssot_bridge.py` | 单测 |

## 验证

| # | 项 | 结果 |
| --- | --- | --- |
| V1 | pytest 034d0 + glossary | PASS |
| V2 | `verify-plan-034.sh` | PASS |
| V3 | 空 json 条数对齐 | PASS |

## 已知限制

- 图片嵌字 RapidOCR 仍读 `merged.csv`；UI 新词需跑 `glossary_merge_runtime.py` 后才进 PDF/图片链。
- Concept / TBX / 审批 → 034d；TM → 034e。
