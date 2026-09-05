# PLAN-010：扫描件版式保真通用化

PLAN-009 只解决了字号层级。本 PLAN 处理**这一类扫描件都会犯**的四个问题，并沉淀为 Skill。不改泰州 HPD。

## 目标

| 现象 | 对策 |
| --- | --- |
| 2.4–6pt 碎字 | `_deoverlap_boxes` + 微段落抑制 |
| 落款挤行 / 乱套 | 角色感知聚合；`signature_align=left` |
| logo 丢失 | `graphic_regions` 检测 + 译后 `graphic_reinsert` |
| GenScend→金斯瑞 | `glossaries/proper-nouns.csv` + harvest identity |

## 实现清单

| ID | 内容 | 状态 |
| --- | --- | --- |
| 010a | `_deoverlap_boxes` / `_expand_boxes` 全后继；微段落抑制 | done |
| 010b | `MERGE_ROLES` + 落款左齐 | done |
| 010c | `graphic_regions` / `graphic_reinsert` + GUI/bench | done |
| 010d | 专名表 + harvest + `--glossaries` | done |
| 010e | V8 + `verify-plan-010.sh` + deliverables + WT | done |
| 010f | Skill SK-Q001 + registry/verify/sync | done |

## 关键文件

- `scripts/hpd_ocr.py` / `scripts/letter_layout.py` / `scripts/doc_profile.py`
- `scripts/graphic_regions.py` / `scripts/graphic_reinsert.py`
- `scripts/proper_nouns.py` / `glossaries/proper-nouns.csv`
- `scripts/bench-scanned-page1.sh`（V8）
- `scripts/verify-plan-010.sh`
- `deliverables/plan-010-fidelity/`
- `.cursor/skills/scanned-doc-layout-fidelity/`

## 不做

- 不改泰州 HPD `/parse`
- 不整页重排、不自定义字体文件
- 不做文献/IND 模板的角色层级
- 不重跑 20 页；不接 OCR 之外的版式模型
