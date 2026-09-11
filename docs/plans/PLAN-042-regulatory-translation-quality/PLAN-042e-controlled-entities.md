# PLAN-042e：受控实体与确定性映射

> 状态：**已完成**
> 父计划：[PLAN-042](./PLAN-042-regulatory-translation-quality.md)

## 交付

1. 扩写 `glossaries/org-proper-nouns.csv`：三生国健/3SBio、代表性医院与院校官方英文名。
2. `glossaries/regulatory-form-fields.csv`：章节序号（一→I …）、量词（日/周/分/例）。
3. `qyunslation/structure/regulatory_entities.py`：未命中实体策略（保留原文）；罗马数字抽取纠正（II≠11）。

## 验收

- 申办方/医院命中受控层或保留原文。
- 章节序号不重号；II 期不被读成 11 期。
