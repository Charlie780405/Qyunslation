---
name: translation-quality-evolution
description: >-
  全局翻译质量自进化总纲：裁决反哺规则、领域准确度台账、症状路由到分域 skill。
  触发：规则进化、term-exclusions、台账、SCREEN_BLIND、候选突然很少、already patched、
  PLAN-063、SK-Q011、promote 规则。
---

# 翻译质量自进化总纲（SK-Q011）

## 铁律

1. **每次交付必须跑 SK-Q008 capture 与 `ledger.record_run`。**
2. **规则变更必须 bump `version` 并过 verify 门。** 内容哈希变而版本未变 → `SIG-RULES-VERSION-DRIFT`。
3. **未跑金标回归不得改硬约束。** 阈值 SSOT 是 PLAN-051 四键，不另造一套。
4. **规则提案一律人工 `--promote`，不自动落地。**
5. **候选变少先查裁定通道。** `SCREEN_GENERIC` 高或 `origin=error` 非零按失明处理，不得判干净。

## router

| 症状 | Skill |
| --- | --- |
| 表格崩 / 串格 / 列并了 | SK-Q009 |
| 图内嵌字 / 译文丢字 / 遮盖 | SK-Q002 |
| 改了没效果 / 依然如故 | SK-Q004 |
| 补丁 already patched 但行为是旧的 | SK-Q004 + 本 skill 标记清单 |
| 译文段落丢 / 摘要碎片 | SK-Q005、SK-Q007 |
| 术语链（候选污染、两列空、保存被顶掉） | 本 skill |
| 候选突然很少 / 缩写一个都没进待确认 | 本 skill 的 screen 盲区 |

## 每轮固定动作

译后 → QA/QC 证据落盘 → `--report` / `--screen-pending` → 人工裁决 → `--promote` bump → 金标回归 → 台账曲线。

## 首查

- 规则：`glossaries/term-candidate-rules.toml` `version` 与 `.cursor/skills/skill-registry/term-rules-versions.md` fingerprint。
- 裁定失明：`excluded_stats.screen_origin` / `SCREEN_GENERIC`。
- GUI 漂移：现场 `gui.py` 对补丁标记清单，不是单一 marker。
