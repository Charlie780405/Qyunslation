# WT-045：学术文献 PDF 译文保真

日期：2026-09-11  
纲领：[PLAN-045](../plans/PLAN-045-literature-pdf-fidelity/PLAN-045-literature-pdf-fidelity.md)  
分支：`feat/PLAN-045-literature-pdf-fidelity`

## 实施记录

| 子计划 | 状态 | 交付 |
| --- | --- | --- |
| 045a | 已完成 | L1 终点短语；图片默认 `merged.csv`；`glossary_merge_runtime` 已跑 |
| 045b | 已完成 | `1Langanan` 等粘连 ENTRY_RE；033h 补丁仍在现场 |
| 045c | 已完成 | `text_sanitize` + `apply-pdf2zh-045c-sanitize.py`；service ExecStartPre |
| 045d | 已完成 | `panel_letter`；`TIER_K_FLOOR`；擦除 2 轮；`SOURCE_INK_LEFT` 熔断 |
| 045e | 已完成 | 文献 `source_p75`；与 REGULATORY `ladder` / `isolate_residue` 拆开 |
| 045f | 已完成 | PLAN 目录、`verify-plan-045.sh`、SK-Q002、错误台账 L 族 |

## 验证

```bash
bash scripts/verify-plan-045.sh
# 实样：QYUNSLATION_PLAN045_SAMPLE=/path/to/literature.pdf
# 重译后：QYUNSLATION_PLAN045_EN_OUTPUT=/path/to/*.en*.pdf
```

## 部署注意

- 重启 `pdf2zh.service` 以应用 045c ExecStartPre。
- 旧译文 PDF 不会自愈，需对文献样例重新提交翻译。
- 实样与截图不入库。
