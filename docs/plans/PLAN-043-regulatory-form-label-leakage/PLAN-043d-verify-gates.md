# PLAN-043d：金标门禁与交付

> 状态：已完成
> 父计划：[PLAN-043](./PLAN-043-regulatory-form-label-leakage.md)

## 交付

1. `scripts/verify-plan-043.sh`
2. [WT-043](../../walkthroughs/WT-043-regulatory-form-label-leakage.md)
3. 扩写 [SK-Q003](../../../.cursor/skills/pdf-regulatory-form-fidelity/SKILL.md)

## P1 L1 标签硬断言清单（EN 文本层不得出现）

```
登记号 试验状态 进行中 申请人联系人 首次公示信息日期 申请人名称
一、题目和背景信息 相关登记号 试验专业题目 试验通俗题目 方案最新版本号
二、申请人信息 联系人邮政地址 三、临床试验信息
试验分类 安全性和有效性 试验分期 设计类型 平行分组 随机化 盲法 双盲
试验范围 国内试验 年龄 性别 男+女 健康受试者 否 无 生物制品 临床研究
药物名称 药物类型 适应症 版本日期
```

人名：不得出现 `周清红`；允许 `Zhou Qinghong`。

## verify 规则

| 条件 | 行为 |
| --- | --- |
| 无 `QYUNSLATION_PLAN043_SAMPLE` | `BLOCKED` |
| 有实样 | P1 L1 清单零命中 + `scan_page_text_qc` CJK 相对基线 177 下降 |
| 回归 | `verify-plan-041.sh` / `verify-plan-042.sh` 不红 |

GUI 仍可告警交付（042f）；verify 硬门只卡 CI/发布。

## 部署

- 精确 commit → no-ff merge main → `systemctl --user restart pdf2zh.service`
- 042b 补丁在 ExecStartPre 链；重启即重打
