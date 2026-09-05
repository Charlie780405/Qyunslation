# WT-012：扫描书信叠字 / 字号 / 并行 / 进度

**日期：** 2026-09-05  
**状态：** 待部署（见文末）

## 做了什么

- 修中英叠字：原始 OCR 盒擦除 + 细长带过滤 + letter 只回插 logo/stamp
- 正文锁 12pt / 章节 14pt（删 13pt 档）
- 翻译按页并行（默认 4）+ `~/.cache/qyunslation/letter-zh.json`
- HPD 预取架构（探测 1/3/5 → 33/38/46s，默认 workers=1）
- OCR+翻译进 `run_in_executor`，进度 ①识别 / ②翻译 / ③重绘
- `missing_zh` 改告警 + `.warnings.json`
- Skill 铁律 13–18

## 验证

`verify-plan-012.sh` 19/19。

端到端重绘（已有 `text_zh`，workers=1）：

| 项 | 结果 |
| --- | --- |
| 第 2 页 imgs | 2（仅 logo） |
| 第 2 页英文叠字 | 无 |
| 信纸第 12 页 body | 12.0 |
| 墙钟 | ~16s（缓存命中） |

## 使用

文档类型「正式书信」；进度条应可见 ①识别 → ②翻译 n/N → ③排版重绘。

环境变量：

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `QYUNSLATION_HPD_WORKERS` | 1 | HPD 并发（同卡调高通常更慢） |
| `QYUNSLATION_LETTER_WORKERS` | 4 | 按页翻译并发 |
| `QYUNSLATION_LETTER_CACHE` | `~/.cache/qyunslation/letter-zh.json` | 译文缓存 |
| `QYUNSLATION_LETTER_GRAPHICS` | 关 | 设 `1` 才回插 `graphic` |

## 已知限制

- 密页仍可能 `flow 截断` log（不丢单）；装不下打日志
- HPD 与 Ollama 不同卡，但 HPD 服务端自身串行，OCR 段仍约 5.5s/页
