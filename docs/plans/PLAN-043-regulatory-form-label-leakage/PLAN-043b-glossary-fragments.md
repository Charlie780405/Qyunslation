# PLAN-043b：词表补洞、断行标签、人名

> 状态：已完成
> 父计划：[PLAN-043](./PLAN-043-regulatory-form-label-leakage.md)
> 优先级：**P0**（须在 043a 之后）

## 交付

### 1. form 词表补洞

[`glossaries/regulatory-form-fields.csv`](../../../glossaries/regulatory-form-fields.csv) 新增：

| source | target |
| --- | --- |
| 药物名称 | Drug Name |
| 药物类型 | Drug Type |
| 适应症 | Indication |
| 版本日期 | Version Date |
| 试验方案编号 | Protocol Number |
| 临床申请受理号 | Clinical Trial Application Acceptance Number |
| 联系人姓名 | Contact Person Name |
| 联系人手机号 | Contact Mobile |
| 联系人Email | Contact Email |
| 联系人邮编 | Contact Zip Code |
| 方案是否为联合用药 | Is the protocol for combined use? |
| II期 | Phase II |

### 2. 断行拼回

042b lookup：当前段落 + 下一行 ≤2 字 suffix → 拼回后再查 form 层（如 `方案是否为联合用`+`药`）。

### 3. 人名

- [`glossaries/org-proper-nouns.csv`](../../../glossaries/org-proper-nouns.csv) 或 form 层：`周清红` → `Zhou Qinghong`
- [`regulatory_entities.py`](../../../qyunslation/structure/regulatory_entities.py)：2–4 字纯 CJK 人名**先查词表**；未命中才保留原文（组织名逻辑不变）

## 验收

- `build_merged_dict()` 命中上述新增项。
- 611-2期 P1 文本层不含 `周清红`；含 `Zhou Qinghong`。
- 043a+043b 后 P1 L1 短标签清单零残留（见 043d）。
