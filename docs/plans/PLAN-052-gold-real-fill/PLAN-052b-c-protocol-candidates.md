# PLAN-052b：C 类临床真件候选

> 状态：**已实现**
> 父计划：[PLAN-052](./PLAN-052-gold-real-fill.md)
> 依赖：052a

## 目标

登记 Protocol / CDP 为 **C** 槽（**不是** CTD M2 / R）。M2.5 综述走 R-01，见登记表。

## 候选

| entry | 来源 | kind | 状态 |
| --- | --- | --- | --- |
| C-04 | 本机 STREAM-AD-Protocol.pdf | protocol | promoted |
| C-05 | 本机 SOLO1-2-Protocol.pdf | protocol | promoted |
| C-06 | `docs/Resources/` GS101 1 期方案 DOCX | protocol | promoted |
| C-07 | `docs/Resources/` GS101 CDP DOCX | cdp | promoted |

R-01：`docs/Resources/` GS101 临床综述 / CTD M2.5（**禁止**标成 C）→ promoted。

## 判据

- C real ≥5（本机 7）
- C-06/C-07/R-01 在 `real-sources.json` 且 kind 与类诚实表一致
- R-01 为唯一 R real（产品条件已满足）
