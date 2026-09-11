# PLAN-042c：词内断裂与行内重排

> 状态：**已完成**
> 父计划：[PLAN-042](./PLAN-042-regulatory-translation-quality.md)

## 交付

1. `scripts/doc_profile.py`：`patch_regulatory_typesetting()` — 禁止词内断行、拉丁词整词换行、CJK/Latin 边界不插半空格。
2. `apply-pdf2zh-docprofile` / regulatory 路径启用该补丁。
3. 合成断词压力夹具断言 `score`/`indicator`/`Monoclonal`/`Endpoints` 完整。

## 验收

- 拉丁词零词内断裂。
- letter 模板既有补丁不受影响。
