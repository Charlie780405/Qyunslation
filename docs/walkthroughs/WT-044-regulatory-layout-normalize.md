# WT-044：监管表单译文版式归一化与交付率收口

日期：2026-09-11  
纲领：[PLAN-044](../plans/PLAN-044-regulatory-layout-normalize/PLAN-044-regulatory-layout-normalize.md)

## 实施前基线（job `fd3b740e`）

| 指标 | 值 |
| --- | --- |
| 表 / 可译格 | 14 / 492 |
| 表格链实绘 | 10 格（2%） |
| FAILED_HARD | 13/14（主因 SOURCE_RESIDUE） |
| 输出字体 | NotoSans + SimSun + Calibri |
| 字号档 | 14；`<7pt` ≈ 70% |

## 实施记录

| 子计划 | 状态 | 交付 |
| --- | --- | --- |
| 044a | 已完成 | `compose_cell_text`：行分桶 + CJK 零空格 + 软换行 |
| 044b | 已完成 | `_llm_translator` 禁止源文伪译文；缺索引单条补译 |
| 044c | 已完成 | `TABLE_CELL_DEGRADED`；残留率 >30% 才表级失败；REGULATORY 启用隔离 |
| 044d | 已完成 | `TABLE_ROLE_SIZE` 阶梯；`measure_textbox`；paint inset ≥1.5/1.0pt |
| 044e | 已完成 | `verify-plan-044.sh`；SK-Q003；错误台账 H/A5/B7–B10/G2 |

## 验证

```bash
bash scripts/verify-plan-044.sh
# 实样：QYUNSLATION_PLAN044_SAMPLE=/path/to/611-3期.pdf
# 重译后：QYUNSLATION_PLAN044_EN_OUTPUT=/path/to/*.tbltr.pdf
```

## 遗留

- [ ] 生产 GUI 对 611-3期 再跑一趟真实 LLM 表格链，核对交付格数与字体归一
- [ ] 残留率阈值 30% 是否需按页调参，待实样分布回写
