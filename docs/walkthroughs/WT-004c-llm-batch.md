# WT-004c LLM 批阈值

**日期：** 2026-08-23  
**状态：** 已部署补丁；fallback 门与 QnA SLO 待长文档实测

## 变更

`apply-pdf2zh-throughput.py` 将 `process_page` 批门槛改为：

- `PDF2ZH_LLM_BATCH_TOKENS` 默认 **400**（原 200）
- `PDF2ZH_LLM_BATCH_PARAS` 默认 **8**（原 5）

可通过环境变量回滚为 `200` / `5`。

## 门禁（待测）

| 项 | 状态 |
| --- | --- |
| C-V1 批阈值 400/8 | ✅ 补丁已生效 |
| C-V2 fallback ≤2× 基线 | ⏳ 需 10+ 页 PDF 对比 200/5 vs 400/8 日志 `Fallback:` |
| C-V3 QnA ≤10 min | ⏳ 需全量 QX027N QnA 墙钟 |
| C-V4 3 页抽检 | ⏳ 对照 DT-2026-0002 |

未跑长文档前 **不阻塞** 004b；若 fallback 恶化，设 `PDF2ZH_LLM_BATCH_TOKENS=200 PDF2ZH_LLM_BATCH_PARAS=5` 后重启 pdf2zh。

## 回滚

```bash
export PDF2ZH_LLM_BATCH_TOKENS=200 PDF2ZH_LLM_BATCH_PARAS=5
systemctl --user restart pdf2zh.service
```
