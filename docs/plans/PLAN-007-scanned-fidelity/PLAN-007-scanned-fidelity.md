# PLAN-007：扫描件一对一译文渲染

## 目标

修复扫描 PDF 译文页「英文栅格可见 + 微米级中文叠字」：启用上游 `ocr_workaround`、修正 HPD 隐形层字号/坐标、用 JSON mode 消除译文回退。以第 1 页为快速夹具迭代验收。

## 子计划

| 编号 | 名称 | 依赖 |
| --- | --- | --- |
| 007a | 第 1 页快速夹具 | — |
| 007b | HPD 几何/字号 | 007a |
| 007c | ocr_workaround | 007a |
| 007d | JSON mode | 007a |
| 007e | 全量验收与部署 | 007b+007c+007d |

007b/007c/007d 可并行改码，须一起验收。

## 质量不变量

- 模型 `qwen3.6:35b-a3b`，`temperature=0`，`/no_think`
- `ocr_workaround` **仅** HPD 分支启用，不写进 `config.toml` 全局
- 文字 PDF 不误入 HPD；文字 PDF 渲染不劣化
- 关自动抽术语；QX027 静态 glossary

## Out of Scope

- 默认不做自建栅格渲染器（决策门不达标再升级）
- MinerU / DeepL / 换模型

## 总 SLO（页 1 达标线）

| 指标 | 目标 |
| --- | --- |
| 中文覆盖率 | ≥ 90% |
| 渲染字号中位数 | ≥ 9pt |
| `try fallback` | = 0 |
| 目视 | 无英文叠字；信头/签名可辨 |

## 实现顺序

1. 007a 夹具 + baseline
2. 007b ∥ 007c ∥ 007d
3. 007e 全量 + verify + WT + 部署
