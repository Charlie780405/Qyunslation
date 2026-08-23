# WT-004c LLM 批阈值

**日期：** 2026-08-23  
**状态：** **失败并回滚**（质量门触发）

## 事故（CBP-201 Ph 3.pdf）

- JSON 批译：`Expecting value: line 1 column 1 (char 0)`（模型输出为空）
- `Successful: 0, Fallback: 43`（100% fallback，远超「不得 ≥2× 基线」）
- dual 右侧大段空白，仅剩「五十二」等残片
- `num_predict=512` + `min(..., 1024)` 把批 JSON / fallback 解码截断

## 回滚

| 项 | 现网 |
| --- | --- |
| `config.toml` `num_predict` | **2000** |
| `ollama.py` 封顶 | **已去掉** |
| 批阈值默认 | **200 / 5**（`PDF2ZH_LLM_BATCH_*` 仍可覆盖） |
| 004b skip / glossary / cache 日志 | 保留 |

## 验收

重新翻译同一 PDF 时，journal 不应再出现 `Successful: 0`；dual 右侧应有完整中文段。
