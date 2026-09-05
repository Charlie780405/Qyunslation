# PLAN-009：书信角色字号与中文行款

在 PLAN-008 `letter` 模板上补层级，**不重排整页**。信头/地址/正文/落款仍落在原信对应盒子里，只改字号、缩进、对齐和中文标点。文献 / IND 模板本 PLAN 不动。不改泰州 HPD。

## 目标

| 角色 | 字号 | 行款 |
| --- | --- | --- |
| header / address / signature | 9pt | 落款块内右齐 |
| salutation | 10.5pt | 顶格 |
| body | **12pt** | 段首 `　　`；行距 1.5 |
| closing | 9.5pt | 不居中 |
| footer | 8.5pt | 原位 |

## 实现清单

| ID | 内容 | 状态 |
| --- | --- | --- |
| 009a | `scripts/letter_layout.py` tag/clean；`hpd_ocr` 仅 letter 调用 | done |
| 009b | `doc_profiles.toml` `[letter]` 字号/缩进/右齐字段 | done |
| 009c | `doc_profile.patch_letter_typesetting` 运行时注入 | done |
| 009d | V7 页 1 验收 + verify + WT | done |

## 关键文件

- `scripts/letter_layout.py`
- `scripts/hpd_ocr.py`（`profile=letter` 时清洗）
- `scripts/doc_profiles.toml` / `scripts/doc_profile.py`
- `scripts/apply-pdf2zh-docprofile.py` / `scripts/run_babeldoc_letter.py`
- `scripts/bench-scanned-page1.sh`（V7）
- `scripts/verify-plan-009.sh`
- `deliverables/plan-009-letter/`

## 不做

- 不改泰州 HPD `/parse`
- 不整页重排、不自定义字体
- 不在本 PLAN 做文献/IND 层级
- 不重跑 20 页
