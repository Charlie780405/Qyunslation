# PLAN-010b：角色感知聚合 + 落款行款

## 目标

落款/地址逐行独立；块整体偏右、块内左齐。

## 改动

- `scripts/letter_layout.py`：`MERGE_ROLES` / `group_for_merge`；地址 hint 增强
- `scripts/hpd_ocr.py` letter 分支按角色选择性聚合
- `scripts/doc_profiles.toml`：`signature_align = "left"`

## 验收

`bash scripts/verify-plan-010.sh after-b`
