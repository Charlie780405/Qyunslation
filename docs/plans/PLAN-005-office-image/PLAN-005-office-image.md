# PLAN-005：Word / 扫描 PDF / 图片嵌字

## 目标

现网 `translate.qyunsgen.com` 只收 PDF（BabelDOC）。本期补齐：**可编辑 .docx**、**图片型 PDF 可选中译文**、**图内嵌字覆盖**。不换模型、不把 Word 塞进 BabelDOC。

## 子计划

| 编号 | 名称 | 依赖 |
| --- | --- | --- |
| 005a | 扫描 PDF 正规化（HPD） | PLAN-003/004 质量回滚 |
| 005b | Word sidecar | 与 005a 可并行 |
| 005c | 图片嵌字 | 005b + HPD |
| 005d | 归档/检索 | 005b |
| 005e | 统一入口（门禁） | 默认不做 |

## 质量不变量

- 模型 `qwen3.6:35b-a3b`，禁止 27b
- `temperature=0`，`/no_think`
- 关自动抽术语；QX027 静态 glossary
- 文字 PDF：BabelDOC；`num_predict=2000`；批阈值 200/5
- Caddy 只 reload；不改 translate→7860 默认站

## Out of Scope

- MinerU 重排版 / xlsx/pptx / DeepL / vLLM
- 扫描 PDF 内插图再嵌字
- 再封 num_predict / 无门禁上调批阈值
- BabelDOC 链进 Qyunslation（AGPL）

## 总 SLO

| 阶段 | 速度 | 质量 |
| --- | --- | --- |
| 005a | 扫描 ≤ 文字同段数 + 1.5× HPD | dual 可选中；文字 PDF 不误入 HPD |
| 005b | ~200 段 docx ≤8 min | 可编辑、样式在 |
| 005c | 单图 ≤90s | 覆盖可读；图失败不毁全文 |
| 005d | 译完归档可见 | 同一 DT 体系 |
| 005e | 仅门禁 | 不损伤 PDF 站 |

## 实现顺序

1. 落盘 PLAN/verify
2. 005a ∥ 005b → 005c → 005d
3. 未要求单 URL → WT 关 005e
