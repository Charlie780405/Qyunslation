# PLAN-059h：模型路由、术语策略与运行时证据

> 父计划：[PLAN-059](./README.md)  
> 状态：待批准  
> 依赖：059a、PLAN-058

## 交付

- 在任务 Manifest/trace 中记录 provider、endpoint、model_id、embedding_model、语言方向、termbase_version、请求对象和降级状态。
- LIVE 验收确认翻译模型是否为泰州 `qwen3.6:35b-a3b`，embedding 是否为泰州 `bge-m3`；配置存在但健康探针不一致只能报告 BLOCKED。
- 译前注入 PLAN-058 的确定性术语策略包；精确/别名命中不调用 embedding；低置信向量候选只能建议，不能硬覆盖。
- 模型超时、JSON 不完整、embedding 不可用时安全降级并标记，不返回伪成功或静默漏译。

## 验收标准

- [ ] 同一任务的所有正文、表格、脚注和图片 OCR 路径使用同一可追溯策略包和语言方向。
- [ ] 运行时探针返回的 Qwen/bge-m3 与目标 allowlist 一致；不一致为 BLOCKED，不以模型别名猜测。
- [ ] 已批准术语遵从率、未知术语、降级状态和模型错误均可在 UI/Manifest 查询。

## 验证、依赖与范围

- 验证：mock provider、泰州 LIVE health/model probe、术语注入回归、失败降级和请求审计。
- 依赖：059a、PLAN-058。文件：`gateway/`、`embed/`、`glossary/`、`structure/model_trace.py`、`tests/server/`。
- 规模：Medium。此计划不训练或微调模型。
